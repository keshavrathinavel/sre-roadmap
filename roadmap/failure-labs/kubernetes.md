# The Failure Curriculum

> Deeper mechanism notes that came out of running these labs (OOM/QoS/priority internals, CPU
> throttling stats, OSI layers applied to K8s networking) live in `kubernetes/tidbits.md`.

## Category 1 — Resource Exhaustion

These are the most common real-world cluster failures and the most misdiagnosed.

### OOMKilled Pods
Deploy a pod with a memory limit lower than it needs. Watch it get OOMKilled.

Learn to distinguish **OOMKilled** from **CrashLoopBackOff** in:

```bash
kubectl describe
```

Understand:
- Why the container restarts
- Why it stays dead

### CPU Throttling
Deploy something with a **very low CPU limit**.

It won't crash but it will be **mysteriously slow**.

Learn to spot:
- CPU throttling in metrics
- actual high CPU usage

They look similar externally but require **completely different fixes**.

> Lab manifest: `kubernetes/cpu-throttle.yaml` (report-worker, 100m limit, logs per-cycle latency).
> The lie of `kubectl top`: it shows *allowed* usage (pinned at the limit), never *demanded* usage. The proof of throttling lives in the cgroup, not in metrics-server:
> `kubectl exec deploy/report-worker -- cat /sys/fs/cgroup/cpu.stat`
> Read `nr_throttled / nr_periods` (how often capped when it wanted CPU) and `throttled_usec` (total wall-time locked out). CFS throttling is **silent** — it never hits `dmesg` (a `dmesg` throttle hit means *thermal*, a different beast). The actor is the kernel CFS scheduler, not K8s; K8s only writes `cpu.cfs_quota_us`/`cpu.cfs_period_us`.
> Fix order: (1) immediate — `kubectl set resources deploy/report-worker --limits=cpu=1` (rolling restart); (2) prevention — for predictable internal workloads, set a CPU *request* and **drop the CPU limit** (Tim Hockin "CPU limits considered harmful"); keep it Burstable, never BestEffort.

#### Twin case — genuine CPU saturation (TODO: build the lab)
Externally **identical** to throttling: service is slow, CPU pegged. But the cause and fix are opposite.

Reproduce: same workload pattern but with a busy-spin / runaway hot path (infinite loop, O(n²) blowup, catastrophic regex backtracking, GC death-spiral) and **no CPU limit** (or limit well above demand) — let it eat a whole core legitimately.

The single discriminator is **`nr_throttled` in `cpu.stat`**:

| | Throttling (the lab above) | Twin — genuine saturation |
|---|---|---|
| `top` | pegged at limit | pegged (whole core if unlimited) |
| `cpu.stat` `nr_throttled` | climbing fast | **≈ 0** |
| Root cause | starved — demand > quota | the *work itself* is the problem |
| "Raise the limit" | **fixes it** | **wrong** — burns more CPU, starves neighbours, or no-op |
| Real fix | give it the CPU | **profile & fix the code / scale out** |

Same symptom, opposite fix. `cpu.stat` is the one file that tells them apart.

> Not the same as **lock contention / thread-pool exhaustion** — that presents as slow with **LOW** CPU (threads blocked, not burning) + high context-switch counts. A useful *third* bucket; different signature.

### Node Pressure
Fill a node's disk by writing junk to a `hostPath` volume.

Watch the kubelet **evict pods**.

Eviction order:

1. **BestEffort**
2. **Burstable**
3. **Guaranteed**

Understand why **QoS classes matter**.

**What you learn**
- How the Kubernetes resource model actually works
- Why limits and requests are different
- How the kubelet makes eviction decisions
- Understand how to diagnose between a memory leak (RSS climbs over hours) an an undersized limit (RSS hits the ceiling on startup) - can even check Prometheus for container_memory_working_set_bytes historically.


---

## Category 2 — Networking Failures

These are the **hardest to diagnose** and show up constantly in real on-call rotations.

### DNS Resolution Breakdown
Delete the **CoreDNS pods** and watch service-to-service communication fail in ways that look like application errors, not DNS errors.

Trace the problem using:

```bash
kubectl exec
nslookup
```

### Service Endpoint Mismatch
Create a Service with a selector that **doesn't match any pod labels**.

Traffic silently fails.

Use:

```bash
kubectl get endpoints
```

### NetworkPolicy Blocking
Apply a **NetworkPolicy** that blocks traffic between two services.

The connection will **time out rather than refuse**.

Learn the difference between:
- **Timeout**
- **Connection refused**

### CNI Failure
Forcefully kill the **CNI plugin daemonset pods**.

New pods get stuck in:

```
ContainerCreating
```

