# Kubernetes Failure-Lab Tidbits

Supplementary reference notes for the failure lab in `roadmap/failure-labs/kubernetes.md` —
mechanism breakdowns and quick-reference tables that came out of actually running the labs
and digging one layer deeper than the main writeup.

---

## Memory, OOM & QoS

### What `malloc()` actually does — the full chain

```
process calls malloc() / mmap()          → only virtual memory reserved
process writes to the new memory          → page fault
kernel's page-fault handler runs          → tries to allocate a physical page
checks memory.current vs memory.max       → cgroup v2 (was usage/limit_in_bytes in v1)
if over limit → memory cgroup OOM killer  → scans tasks in that cgroup
                                           → picks victim by oom_score (+ oom_score_adj)
                                           → SIGKILL
```

Demand paging is why `malloc()` "succeeding" doesn't mean the memory is actually resident yet
— see `roadmap/topics/linux-and-networking.md` for the general mechanism.

### QoS classes — exact definitions

| Class | Exact definition |
|---|---|
| **Guaranteed** | `requests == limits`, for **both CPU and memory**, for **every container** in the pod |
| **Burstable** | Anything in between — at least one container has a request or limit set, but doesn't satisfy Guaranteed |
| **BestEffort** | **No** requests or limits set, on any container |

A common trap: Burstable is "at least one container has a request *or* limit defined" — but
Guaranteed requires requests and limits to be **equal**, for **both** CPU and memory. If memory
is `requests: 100Mi, limits: 100Mi` but CPU is `requests: 100m, limits: 200m`, that pod is
**Burstable**, not Guaranteed — one mismatched resource is enough to disqualify it.

### The OOM-score mechanism — how K8s nudges the kernel

K8s writes `oom_score_adj` to `/proc/<pid>/oom_score_adj` based on QoS class:
- BestEffort: **1000** (most killable)
- Burstable: scaled by `1000 - (1000 * memory_request / node_capacity)` — smaller request = higher score
- Guaranteed: **-997** (almost untouchable)

The kernel adds `oom_score_adj` to the raw `oom_score` (based on RSS) when picking a victim.
This is how K8s influences a Linux kernel decision without overriding the kernel — it nudges
it via a standard interface. A nice example of "beautiful design point worth knowing."

### Eviction order — what actually gets ranked

When the kubelet evicts under node pressure, the ranking is:
1. **Does the pod's usage of the pressured resource exceed its request?** (boolean — exceeders are killed first)
2. **Pod Priority** (`priorityClassName` / `.spec.priority`)
3. **Magnitude of usage above request**

QoS class isn't the sort key — it's a **consequence** of how requests are set, which is why it
correlates with the order:
- **BestEffort** sets no requests → request is effectively 0 → any usage "exceeds request" → always sorts into the kill-first bucket.
- **Burstable** has some requests → exceeds only by the overage → middle.
- **Guaranteed** requests == limits → usage is within request → "does not exceed" → kill-last bucket.

So the precise mechanism is: *eviction is ranked by usage-over-request, then Priority, then
usage magnitude. QoS BestEffort→Burstable→Guaranteed is the emergent order because requests are
what define both QoS and the over-request ranking.*

**The trap:** Priority beats QoS. A high-priority BestEffort pod can outlive a low-priority
Guaranteed one — setting `priorityClassName: system-cluster-critical` on a BestEffort pod means
it will *not* die first, QoS class notwithstanding.

### OOM fixes — the tradeoffs

| Approach | Tradeoff |
|---|---|
| **Raise the limit** | Fast unblock. Hides leaks. Wastes RAM if it's a startup spike. |
| **Optimize the app** — fix the leak, reduce footprint | Right fix. Slow. Sometimes impossible (3rd-party image). |
| **VPA (Vertical Pod Autoscaler)** | Auto-tunes limits from observed usage. Bad for spiky workloads; restarts pods to apply. |
| **Startup probe + initial higher request** | Right if it's a JVM-style warmup hump. |
| **Tune the runtime, not the K8s limit** — e.g. JVM `-XX:MaxRAMPercentage=75` so the heap respects the cgroup | Critical for JVM apps. Pre-Java 10 JVMs were cgroup-blind and would size the heap to *host* memory — still a common production bug. |

---

## Priority

### Reserved PriorityClass values

| Name | Value | Use |
|---|---|---|
| `system-cluster-critical` | 2000000000 | Cluster-critical add-ons (e.g. CoreDNS, metrics-server) |
| `system-node-critical` | 2000001000 | Highest — node-critical (e.g. kube-proxy, CNI). Last thing the kubelet ever evicts. |

Values > 1,000,000,000 are **reserved** for these system classes — you can't assign them to your
own pods. If no `priorityClassName` is set and there's no `globalDefault`, priority is **0**.

### PriorityClass vs priorityClassName vs spec.priority — three different objects

