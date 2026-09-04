# Failure Lab — Streaming Data Platforms (Kafka / Flink / Spark)

> Topic knowledge for this lab lives in `roadmap/topics/data-platform-streaming.md` — read that
> first. This is the hands-on curriculum: same philosophy as the Kubernetes failure lab —
> **break it on purpose, watch the symptom, diagnose from first principles, write the RCA sentence.**
> Run on your own machine (Docker Desktop or a Multipass/VM).

## If you only have time for four labs, do these

1. **Flink Operations Playground** (backpressure, kill the JobManager with no HA, checkpoint timeout). Highest ROI — turns abstract state and recovery into war stories you can narrate. The Playground also ships a Kafka broker, which doubles as your Kafka lab environment.
2. **Kafka consumer lag spike lab.** Consumer lag is the single most-referenced streaming health signal — know it from first principles, not just the dashboard number.
3. **Spark skew lab.** The one Spark topic that actually gets asked.
4. **Flink watermark / late-data lab.** The correctness story the whole topic is built on.

## Setup options

- **Kafka, fastest path:** the Flink Operations Playground's docker-compose already includes a Kafka broker (it's how the Playground's demo job gets its data) — reuse that broker directly rather than standing up a separate cluster. `kafka-consumer-groups.sh --describe` (or `kcat`/`kafkacat` for quick produce/consume) is enough for every lab below.
- **Spark, fastest path:** `pip install pyspark` and run local jobs. Local mode reproduces skew, shuffle spill, and driver OOM. For a real driver/executor split, use the `apache/spark` Docker image in standalone mode.
- **Flink, best path:** the official **Flink Operations Playground** (docker-compose setup from the Flink docs, built for exactly this — observe jobs, kill components to watch failure recovery, upgrade with savepoints, rescale, read metrics). Pull the current compose file from the docs since it tracks the release.
- **Watch symptoms through the UIs:** Spark UI (port 4040), Flink UI (port 8081) — treat them like k9s and Grafana: the UI is where the symptom becomes legible.

## Flink labs

### Lab 1 — Backpressure
- **Break it:** fast source, deliberately slow operator or sink (a sleep in a map, or a slow sink).
- **Symptoms:** the pipeline lags and falls behind real time, nothing crashes, source lag grows.
- **Hypothesis:** a downstream operator can't keep up and is slowing the whole pipeline.
- **Diagnose:** Flink UI backpressure view. Trace upstream from the busy operator — the first operator showing high backpressure points at the one below it.
- **RCA sentence:** "A slow downstream operator applied backpressure up the chain, which throttled the source and surfaced as growing lag with no crash."
- **Fix and prevention:** scale the bottleneck operator's parallelism, fix the slow sink, or add buffering. Alert on backpressure and lag, not job-down.

### Lab 2 — JobManager as single point of failure
- **Break it:** run a session cluster without HA, then kill the JobManager container.
- **Symptoms:** the running job dies and doesn't come back on its own.
- **Hypothesis:** no HA means no standby JobManager and no durable job metadata to recover from.
- **Diagnose:** observe the job and its state are gone, not paused. Contrast with an HA run where a standby takes over and restores from the last checkpoint.
- **RCA sentence:** "The JobManager was a single point of failure with no HA, so its loss took the job and its coordination state with it, surfacing as a full pipeline outage from one container death."
- **Fix and prevention:** configure JobManager HA (Kubernetes HA services or ZooKeeper) with durable checkpoint storage. The most consequential Flink reliability lesson there is.

### Lab 3 — Checkpoint failure and timeout
- **Break it:** aggressive checkpoint interval and timeout, then induce backpressure or large state so checkpoints can't finish in time.
- **Symptoms:** checkpoints fail or time out. On a real failure, recovery replays from an old checkpoint and reprocesses.
- **Hypothesis:** checkpoint duration exceeds the timeout from backpressure or state size.
- **Diagnose:** Flink UI checkpoints tab. Watch duration, failed count, and alignment time. Rising duration points at backpressure or growing state.
- **RCA sentence:** "Checkpoint duration exceeded its timeout because backpressure stalled barrier alignment, which surfaced as repeated checkpoint failures and a lengthening recovery window."
- **Fix and prevention:** relax the interval, enable unaligned checkpoints, move large state to RocksDB, fix the backpressure root cause. Alert on checkpoint duration trend.

