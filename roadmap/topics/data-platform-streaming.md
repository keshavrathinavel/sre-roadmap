# Streaming Data Platforms — Kafka, Flink, Spark for SREs

> This is written from the **operational seat**: you keep these systems running, you don't
> necessarily write the jobs that run on them. Hands-on labs for this topic live in
> `roadmap/failure-labs/data-platform.md`, using the same diagnosis discipline as the Kubernetes
> failure curriculum: Symptoms → Hypothesis → Diagnose → RCA sentence → Fix + prevention.
>
> Two framings worth leading with in any design or troubleshooting answer on this topic:
> 1. **Reliability for a data platform means correctness, not just availability** — no loss, no
>    duplication, freshness, completeness. Uptime is table stakes.
> 2. **Flink state is a database you have to operate** — size it, back it up, retain it, recover it.

---

## Kafka (the backbone)

**Why it matters:** a streaming data platform is Kafka feeding stream/batch processors (Flink, Spark). It's the backbone — it shows up in every design and every incident.

### Core concepts

- **Topic:** a named, append-only log of records — the unit you produce to and consume from.
- **Partition:** a topic is split into partitions, each an independently ordered, append-only sequence. Ordering is only guaranteed *within* a partition, never across partitions of the same topic — this is the single most-missed fact about Kafka ordering.
- **Offset:** a record's position within its partition — a simple monotonically increasing integer. Consumers track "the next offset I haven't read yet" per partition; that tracked position is what "committing an offset" means.
- **Broker:** a single Kafka server; a cluster is many brokers. Each partition is hosted (led) by one broker at a time (its **leader**), with replicas on other brokers as followers — see Replication below.

### Producers

- **`acks`** controls how many replicas must confirm a write before the producer considers it successful: `acks=0` (fire and forget, fastest, can silently lose data), `acks=1` (leader only — can lose data if the leader dies before followers replicate), `acks=all`/`-1` (leader + all in-sync replicas — the durability-first setting, paired with `min.insync.replicas`).
- **Retries:** producers retry on transient failures (broker not available, timeout); with retries enabled but *without* idempotence, retries can create duplicates — this is exactly what idempotence exists to fix.
- **Batching:** producers buffer records and send them in batches (`batch.size`, `linger.ms`) rather than one request per record — the throughput/latency tradeoff knob. `linger.ms` deliberately delays sending to let a batch fill up.
- **Idempotence:** an idempotent producer (`enable.idempotence=true`) tags each batch with a producer ID + sequence number, so the broker can detect and drop a duplicate from a retried send. This turns "at-least-once with occasional duplicates from retries" into effectively-once *per partition* — the foundation Kafka transactions build on for full exactly-once (see the Exactly-once section below).

### Consumers

- **Consumer groups:** consumers subscribing to a topic as part of the same group split its partitions between them — each partition is read by exactly one consumer in the group at a time, which is *how* Kafka parallelizes consumption. Partition count is therefore a hard ceiling on a group's consumer parallelism: a 6-partition topic can use at most 6 consumers in one group productively; the 7th sits idle.
- **Partition assignment:** the group coordinator (a broker) assigns partitions to the group's live consumers using an assignment strategy (range, round-robin, or the sticky/cooperative strategies that minimize reshuffling).
- **Rebalancing:** whenever group membership changes (a consumer joins, leaves, or is considered dead by a missed heartbeat), the group coordinator triggers a rebalance — partitions get reassigned, and consumption pauses for every member during it, not just the one that changed. Frequent rebalances (from slow processing that misses `session.timeout.ms`, or from aggressive/misconfigured timeouts) cause repeated stall-and-reprocess cycles, which is often confused with the workload itself being slow.

### Consumer lag

**Consumer lag** = the difference between the latest offset produced to a partition and the offset a consumer group has committed for it — literally "how many records behind is this consumer." It's the core SLO input for a streaming pipeline: lag that's flat (even if nonzero) means the consumer is keeping pace; lag that's *growing* means it's falling behind and will keep falling behind until something changes. Alert on the lag **trend**, not just a static lag threshold — a consumer that's 10,000 records behind but shrinking is healthy; one that's 100 records behind but climbing is not.

