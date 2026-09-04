# Kubernetes Internals — Deep Reference

> Format per topic: first-principles *why* → mechanics → production failure modes → "3 things to remember."
> Pairs with `roadmap/failure-labs/kubernetes.md` — that's the hands-on curriculum; this is the mental model
> you're building while you break things.

---

## Pod lifecycle: Pending → Running → Succeeded/Failed/Unknown

**Core idea:** `status.phase` is a *coarse rollup* the kubelet reports to the API server. The debuggable truth lives one layer below it.

### The 5 phases (`status.phase`)
| Phase | Meaning |
|-------|---------|
| **Pending** | Accepted by API server, but ≥1 container not running. Either not scheduled yet, *or* scheduled but images pulling / volumes mounting. |
| **Running** | Bound to a node, all containers created, **at least one** running/starting/restarting. |
| **Succeeded** | All containers exited 0, will **not** restart. Terminal. |
| **Failed** | All containers terminated, **at least one** failed (non-zero / killed). Terminal. |
| **Unknown** | Control plane lost contact with the node (kubelet/node down). State unknowable. |

### Mental model
Scheduler decides *where*; kubelet decides *what's actually happening*; phase is the rolled-up postcard sent to the API server. `Unknown` isn't a state the pod is *in* — it's a state of **ignorance** (no kubelet heartbeat within `node-monitor-grace-period` ~40s). **A wave of pods → Unknown at once = node/network partition, not an app bug.** Don't read app logs.

### The layer that actually matters for debugging
Phase is too coarse. Real signal:
- **Container states:** `Waiting` (+`reason`), `Running`, `Terminated` (+`reason`/`exitCode`).
- **Pod conditions:** `PodScheduled`, `Initialized`, `ContainersReady`, `Ready`.

`CrashLoopBackOff`, `ImagePullBackOff`, `ContainerCreating` are **not phases** — they're `Waiting` *reasons*. A crash-looping pod is still phase **Running** (kubelet is actively restarting it; backoff 10s→20s→40s… capped 5 min).

**Pending splits into two completely different failure classes** (the disambiguating-signal habit):
- **Unschedulable** — `PodScheduled=false`, Events say "0/N nodes available: insufficient cpu / affinity / taints" → *scheduler* problem.
- **Scheduled but stuck** — `ContainerCreating` → *kubelet* problem (image pull / volume mount / CNI IP).

**Init containers:** run to completion in order before app containers. Pod sits **Pending**, `Initialized=false`, shows `Init:0/2`. "App won't start, logs empty" → you're reading the app container; read the init container: `kubectl logs <pod> -c <init-container>`.

### 3 to remember
1. Phase = coarse kubelet rollup; debug via container states + pod conditions. `describe` is where you read it.
2. Pending = two distinct classes (unschedulable vs scheduled-but-not-ready); `PodScheduled` condition disambiguates.
3. Unknown = lost node contact, not a pod fault. CrashLoopBackOff is a *Waiting reason* under a Running phase.

---

## The other state-descriptor families in K8s

Four families:

**Family 1 — `phase` (closed enums, being phased out).** Only some objects have one:
- Pod: Pending/Running/Succeeded/Failed/Unknown
- PersistentVolume: Available/Bound/Released/Failed
- PersistentVolumeClaim: Pending/Bound/Lost
- Namespace: Active/Terminating

A phase is a single scalar — can't express concurrent/partial truth. K8s deliberately moved away from it (Node used to have a phase; now uses conditions).

**Family 2 — `conditions` (the dominant, extensible pattern).** On almost everything (Pod, Node, Deployment, Job, PVC, CRDs). A condition = `{type, status, reason, message, lastTransitionTime}`.
- **`status` is tri-state: True / False / Unknown** (not boolean — "we don't know" is first-class).
- **`type` set is open-ended** — anyone (incl. CRDs) can add types without breaking the API. That's the advantage over phase.
- Examples: Pod `PodScheduled/Initialized/ContainersReady/Ready`; Node `Ready/MemoryPressure/DiskPressure/PIDPressure/NetworkUnavailable`; Deployment `Available/Progressing/ReplicaFailure`; Job `Complete/Failed`.