### Lab 4 — Stuck watermark and late data (the correctness lab)
- **Break it:** run a windowed event-time job reading from a multi-partition source, then stop producing to one partition so it goes idle. Separately, inject an event with an old timestamp after its window has closed.
- **Symptoms:** windowed output stops updating entirely even though data is still flowing on other partitions, with no error. The late event is silently dropped from its window.
- **Hypothesis:** the global watermark is the minimum across partitions, and one idle partition is holding it back so no window ever closes. The late event arrived past the watermark.
- **Diagnose:** Flink UI watermarks view per operator. A watermark stuck at an old timestamp while records keep flowing is the signature. Confirm the idle partition is the laggard.
- **RCA sentence:** "An idle source partition stalled the global watermark, so event-time windows never closed, which surfaced as dashboards that quietly stopped updating with no errors."
- **Fix and prevention:** idleness detection (`withIdleness`), tune allowed lateness, route late events to a side output for correction rather than dropping. Alert on watermark lag, not just consumer lag.

### Lab 5 — Unbounded state growth
- **Break it:** a keyed job accumulating state per key with no TTL and no windowing, fed ever-new keys.
- **Symptoms:** state size climbs steadily, checkpoints grow slower, memory pressure rises.
- **Hypothesis:** keyed state has no expiry, so it grows without bound.
- **Diagnose:** checkpoint size climbing over time in the Flink UI, correlated with key cardinality.
- **RCA sentence:** "Keyed state accumulated without TTL, so state size grew unbounded, which surfaced as ever-slower checkpoints and rising memory pressure."
- **Fix and prevention:** state TTL, windowing, or RocksDB for large state. Alert on state and checkpoint size trend. Treat state as a database with a retention policy.

### Lab 6 — TaskManager OOM
- **Break it:** a TaskManager with heap sized too small for its state and buffers (small `taskmanager.memory.process.size`), running a job with real keyed state under the heap-based state backend, or a job with large per-record objects.
- **Symptoms:** the TaskManager crashes or is killed, the job restarts and redistributes its tasks, and it can recur on the next TaskManager that inherits the same state shard.
- **Hypothesis:** state (or per-record working set) exceeds what the heap-based backend and configured memory can hold.
- **Diagnose:** TaskManager logs show a `java.lang.OutOfMemoryError` or the container is OOM-killed at the K8s/container level (the same cgroup mechanism as any other containerized process — see `roadmap/failure-labs/kubernetes/tidbits.md`). Flink UI shows the TaskManager disappear and tasks reschedule elsewhere.
- **RCA sentence:** "State and per-record working set exceeded the TaskManager's configured memory under the heap state backend, which surfaced as repeated OOM kills and task redistribution rather than a clean failure."
- **Fix and prevention:** move to the RocksDB state backend for large state (spills to disk instead of holding everything in heap), size `taskmanager.memory.process.size` and managed-memory fractions to the actual state size, or reduce per-key state footprint. Alert on TaskManager memory usage trend, not just crash count.

### Lab 7 — Job restart loops
- **Break it:** a job with a deterministic failure — a bad record that always throws on deserialization, a sink that's unreachable, a config error — combined with a restart strategy (e.g. fixed-delay) that keeps retrying.
- **Symptoms:** the job cycles through RESTARTING repeatedly in the Flink UI, never settling into RUNNING for long, until the restart strategy's attempt limit is exhausted and the job goes to FAILED.
- **Hypothesis:** the failure is deterministic (not transient), so every restart hits the same exception immediately — a restart strategy can't fix a bug, only ride out transient blips.
- **Diagnose:** Flink UI's exception history shows the *same* exception on every restart attempt. A transient issue would show varying or eventually-absent exceptions; a restart loop shows the identical stack trace each time.
- **RCA sentence:** "A deterministic failure in the pipeline was masked as transient by the restart strategy, which surfaced as a restart loop burning resources until the attempt limit exhausted and the job failed outright."
- **Fix and prevention:** fix the root cause (bad-record handling via a dead-letter side output, sink connectivity, config), not the restart strategy. Alert on restart *count* over a time window, not just job-down — a healthy job restarts rarely.

## Kafka labs