### Retention policies

Kafka keeps data for a configured retention window, not forever — this is what bounds how far back replay/backfill can reach.
- **Time-based** (`retention.ms`) — delete segments older than N.
- **Size-based** (`retention.bytes`) — cap total partition size, oldest segments evicted first.
- **Compaction** (`cleanup.policy=compact`) — instead of deleting by age/size, keep only the *latest* record per key, deleting older records for the same key. Used for topics that represent current state (e.g. "latest value per user ID") rather than an event history — a changelog, not a log of everything that ever happened.

### Replication

- **ISR (In-Sync Replicas):** the set of replicas (leader + followers) that are fully caught up with the leader. A replica that falls behind (slow disk, network issue, GC pause) drops out of the ISR.
- **`min.insync.replicas`:** the minimum ISR size required for a write with `acks=all` to succeed. If the ISR shrinks below this (e.g. two broker failures with `min.insync.replicas=2`), producers using `acks=all` start getting errors — a deliberate trade of availability for durability, not a bug.
- **Under-replicated partitions:** a partition whose ISR is smaller than its configured replication factor — some replica isn't caught up. This is a leading-indicator metric worth alerting on directly, because it's the state that precedes data-loss risk (if the leader dies while a partition is under-replicated, an out-of-sync replica may have to take over with missing data, or the partition may go unavailable, depending on `unclean.leader.election.enable`).

## Flink (hard because of state)

**Why it exists:** true stream processing with low latency and managed state. The operational difficulty is that state is effectively a database you have to run.

### Architecture

- **JobManager:** the coordinator — owns scheduling, checkpoint coordination, and failure recovery for the jobs running on the cluster. A single point of failure without HA: lose it with no standby and you lose the job's coordination state along with it.
- **TaskManager:** a worker process that actually executes operators and holds their state and buffers.
- **Slots:** each TaskManager offers a fixed number of task slots — the unit of resource a single parallel instance of an operator occupies. Total slots across all TaskManagers is the hard ceiling on how parallel a job can run.
- **Parallelism:** how many parallel instances of each operator run, set per-job or per-operator; bounded above by total available slots. This is the dial you turn to fix backpressure at a specific operator (see below) rather than the whole job.

### Job lifecycle

A Flink job moves through a small state machine: **CREATED → RUNNING → FINISHED** (batch jobs / bounded streams that complete normally) **/ CANCELLED** (a user or system explicitly stopped it) **/ FAILED** (an unrecoverable exception, or the configured restart strategy exhausted its attempts). A job stuck cycling **RESTARTING** between attempts — visible in the Flink UI's exception history — is the signature of a **restart loop**: something is failing deterministically on every retry (see Job restart loops in the failure lab), not a transient blip that a restart should have cleared.

### Streaming vs batch mode

Flink runs the same engine in two modes: **streaming** (unbounded input, results emitted continuously, checkpointing for fault tolerance) and **batch** (bounded input, optimizations like sorting/blocking exchanges that assume the input has an end, no need for continuous checkpointing since a failed batch job can just restart from the beginning). Knowing which mode a job runs in matters operationally — batch-mode failure recovery and streaming-mode failure recovery look and behave differently, and a job accidentally left in the wrong mode has a very different cost profile than intended.

### Sources and sinks

A Flink job is a graph of transformations between a **source** (where data enters — a Kafka topic is the overwhelmingly common one) and one or more **sinks** (where results leave — commonly an object-store/lake sink like S3 or HDFS via a table format, or a JDBC sink into a relational database for smaller, query-friendly outputs). Source and sink choice is what most exactly-once and reliability guarantees ultimately hinge on — see the sink layer section below and the Exactly-once mechanics section for why the *sink's* capabilities (does it support two-phase commit? is it idempotent to retries?) determine what end-to-end guarantee is actually achievable, not just what Flink itself does internally.