**Family 3 — other genuine closed enums (scattered):** container state (Waiting/Running/Terminated), QoS (Guaranteed/Burstable/BestEffort), restartPolicy (Always/OnFailure/Never), taint effects (NoSchedule/PreferNoSchedule/NoExecute), PV access modes (RWO/ROX/RWX/RWOP), Service type, imagePullPolicy.

**Family 4 — the trap: `reason` strings are NOT enums.** `CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`, `ErrImagePull`, `Evicted`, `ContainerCreating` are **free-form strings** set by kubelet/controllers by convention — no schema constrains them. Also: **`Terminating` and `Completed` are not stored states** — `kubectl` *synthesizes* them (Terminating = presence of `.metadata.deletionTimestamp`+finalizers; Completed = display for phase Succeeded). Much of `kubectl get` output is derived presentation.

---

## Deployment vs StatefulSet vs DaemonSet vs ReplicaSet

**Core question to derive the answer:** *"What identity and ordering guarantees do my replicas need?"* — not "is it a database."

### The layering (the key insight)
```
Deployment ──manages──> ReplicaSet ──manages──> Pods
```
- **ReplicaSet** = primitive: "keep N pods matching this selector alive." No versions, no rollout. Pods are interchangeable (random name/IP). Cattle.
- **Deployment** = adds **versioned rollout/rollback** on top. On template change it creates a *new* RS, scales it up while scaling old down (rolling update); keeps old RS at 0 for rollback. **Use Deployment, almost never a bare ReplicaSet.**

### The four by the question they answer
| Controller | Guarantee | Question |
|-----------|-----------|----------|
| ReplicaSet | N identical interchangeable pods | "keep this many alive" (primitive) |
| Deployment | RS + versioned rollout/rollback | "stateless app I deploy & update" |
| StatefulSet | stable identity + ordering + stable storage | "each replica is distinct & must stay distinct" |
| DaemonSet | one pod per matching node | "run this on every node" |

### StatefulSet — what "stateful" actually buys (3 guarantees a Deployment can't give)
1. **Stable network identity** — ordinal names `web-0/1/2`; stable DNS via a **headless Service** (`web-0.svc.ns.svc.cluster.local`). `web-0` is always `web-0`.
2. **Stable storage** — each pod gets its **own** PVC via `volumeClaimTemplates` (`data-web-0`…); reattaches the same volume on reschedule.
3. **Ordered ops** — up `0→1→2` (each waits for prev Ready); scale-down & rolling update in **reverse** `2→1→0`.

*Why databases need it:* a primary/replica or sharded cluster can't have interchangeable pods or shared storage. **Cost:** slower, more fragile — a stuck pod blocks the ordered sequence. Don't use unless you need identity/ordering/per-replica storage.

### DaemonSet — one pod per node
No replica count; replica = node count implicitly. Add node → pod appears; drain → pod gone. Use for **node-local agents**: CNI, kube-proxy, log collectors (Fluent Bit), node-exporter, CSI node plugins. A log shipper reading each host's `/var/log` **must** be a DaemonSet. Often needs **tolerations** to land on tainted/control-plane nodes.

### Decision tree (say out loud)
1. Node-local agent on every node? → **DaemonSet**
2. Need stable identity / ordering / per-replica storage? → **StatefulSet**
3. Stateless, interchangeable, needs rollout/rollback? → **Deployment**
4. Bare ReplicaSet? → ~never.
- Batch: run-to-completion → **Job**; scheduled batch (nightly backup) → **CronJob**.

### 3 to remember
1. It's a layering: RS primitive → Deployment adds rollout/rollback → use Deployment, not bare RS.
2. StatefulSet = identity + ordering + per-replica PVC; that's the *why* behind "databases," and it costs operational speed.
3. DaemonSet = one pod per node for node-local agents; driver is "must it be on every node," often needs tolerations.

---

## Autoscaling and scheduling constraints