**What you learn**
- The full packet path from **pod A → pod B**
- How DNS works inside a cluster
- Why NetworkPolicy timeouts differ from refusals

---

## Category 3 — Control Plane Stress

### etcd Latency
Run `stress-ng` on your control plane node to spike disk I/O.

Watch API server responses slow down and eventually timeout.

Learn what **etcd slow apply warnings** look like in logs and why disk speed is a critical dependency.

### API Server Overload
Hammer the API server with:

```bash
kubectl get pods
```

Run it from ~20 concurrent processes.

Watch legitimate operations queue.

Learn about:
- **API priority and fairness**
- Why kubectl operations fail during incidents even when workloads are fine

**What you learn**

The control plane is **not magic**. It has its own resource constraints and subtle failure modes.

---

## Category 4 — Application Failure Patterns

### CrashLoopBackOff Diagnosis
Deploy pods that fail in different ways:

- Missing env var
- Missing ConfigMap
- Bad command
- OOM

They all show **CrashLoopBackOff** but for completely different reasons.

Practice diagnosing from logs alone because in production you often can't exec into crashed containers.

### Liveness vs Readiness Probe Confusion
Deploy something where the **liveness probe is too aggressive**.

Kubernetes will kill a pod that is actually healthy but slow to start.

Fix it with:

```
startupProbe
```

### Pending Pods
Create pods that cannot be scheduled:

- Request more CPU than any node has
- Use a `nodeSelector` that matches nothing
- Use a taint without a toleration

Each results in **Pending** but for different reasons.

Learn to read **scheduler events**.

**What you learn**

```bash
kubectl describe pod
```

The **events section** tells you what the scheduler and kubelet actually decided and why.

---

## Category 5 — Stateful & Storage Failures

### PVC Stuck in Pending
Create a PVC with a **StorageClass that doesn't exist**.

Trace the issue.

Then create one with **WaitForFirstConsumer** binding mode and observe why it stays Pending until a pod claims it.

### Pod Stuck in Terminating
Give a pod a `preStop` hook that sleeps for **120 seconds**, then delete it.

Watch it hang.

Learn about:

- `terminationGracePeriodSeconds`
- Force deleting safely vs unsafely

**What you learn**

Storage failures often cause the **nastiest cluster hangs**, and the termination lifecycle is poorly understood.

---

# Diagnosis Framework for Every Failure

1. **Symptoms first**  
   What does it look like externally? What would alerts or users report?

2. **Hypothesis**  
   Guess the cause *before* checking anything.

3. **Describe**
   ```bash
   kubectl describe
   ```

4. **Logs**
   ```bash
   kubectl logs
   kubectl logs --previous
   ```

5. **Metrics**
   What does this look like in **Prometheus/Grafana**?

6. **Root cause**
   Write one sentence:

   > "This happened because X, which caused Y, which surfaced as Z"

7. **Fix + prevention**
   - Immediate fix
   - Long‑term prevention

Writing the **RCA sentence** separates engineers who *fix things* from engineers who *understand things*.

---

# Tools to Install Alongside Your Cluster

- **k9s** — terminal UI for watching failures in real time
- **stern** — tail logs from multiple pods simultaneously
- **Prometheus + Grafana** — observe every failure through metrics
- **Litmus Chaos** — structured chaos experiments with hypotheses

---

# The Honest Time Investment

One failure category per week → **5 weeks of extremely high‑quality learning**.

Outputs compound:

- Writeups → blog posts
- Blog posts → portfolio
- Portfolio → callbacks from international companies

---

### Questions for Clarification
1. What changed recently? — deployments, node upgrades, Terraform applies, cert rotations, config changes
2. When did this start? — exact time, correlate with change history
3. Has this ever happened before? — recurring issues have patterns
4. What's the blast radius? — is it one pod, one service, one namespace, the whole cluster?
5. Any upstream/downstream services affected? — payments-api failing might be symptomatic of something deeper
6. Who made the last change and what was it? — check your CI/CD pipeline, ArgoCD sync history, AWS CloudTrail

## Learnings 
`nc -zv host port` — raw TCP connectivity
`pg_isready` — Postgres-specific
VPC Reachability Analyzer — AWS path analysis
`traceroute / mtr` — routing issues
`kubectl exec + any of the above` — from inside the pod's network namespace

---

### Example Problems Solved

1. A pod is stuck in CrashLoopBackOff and the logs aren't obvious - did one problem where the diagnosis was misconfigured security groups
2. A node goes NotReady and workloads start evicting in unexpected ways
3. A deployment rollout silently fails — new pods come up but traffic still hits old pods
4. DNS resolution is broken inside the cluster for one specific service