### Checkpointing and savepoints

- **Checkpointing:** periodic distributed snapshots of all operator state to durable storage — the automatic recovery mechanism. Most production pain is checkpoint duration and frequency, not the concept itself.
- **Checkpoints vs savepoints:** checkpoints are automatic and for recovery; savepoints are manual and for upgrades, migrations, and rescaling — you take a savepoint deliberately before touching the job, then restore from it.
- **Incremental vs full checkpoints:** a full checkpoint snapshots all state every time; an incremental checkpoint (RocksDB state backend only) writes just the state that changed since the last checkpoint, trading a bit of recovery-time complexity for dramatically cheaper ongoing checkpoint cost on large state.

### State management

- **Keyed state:** state partitioned by a key (e.g. per-user running totals) — scoped to whichever key a given record carries, and it's what gets redistributed if you rescale parallelism.
- **Operator state:** state scoped to an operator instance as a whole, not partitioned by key — used when there's no natural per-key split (e.g. a source tracking its own offsets).
- **State backends:** heap-based (state lives as JVM objects — small, fast, but bounded by TaskManager memory) vs **RocksDB-based** (state spills to local disk, so it can grow far larger than memory, at the cost of serialization overhead per access). This is the same knob mentioned in the checkpointing note above — RocksDB is also the backend that enables incremental checkpoints.
- **Unbounded growth:** keyed state with no TTL and no windowing accumulates forever as new keys arrive — checkpoints slow down and memory pressure rises well before anything crashes outright. Treat state as a database with a retention policy, not a free-standing accumulator.

### Backpressure

When a downstream operator can't keep up, it slows everything upstream — visible directly in the Flink UI's backpressure view. The classic "pipeline is lagging but nothing is crashing" symptom: no exception, no restart, just growing end-to-end latency. See the failure lab for how to trace it to the actual bottleneck operator.


## Event-time, watermarks, and late data (the correctness centerpiece)

- **Why this is non-negotiable:** if your differentiator is correctness, this is the mechanism that delivers it. For any mobile/IoT-style event stream, late data is the norm, not the exception — a device goes offline, then reconnects and dumps hours of backlogged events.
- **Event-time vs processing-time vs ingestion-time:** event-time is when the event actually happened (embedded timestamp); processing-time is when the operator sees it. Correct aggregates use event-time.
- **Watermark:** a marker flowing through the stream that asserts "I believe I've seen all events up to time T." Windows fire when the watermark passes the window end.
- **Windowing:** tumbling, sliding, session. The watermark decides when each window closes.
- **Allowed lateness and late data:** events arriving after the watermark can be dropped, sent to a side output (a dead-letter path for later correction), or used to re-emit a corrected result. Know all three options and when each fits.
- **The operational trap (the classic war story):** the watermark is the **minimum across all input partitions**. One idle partition never advances its watermark, so the global watermark stalls, so windows never fire, so dashboards silently stop updating with **no error**. The fix is idleness detection (`withIdleness`). This is the hidden cause of a large fraction of "the numbers are wrong or lagging" incidents — which makes watermarks an operational topic, not just a design one.
- **The likely follow-up question:** "A user's offline event from three hours ago arrives now, but that hourly window already closed and shipped to the dashboard. What happens?" Answer with watermark → allowed lateness → side-output → corrected re-emit.

## Spark (operational axis)

- **Why it exists:** distributed batch and micro-batch compute. You operate the cluster; you don't necessarily write the pipelines.
- **Driver and executor model:** the driver builds the DAG and schedules; executors run tasks and hold data. Driver failure recreates the context; executor failure reassigns tasks.
- **The shuffle:** redistributing data across partitions (`groupBy`, `join`, `repartition`). Expensive, spills to disk, source of most performance incidents.
- **Data skew (the single most important Spark operational topic):** uneven key distribution sends most data to one task, which runs forever or OOMs while the rest sit idle. This is the one Spark topic that reliably gets asked about.
- **Executor OOM:** usually skew, oversized partitions, or too little executor memory.
- **Capacity knobs:** `spark.executor.instances`, `spark.executor.memory`, `spark.executor.cores`, `spark.sql.shuffle.partitions` — your K8s requests/limits intuition, translated.
- **Dynamic allocation:** scales executors with workload.
- **Fault tolerance:** RDD lineage recomputes lost partitions; checkpointing persists to durable storage to avoid long lineage recomputation.
- **One-liner:** "Spark recovers by recomputing from lineage, Flink by restoring from periodic state snapshots — which is why Flink recovers faster and with less disruption."