**HPA vs VPA vs Cluster Autoscaler — three different axes, easy to conflate.**
- **HPA (Horizontal Pod Autoscaler)** changes *replica count* based on a metric (CPU%, memory, or a custom/external metric) — more pods, not bigger pods.
- **VPA (Vertical Pod Autoscaler)** changes a *container's requests/limits* based on observed usage — same number of pods, resized. VPA currently requires evicting and recreating a pod to apply a new size, which is itself a disruption.
- **Cluster Autoscaler** (or Karpenter) changes *node count* — it watches for Pending pods that are unschedulable due to insufficient node capacity and adds nodes; it removes nodes once they're underutilized and their pods can be rescheduled elsewhere. This is the layer below HPA/VPA: they only ever resize or multiply pods within whatever node capacity already exists — something still has to make more capacity exist.
- **Don't run HPA and VPA against the same metric on the same workload** — VPA resizing a pod changes the very CPU% HPA is scaling on, and the two fight each other. If you need both, scale horizontally on one signal and vertically on a different, unrelated one.

**PodDisruptionBudgets (PDBs)** protect against *voluntary* disruption — a node drain, a cluster upgrade, `kubectl drain` — evicting too many replicas of the same workload at once. A PDB declares `minAvailable` or `maxUnavailable`; the eviction API respects it and will refuse an eviction that would violate the budget, forcing the drain to wait or work around it. This is a *voluntary*-disruption guardrail only — it does nothing for involuntary disruption (a node dying outright, an OOM kill).

**Taints/tolerations vs node/pod affinity — repelling vs attracting, and they produce different Pending signatures.**
- **Taints** (on a node) + **tolerations** (on a pod) are a *repel* mechanism: a pod without a matching toleration won't schedule onto a tainted node. `NoSchedule` blocks new scheduling; `NoExecute` also evicts pods already running there without the toleration.
- **Affinity/anti-affinity** (node affinity, pod affinity, pod anti-affinity) is an *attract/avoid* mechanism: schedule this pod near/away-from nodes or other pods matching a label selector.
- Both produce a **Pending** pod when unsatisfiable, but the Events reason differs: a taint mismatch reads as "node(s) had taints that the pod didn't tolerate"; an affinity mismatch reads as "didn't match Pod/Node affinity/anti-affinity rules." Same symptom, different `kubectl describe` sentence — that's the disambiguating signal.

---

## Namespaces — the multi-tenancy boundary (not the Linux kind)

A Kubernetes **Namespace** is a way to divide one cluster into multiple virtual clusters for organization and multi-tenancy. It's easy to confuse with Linux namespaces (the kernel isolation primitive behind containers, covered below) — they solve completely different problems and have nothing to do with each other beyond sharing a name.

