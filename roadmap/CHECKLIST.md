# SRE Study Checklist

> Check each item off only once you can explain it cold *and* connect it to a production scenario.
> This mirrors `roadmap/topics/` for deeper explanations and `roadmap/failure-labs/` for hands-on
> drills — use this file as the flat, scannable version; the topic files are where the mechanism
> behind each line actually lives.
>
> An interactive, checkbox-persisting version of this list lives in `roadmap/checklist.html`.

> **Cross-cutting habits — apply these to every answer, not just the item you're currently on:**
> - **RCA precision** — don't conflate adjacent layers ("app unreachable" vs "service unreachable"). State the precise causal chain.
> - **Fix-vs-prevention sequencing** — lead with the immediate mitigation, *then* prevention. Don't jump straight to long-term prevention.
> - **Reproduce the symptom first** — resist jumping to a hypothesis before confirming what's actually broken.
> - **Disambiguating signal** — for any symptom, name the *one* metric/file/command that distinguishes it from its look-alike failure mode.

---

## 1. Kubernetes

- [ ] Pod lifecycle: Pending → Running → Succeeded/Failed/Unknown
- [ ] Difference between Deployment, StatefulSet, DaemonSet, ReplicaSet — when to use each
- [ ] Namespaces — the multi-tenancy/organizational boundary for names, RBAC, quotas, and NetworkPolicy scope (distinct from Linux namespaces, which isolate kernel resources)
- [ ] Services: ClusterIP vs NodePort vs LoadBalancer vs ExternalName — and the kube-proxy/iptables data plane behind them
- [ ] How DNS works inside a cluster (CoreDNS, FQDN format: `svc.namespace.svc.cluster.local`) — and the OSI L3/L4/L7 mental model for walking a request through the stack
- [ ] Liveness vs readiness vs startup probes — what happens when each fails
- [ ] Resource requests vs limits — how the scheduler uses requests, how the kubelet uses limits
- [ ] QoS classes: Guaranteed, Burstable, BestEffort — eviction order
- [ ] ConfigMaps vs Secrets — how they're mounted (env vs volume)
- [ ] RBAC: Role vs ClusterRole, RoleBinding vs ClusterRoleBinding — and the ServiceAccounts they actually bind to
- [ ] NetworkPolicy: ingress vs egress, default deny patterns — and whether a block produces a timeout (drop) or a connection refused (reset)
- [ ] Ingress — L7 routing on host/path, and why a plain (L4) Service can't do this
- [ ] HPA vs VPA vs Cluster Autoscaler — HPA changes replica *count* from a metric, VPA changes a container's *requests/limits*, Cluster Autoscaler changes *node count* based on unschedulable Pending pods; know why HPA+VPA on the same metric fights itself
- [ ] PodDisruptionBudgets — the guardrail against voluntary disruption (node drains, upgrades) evicting too many replicas of the same workload at once
- [ ] Taints/tolerations and node/pod affinity — repelling vs attracting scheduling, and how each produces a different Pending reason
- [ ] PVC/PV binding, StorageClass, access modes (RWO, RWX, ROX)
- [ ] kubectl commands cold: `get`, `describe`, `logs`, `exec`, `apply`, `rollout status`, `get events`, `top`

## 1b. Virtualization — VMs vs Containers vs Kubernetes

- [ ] Virtual machines: hypervisor types — Type 1/bare-metal (KVM, ESXi) vs Type 2/hosted (VirtualBox, VMware Workstation); each VM gets its own full OS and kernel
- [ ] Containers vs VMs: containers share the host kernel (namespaces + cgroups — see the Docker internals note in `roadmap/topics/kubernetes-internals.md`), so they start in milliseconds but isolate less than a VM
- [ ] Docker Compose — declarative multi-container setups on a single host; the one-host precursor to what Kubernetes coordinates across many
- [ ] When to reach for which: a VM for full OS/kernel isolation or a different OS entirely; a container for fast, portable packaging on a shared kernel; Kubernetes when you need orchestration across many containers and hosts (scheduling, self-healing, scaling, service discovery) — not just "because containers"

## 2. Linux