## Exactly-once, how it actually works

"Exactly-once is real but costs latency" is a soundbite that invites a follow-up. Have the mechanism ready:
- **Flink side:** checkpoint barriers flow through the dataflow and operators snapshot state when the barrier passes (a Chandy-Lamport-style distributed snapshot). For end-to-end exactly-once to an external sink, the sink must do **two-phase commit** coordinated with checkpoints: pre-commit on checkpoint, commit on checkpoint-complete.
- **Kafka side:** the idempotent producer dedupes retries via a producer ID and per-partition sequence number; Kafka transactions make multi-partition writes atomic with read-committed consumers. Flink's Kafka sink uses these for end-to-end exactly-once.
- **The cost:** results only become visible at checkpoint commit, so the checkpoint interval bounds end-to-end visibility latency. That's the latency price, stated precisely.

## The sink layer: the lake and the serving tier are two different systems

A common design ask is "push to data lakes for analysts and feed live dashboards" — these are two sinks with two different reliability profiles. Don't collapse them into "a sink."
- **The lake (batch, query in seconds):** columnar files (Parquet, ORC) on S3/GCS, organized by a table format (Iceberg, Delta, Hudi). A table format gives atomic commits, schema evolution, and time-travel — what makes safe backfills and rollbacks possible.
- **The small-files problem (a real recurring incident):** a streaming job writing every few seconds produces millions of tiny files, which destroys query performance and hammers object-store list operations until they throttle. Compaction jobs (Iceberg rewrite, Delta `OPTIMIZE`) are ongoing operational work — a strong "incident you'd expect to operate" answer.
- **The serving tier (sub-second dashboard queries):** live dashboards aren't the lake. They're Druid, ClickHouse, Pinot, BigQuery, or Elasticsearch. Different SLO (sub-second), different failure modes (ingestion lag, segment/shard balance, memory pressure) from the batch lake.
- **Backfill and reprocessing (first-class, not a name-check):** "yesterday's numbers are wrong, replay from Kafka without double-counting." The mechanics: idempotent writes (upsert on a dedup key), atomic partition overwrite via the table format, and careful offset management for where the replay starts and stops.

## Monitoring the pipeline

- **Golden signals for a streaming pipeline, with an SLO on each:**
  - **Consumer lag (Kafka)** — the headline health signal. SLO on max lag and lag duration.
  - **End-to-end latency** — event timestamp to result available. The user-facing SLO.
  - **Throughput** — events per second, against expected volume.
  - **Checkpoint duration and size (Flink)** — rising means trouble before it becomes an outage.
  - **Error rate** — failed records, dead-letter volume, late-data drop count.
  - **Data freshness and completeness** — how current and how complete the output is. The correctness SLO.
- The framing to say out loud: *"I would not alert on job-down, I would alert on these leading indicators, because by the time the job is down the dashboard has already been wrong for an hour."*

## GCP ↔ AWS mapping (translation, not depth)

If you're AWS-native and the platform in question is on GCP (or vice versa), the real question is "can you transfer": GKE↔EKS, GCS↔S3, Dataproc↔managed Spark, Dataflow↔managed streaming, Pub/Sub↔Kafka-ish messaging, BigQuery↔the warehouse, Cloud Monitoring↔CloudWatch.

---

For hands-on labs that turn this topic map into muscle memory — breaking a Flink pipeline's backpressure, killing a JobManager with no HA, inducing Spark data skew — see `roadmap/failure-labs/data-platform.md`.