- **What's scoped by Namespace:** object names (two Pods can both be named `web` if they're in different Namespaces), RBAC (`Role`/`RoleBinding` are namespaced; `ClusterRole`/`ClusterRoleBinding` aren't), `ResourceQuota` and `LimitRange`, and `NetworkPolicy` selectors default to same-namespace matching unless told otherwise.
- **What's *not* scoped by Namespace:** Nodes, PersistentVolumes, and other genuinely cluster-wide objects — a Namespace organizes namespaced resources, it doesn't partition the cluster's actual compute.
- **Why cross-namespace DNS needs the full name:** this is the same mechanism behind the "short service name only resolves in-namespace" behavior covered in the Cluster DNS section below.

---

## Services: ClusterIP vs NodePort vs LoadBalancer vs ExternalName


**Why it exists:** pods have **ephemeral IPs**; a Service is a **stable virtual IP + name** fronting a *dynamic* set of pods. Backends chosen by **label selector** → the matching, ready pods become **Endpoints / EndpointSlices**. Selector typo → empty endpoints → **silent blackhole** (no error log). Check: `kubectl get endpoints <svc>` shows `<none>`.

### The four types
| Type | Adds | Reachable from |
|------|------|----------------|
| **ClusterIP** | stable virtual IP, internal only | inside cluster |
| **NodePort** | ClusterIP + a port (30000–32767) on **every node** | outside via `<nodeIP>:<nodePort>` |
| **LoadBalancer** | NodePort + cloud LB → node ports | outside via real external IP |
| **ExternalName** | a CNAME (no proxy, no VIP, no selector) | DNS alias |

First three are a **cumulative stack**: LoadBalancer ⊃ NodePort ⊃ ClusterIP. External path: cloud LB → node's nodePort → kernel DNAT to pod IP → pod. **ExternalName** is separate — CoreDNS returns a CNAME to an external host (e.g. map internal name → `mydb.rds.amazonaws.com`); pure DNS sugar, no traffic flows through it.

### Data plane — the ClusterIP is a *fiction* (no process listens on it)
**kube-proxy** runs as a DaemonSet on every node. It **programs** the kernel's netfilter (iptables) or IPVS rules. The **Linux kernel (netfilter + conntrack) does the actual DNAT** on every packet — *kube-proxy never touches a data packet*.

iptables path (top-down, all L3/L4):
1. Pod sends to `10.96.0.10:80` (ClusterIP = L3 dest IP / L4 dest port).
2. `nat` table `KUBE-SERVICES` chain matches IP:port.
3. Per-service `KUBE-SVC-*` chain uses the **statistic/random** module to pick a backend (in-kernel, per-connection LB).
4. `KUBE-SEP-*` chain (SEP = Service EndPoint) does the **DNAT**: `10.96.0.10` → real pod IP `10.244.2.7`.
5. **conntrack** stores the mapping so return packets get un-DNAT'd.

**The insight:** there is no LB *process* — load balancing is the kernel rewriting dest IPs per rules kube-proxy installed.

**iptables vs IPVS:** iptables = linear O(n) rule list, slow to update at thousands of services. **IPVS** = kernel hash tables O(1) + real algorithms (rr, least-conn). Same concept, better data structure.

Inspect on a Kind node:
```
docker exec -it <kind-node> iptables -t nat -L KUBE-SERVICES -n | head
# follow ClusterIP → KUBE-SVC-* → KUBE-SEP-* to see the DNAT rule
```

### Sharp distinctions
- **NodePort opens the port on *every* node**, even ones without the pod (kube-proxy forwards across). Lets cloud LB health-check any node.
- **`externalTrafficPolicy`**: `Cluster` (default) = any node → any pod but **SNATs source IP** (lose client IP); `Local` = only same-node pods, **preserves client IP**, risk uneven load. ("Why did I lose the client IP?")
- **Headless Service** (`clusterIP: None`) = no VIP, no DNAT; DNS returns **pod IPs directly** (one A record/pod). Used by StatefulSets to address `web-0` individually.
- **Empty endpoints** = reset/timeout, no log line. `kubectl get endpoints`.

### OSI framing
- **ClusterIP/NodePort** = **L3/L4** — match/rewrite IP+port; can't see HTTP.
- **LoadBalancer** = L4 (cloud network LB) unless L7 ALB.
- **ExternalName** = naming/L7-ish (DNS).
- **Ingress** = **L7** — routes on HTTP host/path *because* it terminates HTTP. **That's why path-based routing needs Ingress, not a plain Service** (a Service is L4 and can't see paths).