### Lab 1 — Consumer lag spike
- **Break it:** a consumer group processing normally, then either slow the consumer's per-record processing (a sleep, a slow downstream call) or force a rebalancing storm (repeatedly bounce consumers in the group).
- **Symptoms:** lag climbs and keeps climbing (slow-consumer case), or lag spikes in bursts correlated with group membership changes (rebalancing-storm case).
- **Hypothesis:** either the consumer's processing rate is below the production rate, or frequent rebalances are pausing the whole group repeatedly.
- **Diagnose:** consumer group lag over time (`kafka-consumer-groups.sh --describe` or the lag metric in your monitoring stack) — a steady climb points at a slow consumer; lag that jumps in sync with rebalance log lines points at rebalancing. Check consumer logs for repeated `JoinGroup`/`SyncGroup` activity to confirm the rebalancing case.
- **RCA sentence (slow-consumer case):** "Consumer processing throughput fell below production throughput, which surfaced as steadily climbing lag with no errors."
- **RCA sentence (rebalancing case):** "Frequent group membership changes triggered repeated rebalances, which paused the entire consumer group on every cycle and surfaced as bursty lag spikes uncorrelated with actual processing capacity."
- **Fix and prevention:** for the slow-consumer case — scale out consumers (up to the partition-count ceiling), speed up per-record processing, or increase partition count for more headroom. For rebalancing — raise `session.timeout.ms`/tune `max.poll.interval.ms` so slow-but-alive consumers aren't evicted, or move to a cooperative-sticky assignor to reduce reshuffling. Alert on lag trend, not a static threshold.

### Lab 2 — Under-replicated partitions
- **Break it:** kill a broker (or fill its disk) in a cluster where topics have replication factor > 1.
- **Symptoms:** the affected partitions' ISR shrinks; the cluster keeps serving but with reduced redundancy. If `min.insync.replicas` is breached, producers using `acks=all` start failing.
- **Hypothesis:** a broker is down or unable to keep up (disk full, overloaded), so its replicas fall out of the in-sync set.
- **Diagnose:** the under-replicated-partitions metric (JMX / your monitoring stack) goes above zero. `kafka-topics.sh --describe --under-replicated-partitions` names the exact partitions and shows which replicas dropped out of the ISR.
- **RCA sentence:** "A broker became unavailable, which dropped its replicas out of the in-sync set, which surfaced as under-replicated partitions and, if min.insync.replicas was breached, producer errors on top."
- **Fix and prevention:** restore or replace the failed broker so replicas catch back up; ensure enough disk headroom and broker capacity that one failure doesn't cascade. Alert on under-replicated-partition count directly — it's a leading indicator, not just a symptom.

### Lab 3 — Producer/consumer timeouts
- **Break it:** overload a broker (heavy produce/consume traffic, or induce disk I/O contention) or introduce network latency/packet loss between clients and brokers.
- **Symptoms:** producers see request timeouts or `NOT_ENOUGH_REPLICAS`/`REQUEST_TIMED_OUT`-style errors; consumers see fetch timeouts or fall behind sharply during the window.
- **Hypothesis:** the broker can't service requests within the client's configured timeout — either it's overloaded (queueing behind other requests, slow disk fsync) or the network path degraded.
- **Diagnose:** broker-side request queue/latency metrics (or `request-time` JMX metrics) show elevated queue and processing time during the incident window; client logs show which specific timeout fired (`request.timeout.ms` for producers, fetch timeout for consumers). Correlate with broker CPU/disk I/O and network metrics for the same window.
- **RCA sentence:** "Broker request handling slowed under load (or the network path degraded), which exceeded client-side timeouts, which surfaced as producer send failures and consumer fetch stalls without any single client-side bug."
- **Fix and prevention:** address the broker bottleneck (disk I/O, undersized cluster for the load, insufficient partitions to spread load) or the network issue directly; tune client timeouts to be resilient to expected tail latency without masking real problems. Alert on broker request latency percentiles, not just client-side error counts.