- [ ] Basic navigation and file discovery: `ls`/`ls -la`, `cd`, `find` — the fundamentals underneath the internals below
- [ ] File descriptors: 0/1/2 (stdin/stdout/stderr), how `open()` creates an fd, fd table per process
- [ ] Inodes: what they store (metadata, not filename), hard links vs soft links, `stat` output
- [ ] Process lifecycle: fork/exec, zombie (parent hasn't `wait()`) vs orphan (parent died, init adopts)
- [ ] Signals: SIGTERM (graceful), SIGKILL (immediate, uncatchable), SIGCHLD, SIGHUP
- [ ] Process control and service management: `kill`/`kill -9` (sending the signals above from the shell), `systemctl` (start/stop/enable/status, reading a unit file)
- [ ] Memory: RSS vs VSZ, virtual address space, page cache, OOM killer
- [ ] `ps aux`, `top`, `lsof`, `netstat`/`ss`, `df`, `du`, `iostat`, `vmstat` — know what each column means
- [ ] Disk and storage: `df` (filesystem-level space) vs `du` (directory/file-level space), `mount` (what's attached where), `lsblk` (block devices) — and how LVM sits underneath them
- [ ] Linux file permissions: chmod, chown, sticky bit, setuid/setgid, ACLs (`getfacl`/`setfacl`) for permissions beyond the standard owner/group/other model
- [ ] Package management: `apt`/`dpkg` (Debian/Ubuntu) vs `yum`/`dnf`/`rpm` (RHEL/CentOS/Fedora) — install/upgrade/remove, dependency resolution
- [ ] `/proc` filesystem: `/proc/[pid]/fd`, `/proc/[pid]/maps`, `/proc/meminfo`, `/proc/cpuinfo`
- [ ] Cgroups and namespaces — what they isolate (pid, net, mnt, uts, ipc, user)
- [ ] grep, awk, sed, find, xargs, `tail -f` — piping, text processing, and following a live log
- [ ] Shell scripting fundamentals: variables, conditionals, loops, functions in a bash script — and `cron`/`crontab` syntax for scheduling them

## 2b. Operating Systems

- [ ] `ls -l` walked end-to-end at the syscall level (`opendir`/`readdir`/`stat`)
- [ ] Virtual memory: per-process address space, paging, demand paging, page faults (minor vs major), page cache
- [ ] Copy-on-write — what `fork()` actually shares vs copies, and when pages get duplicated
- [ ] Context switch — what's saved/restored; run queue; CFS at a high level
- [ ] **Load average ≠ CPU%** — counts runnable + uninterruptible-sleep tasks
- [ ] Threads vs processes — shared vs isolated memory; race conditions; locks/mutexes
- [ ] The GIL (Python, or any interpreted language with one) — what it serializes, implication for CPU-bound vs I/O-bound work
- [ ] IPC: pipes, shared memory, semaphores — when you'd pick each

## 2c. Networking

- [ ] TCP 3-way handshake + 4-way teardown; **why TIME_WAIT exists** (2×MSL)
- [ ] TCP states; **CLOSE_WAIT buildup = app not closing sockets** (fd leak); spot in `ss -tan`
- [ ] TCP vs UDP — when each; flow control (window) vs congestion control (slow start)
- [ ] **"What happens when you type a URL and hit Enter?"** — DNS → TCP → TLS → HTTP → render
- [ ] TLS handshake — asymmetric to exchange a symmetric key; certs; SNI
- [ ] DNS resolution path — stub → recursive → root → TLD → authoritative
- [ ] L4 vs L7 load balancing (ties to kube-proxy / Ingress)
- [ ] CIDR / subnets / private ranges / NAT — basics
- [ ] **connection refused (RST) vs timeout (drop) vs reset (mid-stream RST)** — name the signal for each
- [ ] Tools: `ss -tanp`, `dig`, `nslookup`, `curl -v`, `ping`, `tcpdump`, `traceroute`, `nc -zv` — what each reveals

## 3. Python Scripting

- [ ] Parse a log file, extract patterns, count frequencies — `re`, file I/O, `collections.Counter`
- [ ] Write a function that processes a list/dict and returns transformed output
- [ ] String compression/manipulation
- [ ] Check if a process is running, parse JSON/YAML output from kubectl
- [ ] Rate limiter (token bucket), LRU/TTL cache, retry with exponential backoff + jitter, top-K from a stream — see `roadmap/topics/scripting-patterns.md`

## 4. Docker

- [ ] Image vs container vs layer
- [ ] Dockerfile instructions: FROM, RUN, CMD vs ENTRYPOINT, COPY vs ADD, EXPOSE, ENV
- [ ] Multi-stage builds — why they reduce image size
- [ ] Docker networking: bridge, host, none, overlay
- [ ] Volumes: bind mounts vs named volumes vs tmpfs — what persists past a container's life vs what doesn't
- [ ] `docker ps`, `docker logs`, `docker exec -it`, `docker inspect`, `docker stats`
- [ ] Container security: running as non-root, read-only filesystem, dropping capabilities, seccomp
- [ ] Difference between CMD and ENTRYPOINT — classic trap
- [ ] Shell form vs exec form — why shell form breaks signal delivery to your app (PID 1 is the shell, not your process)

## 5. AWS

- [ ] IAM: roles vs users vs policies, least privilege, instance profiles, OIDC federation
- [ ] VPC: subnets (public vs private), route tables, security groups vs NACLs, NAT gateway
- [ ] EKS: how node groups work, how pods get IAM permissions (IRSA), VPC CNI IP density limits
- [ ] ECS vs EKS — when you'd pick each
- [ ] S3: bucket policies, versioning, lifecycle rules
- [ ] CloudWatch: metrics, logs, alarms — basic concepts
- [ ] EC2: instance types, auto-scaling groups, launch templates
- [ ] SQS (pull, at-least-once, visibility timeout) vs SNS (push, fan-out); DLQs + idempotency
- [ ] Lambda: event-driven, cold starts as a real latency/SLO consideration, not a footnote

## 6. Infrastructure as Code — Pulumi

- [ ] Stacks — isolated instances of a program (e.g. dev/staging/prod), each with its own state and config
- [ ] Resources & providers — cloud APIs (AWS/Azure/GCP/Kubernetes) wrapped as typed resources in a general-purpose language (TypeScript, Python, Go, …) instead of a declarative DSL
- [ ] Inputs/Outputs — the async `Output<T>` type for values only known after a resource is created, and how it propagates through dependent resources
- [ ] State backends — Pulumi Service (SaaS or self-hosted) vs self-managed backends (S3, GCS, Azure Blob) — same underlying need as Terraform remote state + locking, SaaS-hosted by default
- [ ] Component resources — composing multiple resources into a single reusable abstraction, the OOP-native equivalent of a Terraform module
- [ ] `pulumi preview` / `up` / `destroy` / `refresh` — the core CLI lifecycle, same conceptual shape as plan/apply/destroy
- [ ] Policy as code (CrossGuard) — enforce org policy against resources before they're created, written in the same language as the infra code
- [ ] Config and secrets — per-stack config values, encrypted secrets via a provider (passphrase or cloud KMS)
- [ ] The core tradeoff vs a declarative DSL (Terraform/CloudFormation): a real programming language gives you loops, conditionals, functions, tests, and an existing package ecosystem — more expressive, but easier to accidentally introduce non-idempotent or side-effect-laden code if you're not careful

## 7. System Design / Observability

- [ ] Three pillars: metrics, logs, traces — what each answers, and why they have different cost/retention profiles
- [ ] The cardinality trap in metric labels
- [ ] Pull (Prometheus) vs push (logs/traces) — and why each pillar uses the model it does
- [ ] Alert on symptoms (SLOs), not causes — alert hygiene levers (`for:`, grouping, severity routing)
- [ ] SLI / SLO / SLA / error budget — defined precisely; four golden signals (Latency, Traffic, Errors, Saturation)
- [ ] Burn-rate alerting — the mechanism for spending an error budget deliberately: page on fast burn, ticket on slow burn
- [ ] Monitoring the monitoring — dead-man's-switch, not sharing fate with what it observes
- [ ] Full worked example: `roadmap/topics/system-design-observability.md`

## 8. Data Platforms (Kafka / Flink / Spark)

- [ ] Kafka core concepts: topics, partitions (ordering is per-partition only, never cross-partition), offsets, brokers/leaders
- [ ] Kafka producers: `acks` (0/1/all), retries, batching (`batch.size`/`linger.ms`), idempotence (producer ID + sequence number dedup)
- [ ] Kafka consumers: consumer groups, partition assignment (partition count = hard ceiling on group parallelism), rebalancing and why it pauses the whole group
- [ ] Consumer lag: what it measures, and why the *trend* matters more than the static number
- [ ] Kafka retention: time-based, size-based, and compaction (`cleanup.policy=compact` — latest value per key, not a full history)
- [ ] Kafka replication: ISR, `min.insync.replicas`, under-replicated partitions as a leading indicator of data-loss risk
- [ ] Flink architecture: JobManager (coordinator, SPOF without HA), TaskManager (worker), slots, parallelism vs total slots
- [ ] Flink job lifecycle: CREATED → RUNNING → FINISHED/CANCELLED/FAILED, and what a RESTARTING loop in the exception history signals
- [ ] Streaming vs batch mode in Flink — same engine, different fault-tolerance and optimization assumptions
- [ ] Flink sources and sinks: Kafka source, S3/HDFS sink, JDBC sink — why the *sink's* capabilities gate the achievable delivery guarantee
- [ ] Flink: checkpointing vs savepoints, incremental vs full checkpoints, backpressure, state backends (heap vs RocksDB), keyed vs operator state
- [ ] Event-time vs processing-time; watermarks; the idle-partition watermark-stall trap; allowed lateness + side outputs
- [ ] Spark: driver/executor model, the shuffle, data skew (the one that gets asked), executor OOM, dynamic allocation
- [ ] Exactly-once mechanics: Flink checkpoint barriers + 2-phase-commit sinks; Kafka idempotent producer + transactions
- [ ] The lake vs the serving tier as two different sinks with two different reliability profiles; the small-files problem
- [ ] Golden signals for a streaming pipeline: consumer lag, end-to-end latency, throughput, checkpoint duration, error rate, freshness/completeness
- [ ] Full topic reference: `roadmap/topics/data-platform-streaming.md`; hands-on labs: `roadmap/failure-labs/data-platform.md`

## 9. Hands-On Failure Labs — Kubernetes

- [ ] OOMKilled pods vs CrashLoopBackOff — tell them apart, then tell genuine CPU saturation apart from CPU *throttling* (same symptom, opposite fix)
- [ ] Node pressure: fill disk via `hostPath`, watch the kubelet evict pods in QoS order (BestEffort → Burstable → Guaranteed)
- [ ] CoreDNS deletion: service-to-service failures that look like app errors, not DNS errors
- [ ] Service endpoint mismatch: a selector matching nothing, traffic silently failing
- [ ] NetworkPolicy blocking: timeout vs connection refused — the same disambiguation as the networking topic, reproduced by hand
- [ ] CNI failure: pods stuck in ContainerCreating
- [ ] etcd latency via disk I/O spike: watch the API server slow down and eventually time out
- [ ] API server overload: API priority and fairness, and why `kubectl` hangs even when workloads are fine
- [ ] CrashLoopBackOff from four different root causes that all look identical from the outside
- [ ] Liveness vs readiness vs startup probe misconfiguration: a too-aggressive liveness probe killing a healthy-but-slow-starting pod
- [ ] Pending pods from three distinct causes: oversized resource requests, nodeSelector mismatch, taint without toleration
- [ ] PVC stuck in Pending: nonexistent StorageClass vs `WaitForFirstConsumer` binding mode
- [ ] Pod stuck in Terminating: `preStop` hook + `terminationGracePeriodSeconds`
- [ ] Full lab curriculum: `roadmap/failure-labs/kubernetes.md`

## 10. Hands-On Failure Labs — Data Platforms

- [ ] Flink: backpressure — trace it upstream from the busy operator in the Flink UI
- [ ] Flink: JobManager as a single point of failure with no HA configured
- [ ] Flink: checkpoint failure and timeout under backpressure or large state
- [ ] Flink: stuck watermark and late data — the idle-partition trap, reproduced by hand
- [ ] Flink: unbounded keyed state growth with no TTL
- [ ] Flink: TaskManager OOM — heap-backend state outgrowing configured memory
- [ ] Flink: job restart loops — a deterministic failure masquerading as transient
- [ ] Kafka: consumer lag spike — slow consumer vs a rebalancing storm, and how to tell them apart
- [ ] Kafka: under-replicated partitions from a dead or overloaded broker
- [ ] Kafka: producer/consumer timeouts from broker overload or network degradation
- [ ] Kafka: topic partition skew — a hot partition from an uneven key, and why aggregate metrics hide it
- [ ] Spark: data skew — the one Spark topic that reliably gets asked about
- [ ] Spark: executor OOM vs driver OOM
- [ ] Spark: shuffle spill to disk
- [ ] Spark: the small-files problem on the lake side
- [ ] Full lab curriculum: `roadmap/failure-labs/data-platform.md`