| Attribute | Scope | Who writes it | What it is |
|---|---|---|---|
| `PriorityClass` | Cluster-scoped object | You/admin, once | The **definition** — a named catalog entry mapping a name → integer value |
| `pod.spec.priorityClassName` | Field on the pod | You, in the manifest | A **string reference** pointing at a PriorityClass by name |
| `pod.spec.priority` | Field on the pod | The system, automatically | The **resolved integer**, copied in at admission time |

The flow at pod creation:

```
You write:  priorityClassName: "high-prio"
              │
              ▼  (Priority admission controller looks up the PriorityClass named "high-prio")
PriorityClass "high-prio" { value: 1000000 }
              │
              ▼  (copies the integer onto the pod)
Pod ends up with:  spec.priority: 1000000   ← immutable, this is what scheduler + kubelet compare
```

**Analogy:** PriorityClass is the HR pay-grade table ("Senior = ₹X"). `priorityClassName` is you
writing "Senior" on your offer form. `spec.priority` is the actual number stamped onto your
payroll record. Payroll (the scheduler) pays off the **number**, never the label.

**Why copy the value into `spec.priority` instead of just looking up the class every time?**
1. **Immutability / decoupling** — once admitted, the pod's priority is frozen. If an admin later edits `high-prio` to a different value or deletes the PriorityClass entirely, your running pod keeps the priority it was born with. No retroactive surprises during an eviction storm.
2. **Performance** — the scheduler and eviction manager compare a plain int32 on the pod; no object lookup/join per decision across thousands of pods.
3. **Source-of-truth clarity** — `spec.priority` is the single authoritative value the kubelet reads in `rankDiskPressure`/`rankMemoryPressure`. `priorityClassName` is just the human-friendly pointer that produced it.

So: one object (the definition), one reference (your intent), one resolved integer (the runtime
fact). You set the middle one; the system derives the last one from the first.

---

## CPU throttling

### Reading `cpu.stat` correctly

- **`nr_throttled` / `nr_periods`** answers *"of the moments I wanted CPU, how often was I capped?"* → 100% means every single period got throttled. Brutal.
- **`throttled_usec` vs wall-clock** answers *"what fraction of real time was lost to throttling?"* → smaller, because some wall-clock time it wasn't asking for CPU at all.

These are two different questions with two different denominators — don't conflate "capped
every time I asked" with "capped for most of the wall-clock window."

### Getting to the cgroup file from outside the pod

```bash
POD=$(kubectl get pod -l app=report-worker -o jsonpath='{.items[0].metadata.name}')
kubectl exec "$POD" -- cat /sys/fs/cgroup/cpu.stat
```

Or, skip the variable entirely if there's exactly one pod behind the workload:

```bash
kubectl exec deploy/report-worker -- cat /sys/fs/cgroup/cpu.stat
```

That's the whole trick: `kubectl exec` into the pod, `cat` the cgroup's `cpu.stat`. The fields
that matter are `nr_periods`, `nr_throttled`, and `throttled_usec`.

---

## Scheduling signals

### What `disk-pressure:NoSchedule` actually means

It's tempting to read a `NoSchedule` taint as "the node literally can't carve out a filesystem
for a new pod." That's not it — the kubelet sets `disk-pressure:NoSchedule` as a **protective
backpressure signal**: *"I'm already reclaiming disk, don't pile more consumers on me."* It's a
deliberate guard, not a physical impossibility.

---

## OSI layers, applied to Kubernetes

### The 7 layers, what each does, and how to inspect it

In practice you'll never use all 7 — real conversation collapses to L2/L3/L4/L7. L5/L6 get
squished into L7, and TLS lives in a fuzzy spot between L4 and L7.

| # | Name | What it does | Address type | Tool to inspect |
|---|---|---|---|---|
| L1 | Physical | Bits on a medium | None | Link lights, `ethtool` |
| L2 | Data Link | Frames between directly-connected devices on the same network segment | MAC address | `arp`, `ip neigh`, `tcpdump -e` |
| L3 | Network | Packets between any two hosts across networks | IP address | `ip route`, `traceroute`, `ping` |
| L4 | Transport | End-to-end byte streams between processes | port | `ss`, `netstat`, `nc` |
| L5/6 | Session/Presentation | (Rarely discussed) session state, encoding, encryption | — | (TLS lives here) |
| L7 | Application | What the user/app actually does | hostname, URL | `curl`, `dig`, wireshark |

### Tool-per-scenario decision table

Strip layers, one at a time, from the bottom up:

| Symptom | Best tool | Why |
|---|---|---|
| "Can the name resolve?" | `nslookup` / `dig` | Pure L7 DNS — strips all transport |
| "Can I reach the port?" | `nc -zv host port` | Pure L4 TCP — clean signal, no HTTP/TLS noise |
| "Does the app respond?" | `curl -v` (or `curl -w`) | Full L3→L4→L7. `-w` gives per-stage timing |
| "Refused vs timeout?" | `nc -zv` | Refused = host up, port closed (RST). Timeout = packet dropped silently (NetworkPolicy, firewall) |
| "What hops is it taking?" | `traceroute` / `mtr` | L3 routing. Rare in K8s, common in cross-VPC |
| "Is *my own* process listening?" | `ss -tlnp` (modern) / `netstat -tlnp` (old) | Local L4 socket state |
| "Where exactly is the packet dropped?" | `tcpdump` / `tshark` | Every layer, ground truth |
| "Is the pod IP routable?" | `ping <pod-IP>` (usually works) | L3 ICMP — works for pod IPs in most CNIs, not for ClusterIPs |

**Default escalation order** when something is unreachable in K8s:
`nslookup → nc -zv → curl -v → tcpdump` (if still mysterious).

### Translating OSI layers onto a real request: laptop→google.com vs pod→Service

| Layer | Laptop → google.com | Client pod → web-svc |
|---|---|---|
| L1 | WiFi radio waves, ethernet copper, fiber | Node's physical NIC, plus virtual veth pairs the CNI created for each pod |
| L2 | Ethernet frames on your LAN; ARP to find the router's MAC | Same Ethernet, but on a **virtual bridge** (Docker bridge / CNI bridge) inside the node, or encapsulated in a VXLAN/IP-in-IP tunnel if the target pod is on a different node |
| L3 | Your laptop IP → public IP via NAT at your router → routed across many ISPs/backbones to Google's edge | Two kinds of IPs coexist: **Pod IPs** (real, routable via the CNI's overlay/BGP, e.g. `10.244.0.x`) and **Service ClusterIPs** (virtual, exist only as iptables/IPVS rules — `10.96.x.x`). No interface is configured with a ClusterIP anywhere; it's a fiction maintained by kube-proxy |
| K8s-specific NAT | (doesn't exist outside) — closest analog is CGNAT at ISPs | **kube-proxy** maintains iptables/IPVS rules that DNAT `ClusterIP:port` → one randomly-chosen pod IP from the Endpoints list. This is the step that fails when Endpoints are empty |
| L4 | TCP handshake to Google's load balancer on port 443 | TCP handshake — but to the *DNAT'd* pod IP, not the ClusterIP. The client thinks it's talking to `10.96.57.45`; the actual packets flow to `10.244.0.x` |
| TLS (between L4 and L7) | Cert exchange, key agreement, encrypted channel | Often **mTLS** if there's a service mesh (Istio, Linkerd) — adds another verification layer |
| L7 DNS | Your laptop → `8.8.8.8` or your ISP's DNS → recursive resolution out to Google's authoritative nameservers | Your pod → **CoreDNS** (running as a Deployment in `kube-system`, ClusterIP `10.96.0.10`) → resolves `web-svc.lab-svc.svc.cluster.local` to a ClusterIP |
| L7 HTTP | HTTPS GET to google.com | HTTP GET to `web-svc:80` |

### Where a service-to-service call actually breaks, layer by layer

| Layer | What happens | Where it can break |
|---|---|---|
| L7 DNS | `web-svc` → cluster DNS query to CoreDNS, gets back a ClusterIP (e.g. `10.96.x.x`) | NXDOMAIN, CoreDNS down, wrong search domain |
| L3 | Packet leaves client pod with dst = ClusterIP | Routing, CNI broken |
| L3/L4 NAT | kube-proxy (iptables/IPVS) DNATs `ClusterIP:80` → one of the pod IPs from the **Endpoints** list | **Empty endpoints → no DNAT → no route → connection drops** — the most common silent failure |
| L4 TCP | SYN → SYN-ACK → ACK handshake to the chosen pod IP | NetworkPolicy block, pod not listening, port mismatch |
| L7 HTTP | GET request, server responds 200 | App-level bug, wrong path, wrong vhost |

### Precise layer mapping (avoiding a common mislabel)

The kube-proxy NAT step is the one genuinely K8s-specific addition to the classic OSI model —
it doesn't map cleanly onto any single layer, which is exactly why it's worth calling out on
its own rather than mislabeling it as "L3" or "L4":

| Loosely-named "layer" | Actual OSI layer | What it really is |
|---|---|---|
| "L7 DNS" | L7 (Application) | DNS over UDP/TCP |
| "L3 (packet leaves pod)" | L3 (Network) | IP routing decision |
| "L3/L4 NAT (kube-proxy)" | **Sits between L3 and L4** — it's iptables NAT acting on L3 dst-IP and L4 dst-port. K8s-specific | iptables `KUBE-SERVICES` chain matches `dst=ClusterIP:port` and DNATs. If endpoints are empty → `KUBE-MARK-DROP` or `REJECT` rule fires |
| "L4 TCP" | L4 (Transport) | TCP three-way handshake |
| "L7 HTTP" | L7 (Application) | HTTP request/response |