### Lab 4 — Topic partition skew (hot partitions)
- **Break it:** produce with a key that maps most records to one partition (e.g. a low-cardinality or poorly-distributed partition key), or use a topic with too few partitions for the actual traffic.
- **Symptoms:** one partition (and the broker leading it, and the consumer assigned it) runs hot — high throughput, possibly lagging — while other partitions and consumers sit comparatively idle.
- **Hypothesis:** the partitioning key doesn't distribute evenly, concentrating load onto one partition regardless of overall consumer/broker capacity.
- **Diagnose:** per-partition throughput/lag metrics show one partition far above its peers. If using a keyed producer, check key cardinality and distribution — a single dominant key value is the signature.
- **RCA sentence:** "An uneven partition key concentrated most traffic onto one partition, which capped effective throughput at what a single partition and its consumer could handle regardless of overall cluster capacity, surfacing as one hot partition and lagging consumer while the rest sat idle."
- **Fix and prevention:** choose a higher-cardinality, more evenly-distributed partition key; increase partition count to give hot keys more room to spread (with a better key); as a last resort, salt the key. Monitor per-partition throughput/lag skew, not just topic-level aggregates — an aggregate can look healthy while one partition is drowning.

## Spark labs

### Lab 1 — Data skew (the one that gets asked)
- **Break it:** a dataset where one key holds the vast majority of rows (95% share one id). Run a `groupBy` or join on it.
- **Symptoms:** the job nearly finishes, then one task hangs while every other task is done. Possibly an executor OOM on that one task.
- **Hypothesis:** uneven key distribution concentrating work on one partition.
- **Diagnose:** Spark UI, Stages tab. Look at task duration distribution within the slow stage. One task with massively higher input and shuffle read than its peers is the skew signature.
- **RCA sentence:** "A single hot key concentrated most of the shuffle data into one partition, which serialized the stage onto one task and starved parallelism, surfacing as a job that hangs near completion."
- **Fix and prevention:** salt the hot key, repartition, adaptive query execution skew handling, or broadcast join if one side is small. Monitor partition size skew.

### Lab 2 — Executor OOM
- **Break it:** small executor memory plus large per-task data (a wide aggregation, or the skew from Lab 1). Or collect a large dataset to the driver to OOM the driver instead.
- **Symptoms:** out-of-memory task failures, executors lost and restarted, job retries and slows.
- **Hypothesis:** working set per task exceeds executor memory, or a skewed partition is too big.
- **Diagnose:** Spark UI, Executors tab for failed and lost executors. Logs show the OOM. Separate driver OOM (from `collect` or large broadcast) from executor OOM (from task data size).
- **RCA sentence:** "Per-task working set exceeded executor heap because partition sizing did not match executor memory, which surfaced as repeated executor loss and stage retries."
- **Fix and prevention:** raise executor memory, raise shuffle partitions to shrink per-partition size, fix the skew, avoid `collect` on large results. The same K8s requests/limits reasoning, applied.

### Lab 3 — Shuffle spill
- **Break it:** a large shuffle (wide join or `groupBy`) with limited executor memory and a low partition count.
- **Symptoms:** the job runs but is slow, with heavy disk activity during the shuffle stage.
- **Hypothesis:** shuffle data exceeds memory and spills to disk, trading speed for survival.
- **Diagnose:** Spark UI shows spill (memory) and spill (disk) on the stage. Non-zero disk spill is the signal.
- **RCA sentence:** "Shuffle data exceeded available execution memory and spilled to disk, which surfaced as a slow stage dominated by disk IO rather than compute."
- **Fix and prevention:** more partitions, more executor memory, or reduce shuffle volume. Spill is survival, not failure, and the fix is sizing.

### Lab 4 — The small-files problem (the lake-side incident)
- **Break it:** a streaming or micro-batch write to local Parquet with a very short trigger interval, so it emits many tiny files. Then run a query over the output directory.
- **Symptoms:** the query is slow out of proportion to the data volume, and the slowness scales with file count, not row count. On a real object store, list operations would throttle.
- **Hypothesis:** millions of tiny files impose per-file overhead on the query planner and the storage layer.
- **Diagnose:** count the output files against the data size. A high file-count to data-size ratio is the signature. Query time tracks file count.
- **RCA sentence:** "A short write trigger produced many tiny files, so query and list overhead grew with file count rather than data size, which surfaced as queries far slower than the data volume warrants."
- **Fix and prevention:** compaction (Iceberg rewrite, Delta `OPTIMIZE`), longer write intervals, better partitioning. Recurring operational work on any streaming-to-lake platform, and a strong incident story to have ready.

---

## The compounding output

Same as the Kubernetes curriculum: every lab is a blog post and a portfolio piece. "I broke Flink watermarks on purpose and watched the dashboards silently stall" is exactly the kind of operational signal that shows you can reason about an unfamiliar system from first principles — which is what this whole topic is testing for.