### 3 to remember
1. Service = stable VIP/name decoupled from ephemeral pods (selector → EndpointSlices). Types are a cumulative stack; ExternalName is a standalone CNAME.
2. ClusterIP is a fiction — kube-proxy *programs* iptables/IPVS, the **kernel does the DNAT**; LB = per-connection kernel dest-IP rewrite. IPVS scales better than iptables.
3. Services are L4 (can't see HTTP); path/host routing needs Ingress (L7). Headless skips the VIP. Empty endpoints = silent blackhole.

---

## Cluster DNS: CoreDNS and the FQDN format

**Why it exists:** turns Service names into the stable VIP from the Services section above (`curl http://payments` instead of `curl 10.96.0.10`).

### Name → packet chain (the OSI walk)
1. App calls `getaddrinfo("payments")` (L7 naming).
2. libc reads pod's **`/etc/resolv.conf`** (written by kubelet): `nameserver <kube-dns ClusterIP, e.g. 10.96.0.10>`, `search <ns>.svc.cluster.local svc.cluster.local cluster.local`, `options ndots:5`.
3. DNS query to `10.96.0.10:53` (L7 over UDP/53 = L4).
4. That VIP is a Service → kernel DNATs to a real **CoreDNS pod IP** (DNS itself goes through the kube-proxy data plane).
5. CoreDNS answers: cluster Service → its ClusterIP; else forward upstream.
6. App opens TCP to the resolved IP (DNAT'd again if it's a Service VIP).

**CoreDNS is just pods behind the `kube-dns` ClusterIP Service** (Deployment, 2 replicas default). So DNS can fail like any workload — OOM, throttle, empty endpoints → *every* service call fails, looking like app errors.

### FQDN format
```
<service>.<namespace>.svc.cluster.local
```
- Same namespace: `curl http://payments` works (search path fills the rest).
- Cross namespace: short name **fails** — need `payments.prod` or full FQDN. ("Works in staging, fails across namespaces.")
- Headless/StatefulSet pods also get `<pod>.<service>.<ns>.svc.cluster.local` (e.g. `web-0.web.prod...`).

### The `ndots:5` + search-path trap (the famous one)
- **search:** unqualified names get each search domain appended and tried in turn.
- **ndots:5:** a name with **< 5 dots** is treated as *partial* → run through search list **first**.
- So external `api.stripe.com` (2 dots) is tried as `api.stripe.com.prod.svc.cluster.local` → `.svc.cluster.local` → `.cluster.local` (all NXDOMAIN) → *then* `api.stripe.com`. **4–8 lookups per external call** → latency + CoreDNS load spike → real outages.
- **Fixes:** trailing dot `api.stripe.com.` (skips search), lower `ndots` via `dnsConfig`, or **NodeLocal DNSCache** (per-node cache DaemonSet).
- Disambiguating signal: CoreDNS logs / tcpdump showing burst of NXDOMAIN per request.

### CoreDNS internals
Plugin-based, configured via **Corefile** (ConfigMap in kube-system). Key plugins: **kubernetes** (watches API for Services/Endpoints, authoritative for cluster), **forward** (external → upstream resolvers), **cache** (30s default).

### Failure modes
| Symptom | DNS cause | Check |
|---------|-----------|-------|
| All svc-to-svc failing, intermittent | CoreDNS OOM/crashloop, empty endpoints | `kubectl -n kube-system get pods -l k8s-app=kube-dns` |
| Cross-ns fails, same-ns works | short name + search path | use full FQDN |
| External slow, internal fine | ndots:5 amplification | CoreDNS logs flooded w/ NXDOMAIN |
| One app can't resolve | its `/etc/resolv.conf`/`dnsPolicy` | `kubectl exec -- cat /etc/resolv.conf` |

Triage inside a pod:
```
kubectl exec -it <pod> -- cat /etc/resolv.conf
kubectl exec -it <pod> -- nslookup payments
kubectl exec -it <pod> -- nslookup kubernetes.default   # universal "is DNS alive" probe
kubectl -n kube-system get endpoints kube-dns
```

### OSI framing
"DNS is an **L7** protocol over **L4** (UDP/53), resolving an L7 name to an **L3** IP — and because CoreDNS is fronted by an L4 ClusterIP, the query also traverses the L3/L4 kube-proxy data plane before reaching CoreDNS."

### 3 to remember
1. CoreDNS = pods behind `kube-dns` ClusterIP, written into every pod's `/etc/resolv.conf`; fails like any workload and makes app calls fail in DNS-shaped ways.
2. FQDN = `service.namespace.svc.cluster.local`; short names only work in-namespace (search path).
3. `ndots:5` + search amplifies external lookups (4–8 queries); fix with trailing dot / lower ndots / NodeLocal DNSCache.

**RCA-precision exemplar (intermittent internal+external failures, CPU/mem fine):** "CoreDNS pods unhealthy → kube-dns endpoints empty/intermittent → name resolution fails for cluster + external names → outbound calls fail intermittently, looking like a network problem when it's DNS." The shared dependency of internal+external is the arrow toward DNS.

---

## VMs vs containers vs Kubernetes

**Virtual machines** virtualize hardware: a hypervisor (**Type 1**, bare-metal — KVM, ESXi; or **Type 2**, hosted — VirtualBox, VMware Workstation, running on top of a host OS) gives each VM its own kernel and full OS. Strong isolation — a kernel panic in one VM can't touch another — at the cost of a full OS boot and a much bigger memory/disk footprint per instance.

**Containers virtualize the OS, not the hardware.** A container is a regular host process wrapped in Linux namespaces (isolation) and cgroups (limits) — see below — sharing the host's single kernel. That's why a container starts in milliseconds instead of the seconds-to-minutes a VM takes, and why "the substrate under every pod" is one Linux kernel, not one kernel per pod. The tradeoff: weaker isolation than a VM (a kernel-level bug is a potential cross-container escape) and no ability to run a different kernel/OS than the host.

**Docker Compose** is the single-host answer to "I have several containers that need to talk to each other" — one YAML file declares multiple services, their images, and the network between them, and `docker compose up` starts them together. It's the same problem Kubernetes solves, deliberately scoped down to one host with no scheduling, self-healing, or multi-node story — the natural next step once Compose's one-host ceiling becomes the limitation.

**The decision in practice:** reach for a VM when you need a different kernel/OS or hard security isolation between tenants; reach for a plain container (or Compose) when you're packaging one or a few processes for portability on a single host; reach for Kubernetes once you have enough containers, across enough hosts, that you need something else deciding placement, restarting failures, and scaling for you.

---

## Docker/container internals (the substrate under every pod)


A container is **Linux primitives, not a VM**: **namespaces** (pid/net/mnt/uts/ipc/user = isolation) + **cgroups** (resource limits) + a **union/overlay filesystem** (layered image). A container is a process.

**`ENTRYPOINT`/`CMD` exec vs shell form — the classic trap:**
- **Shell form** (`CMD myapp`) runs your app as a *child* of `/bin/sh`. Signals sent to PID 1 hit the shell, not your app → **SIGTERM is ignored, no graceful drain, zombie reaping is broken.**
- **Exec form** (`CMD ["myapp"]`) makes your app PID 1 directly — it receives signals itself and can shut down gracefully.

This one distinction explains a whole class of "pod takes the full `terminationGracePeriodSeconds` to die" incidents.

**Volumes — what survives a container's death, and what doesn't:**
- A container's own writable layer (the top of the union/overlay filesystem) is deleted with the container. Anything that needs to survive a restart has to live outside it.
- **Bind mount** — a host directory mapped straight into the container. Tied to that specific host; this is effectively what a Kubernetes `hostPath` volume is.
- **Named volume** — storage Docker manages itself, independent of any specific host path; survives container removal, is the closer analog to a PVC.
- **tmpfs mount** — memory-backed, never touches disk, gone the moment the container stops. Useful for secrets/scratch space you explicitly don't want persisted.

**K8s/EKS architecture — control plane vs data plane:**
- **Control plane:** API server (front door — authn/authz/admission), etcd (state), scheduler (placement), controller-manager (reconcile loops). On EKS this is managed (AWS runs API server + etcd across multiple AZs).
- **Data plane:** kubelet (runs on each node, talks to container runtime), kube-proxy (programs the Service data plane — see above), the container runtime itself.
- **Request path of `kubectl apply`:** authn → authz → admission (mutating/validating webhooks) → persisted to etcd → controller notices the diff → scheduler places new pods → kubelet on the target node creates them.
- **Rolling update mechanics:** `Deployment → ReplicaSet → Pods`; `maxSurge`/`maxUnavailable` control how many extra/how many missing pods are tolerated mid-rollout.

### 3 to remember
1. A container = Linux namespaces + cgroups + overlay FS, not a VM — reason about it with Linux tools.
2. Shell-form `CMD` breaks signal delivery to your app (PID 1 is the shell); exec-form fixes it.
3. Control plane decides *and remembers* (API server/etcd/scheduler/controller-manager); data plane *executes* (kubelet/kube-proxy/runtime).
