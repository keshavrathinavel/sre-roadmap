# SRE Onboarding Primer
## A Curriculum for New SREs Ramping Up on Production Systems

---

## Who this is for

This is written for someone starting out as an SRE — early career, ramping up on real production
systems, not yet expected to have deep formal grounding in Linux internals, distributed systems
theory, or large-scale operational practice. The goal isn't to pass an interview; it's to become
genuinely effective at running and troubleshooting the kinds of systems an SRE owns: Kubernetes,
cloud infrastructure, observability stacks, and the data platforms increasingly sitting alongside
them.

There's no fixed timeline here — go at whatever pace actually gets the material to stick. If you
already have a couple of years of hands-on Kubernetes/cloud experience, move through Phase 1
faster. If this is your first real production role, don't rush it — the failure labs are worth
running slowly enough to actually understand what broke and why, not just to get to the next topic.

**If you're not sure where to start: start with the failure labs.** Breaking something on purpose
and fixing it teaches faster than reading topic docs in sequence. The phases below are organized by
topic for reference and depth, not as a mandate to read front-to-back before touching a cluster —
dip into `roadmap/failure-labs/` early and often, and pull in the topic docs when a failure exposes
a gap in your understanding.

---

## How to use this repo

- `roadmap/failure-labs/` — hands-on break-it-yourself curricula (Kubernetes, data platforms) with
  manifests and assets — **start here.** This is where the learning actually compounds
- `CHECKLIST.md` / `checklist.html` — a flat, checkable version of every topic
  below, organized by domain rather than by phase, so you always know what's left regardless of
  where you are in the curriculum
- `roadmap/topics/` — deep-dive reference docs (Kubernetes internals, Linux & networking, AWS/EKS,
  system design/observability, data-platform streaming, scripting patterns)
- `roadmap/system-design/` — the HLD/LLD framework plus worked LLD and distributed-systems problems
- `roadmap/scripting-practice/` — worked Python exercises (log parsing, rate limiter, LRU/TTL
  cache, top-K stream) — the coding patterns that come up in real automation and tooling work

---

## Resource Priority Stack

If you only have time to engage with a handful of external resources, this is the order that pays
off fastest:

1. **NALSD workbook chapter** — sre.google/workbook/non-abstract-design — the clearest published
   framework for reasoning rigorously about a system's failure modes before jumping to a redesign
> https://sre.google/workbook/non-abstract-design/
2. **SRE Book, selective chapters** — sre.google/sre-book — this is the shared vocabulary
   (SLOs, error budgets, toil, blamelessness) that the rest of this curriculum assumes
> https://sre.google/sre-book/effective-troubleshooting/
3. **syedali.net** — a well-organized practical question bank for testing your own understanding
   of Linux and systems fundamentals
> https://syedali.net/engineer-interview-questions/
4. **Brendan Gregg's USE method + Netflix's 60-second Linux analysis post** — the two best
   short reads for structuring a live troubleshooting investigation
> https://www.brendangregg.com/usemethod.html
> https://www.brendangregg.com/Perf/linux_perf_tools_full.png
> https://netflixtechblog.com/linux-performance-analysis-in-60-000-milliseconds-accc10403c55

The full categorized list — every book, article, tool, and video used across this curriculum —
lives in **Resources** near the end of this doc.

---

## Always-On (Parallel Track)

These run alongside every phase:

- **Coding practice, done consistently** — focus on the patterns that actually show up in
  production tooling (heap, BFS/DFS, sliding window, two pointers) rather than grinding breadth
  for its own sake. `roadmap/topics/scripting-patterns.md` and `roadmap/scripting-practice/` are
  the SRE-flavored version of this: rate limiters, caches, log parsers, retry logic.
- **Go learning** — mirror your Python/scripting solutions in Go once you're comfortable; a lot of
  the infrastructure tooling you'll touch is written in Go
- **K8s lab writeups** — after every failure scenario, write a short RCA paragraph. This is the
  single habit that compounds fastest — it's the same discipline you'll use for real incident
  postmortems later
- **Google SRE Book** — read chapter-selectively as you hit each phase (not cover to cover)
- **syedali.net** — ongoing reference for testing your Linux and systems understanding
- **The checklist** — `CHECKLIST.md` (and its interactive version, `checklist.html`)

---

## Phase 1: Systems Foundations

### Linux Internals
The deepest, most foundational area for an SRE. A single command (e.g. `ping`) can unpack into an
entire afternoon of learning if you follow it all the way down.

**Topics:**
- Virtual memory: paging, demand paging, anonymous vs file-backed memory, page faults, dirty pages, page cache, swapping, TLB, MMU, OOM, overcommit
- Signals: SIGTERM, SIGKILL, SIGSEGV, SIGCHLD, signal handlers, masking, default handlers
- Processes: fork/exec, zombie/orphan, copy-on-write, interruptible vs uninterruptible sleep, RSS vs VSZ, runqueue, CFS and scheduler policies, preemption, context switching, CPU registers and caches
- IPC and locking: pipes, shared memory, semaphores, mutexes — advantages/disadvantages, syscalls
- Networking stack: kernel vs userspace, common syscalls, sockfs
- Cgroups and namespaces
- System calls: 12 key syscalls, CPU protection rings, mode switch, userspace vs kernel space
- Tracing: strace, ltrace, ptrace, perf, eBPF
- VFS: proc, sockfs, pipefs, file descriptors, open file table, inodes, NFS, LVM, ACLs, path resolving
- Linux boot process (high-level): BIOS → MBR → GRUB → kernel → init → userspace
- Interrupts: interrupt context vs thread context, top half and bottom half, interrupt masking
- Common tools: iostat, vmstat, top, pidstat, iotop, lsof, df, du — when and why, not just what

**Resources:** Brendan Gregg's USE method and perf tools map, the Netflix 60-second Linux post, and
syedali.net for self-testing — full links in **Resources → Linux & Performance**. Pair with
`roadmap/topics/linux-and-networking.md` for the deep-dive reference on everything in this section.

**Troubleshooting mental model to drill:**
> Before touching the keyboard: (1) Is this live or historical? (2) Am I looking for symptoms or root cause? (3) Is the problem CPU, memory, I/O, network, or application-level? (4) What is the lowest-cost, highest-signal command to start with?

Narrate every command as: **command → intent → signal**. This is the habit that makes you fast
and legible to teammates during a real incident, not just correct.

### Distributed Systems
- DDIA (Kleppmann) — selective chapters: replication, partitioning, transactions, consensus
- Kubernetes internals: scheduler, kubelet, etcd, API server, controller manager (`roadmap/topics/kubernetes-internals.md`)
- Kind cluster labs — break and fix structured failure scenarios (see Failure Curriculum below)

### Coding & Scripting — Start Now
- Focus on patterns: heap, BFS/DFS, graphs, sliding window, two pointers
- Practice without IDE autocomplete occasionally — you won't always have it when debugging on a
  bastion host or inside a container
- Classic problems worth having solved once, by hand: Kth largest in a stream, shortest path in a
  graph, topological sort, filesystem size via DFS, string validation with backtracking
- Python first, then mirror solutions in Go (`roadmap/scripting-practice/` has worked examples)

---

## Phase 2: Security + K8s Mastery

### Cloud Security
- Zero trust architecture
- Vault deep dive — dynamic secrets, PKI, auth methods
- OIDC, mTLS, SPIFFE/SPIRE
- IAM least-privilege patterns
- Network segmentation
- GDPR-compliant PII handling
- Infrastructure as Code — Pulumi (`CHECKLIST.md` § Infrastructure as Code): stacks, component resources, policy as code, and the imperative-language-vs-declarative-DSL tradeoff

### K8s Failure Curriculum
Work through all 5 categories from `roadmap/failure-labs/kubernetes.md`, one at a time, at
whatever pace lets each one actually sink in.

**Category 1 — Resource Exhaustion**
- OOMKilled pods: distinguish from CrashLoopBackOff
- CPU throttling: mysteriously slow ≠ crashing — completely different fixes
- Node pressure: fill disk via hostPath, watch kubelet evict in QoS order (BestEffort → Burstable → Guaranteed)

**Category 2 — Networking Failures**
- CoreDNS deletion: service-to-service failures that look like app errors
- Service endpoint mismatch: selector matches nothing, traffic silently fails
- NetworkPolicy blocking: timeout vs connection refused — know the difference
- CNI failure: pods stuck in ContainerCreating

**Category 3 — Control Plane Stress**
- etcd latency via disk I/O spike: watch API server slow down
- API server overload: learn API priority and fairness

**Category 4 — Application Failure Patterns**
- CrashLoopBackOff from different causes: missing env var, missing ConfigMap, bad command, OOM — all look the same
- Liveness vs readiness probe confusion: use startupProbe
- Pending pods: resource requests too high, nodeSelector mismatch, taint without toleration

**Category 5 — Stateful and Storage Failures**
- PVC stuck in Pending: non-existent StorageClass, WaitForFirstConsumer binding mode
- Pod stuck in Terminating: preStop hook + terminationGracePeriodSeconds

**Diagnosis framework for every failure:**
1. Symptoms first — what would alerts or users report?
2. Hypothesis — guess the cause *before* checking anything
3. `kubectl describe`
4. `kubectl logs` / `kubectl logs --previous`
5. Metrics — what does this look like in Prometheus/Grafana?
6. Root cause — write one sentence: *"This happened because X, which caused Y, which surfaced as Z"*
7. Fix + prevention

> The RCA sentence separates engineers who fix things from engineers who understand things. This
> is also, almost verbatim, the shape of a good postmortem summary — the habit you're building now
> is the same one you'll use on real incidents later.

**Clarifying questions to always ask during real troubleshooting:**
- What changed recently? (deployments, node upgrades, Terraform/Pulumi applies, cert rotations)
- When did this start? Correlate with change history.
- Has this happened before? Recurring issues have patterns.
- What's the blast radius? One pod, one service, one namespace, whole cluster?
- Any upstream/downstream services affected?
- Who made the last change and what was it? Check ArgoCD sync history, cloud provider audit logs.

### Coding & Scripting — Continue
- Topological sort, dynamic programming
- String algorithms: KMP, Rabin-Karp
- Backtracking
- Regex patterns, dictionary/hashmap problems
- Mirror solutions in Go

---

## Phase 3: Observability + Reliability

### Observability
- SLOs and error budgets — deep understanding, not surface knowledge
- OpenTelemetry: traces, metrics, logs
- Chaos engineering: Litmus Chaos with structured hypotheses
- Prometheus + Grafana: observe every K8s failure through metrics
- Full worked example: `roadmap/topics/system-design-observability.md`

**SRE Book chapters for this phase:** *Embracing Risk*, *Service Level Objectives*, *Handling
Overload*, *Addressing Cascading Failures* — full phase-by-phase reading map in
**Resources → SRE Practices & Reliability** (chapter guide).

### NALSD Framework
A rigorous, non-abstract design framework for reasoning about an existing (or proposed) system's
failure modes — meaningfully different from a generic "design me a system" exercise because it
starts from *what's already broken or fragile*, not a blank page.

**Core mental model:** Diagnose and stabilize first. Redesign second.

**8-step NALSD playbook** (from the Google workbook):
1. Clarify requirements and constraints
2. Back-of-envelope estimation (storage, RPS, bandwidth)
3. Identify the current system's failure modes
4. Propose immediate mitigations
5. Draw high-level architecture
6. Deep dive 2–3 components with tradeoffs
7. Failure modes and reliability (SLOs, monitoring, fallback)
8. Cost/economic tradeoffs of the design

**Resources:** the NALSD workbook chapter is the primary resource here (see **Resource Priority
Stack** above); highscalability.com, aosabook.org, and the system-design-primer round it out —
full links in **Resources → System Design & NALSD**.

**Back-of-envelope math traps to know:** Bandwidth vs IOPS vs latency feasibility checks. Know your constants (disk seek time, RAM speed, network RTT).

### HLD/LLD Practice
Using `roadmap/system-design/hld-lld-framework.md` as the framework. Run these with a mentor or
teammate as a genuine design conversation, not a test — talking through the tradeoffs out loud
with someone who can push back is most of the value.

**A good way to structure the conversation (time allocation for a ~30 min session):**
- 2–3 min: Clarify requirements (scale, consistency, latency SLOs, clients, failure definition) — jumping straight to design is a red flag
- 2 min: Back-of-envelope estimation
- 5 min: High-level architecture (major components + data flow, no deep dive yet)
- 10–15 min: Deep dive on 2–3 components with explicit tradeoffs (consistency vs availability, push vs pull, sync vs async)
- 5 min: Failure modes and reliability — **this is where SRE instinct shows up most clearly**
- Tradeoffs: no design is perfect, explain weaknesses and how the design changes at scale

**SRE-relevant HLD problems worth practicing:**
- Multi-tenant Kubernetes platform for 50 teams
- Observability stack for large microservices
- Secrets management system across environments
- CI/CD platform with rollback and canary deployments
- Distributed rate limiter (token bucket vs sliding window)
- Incident management and alerting pipeline
- Zero-downtime deployment system
- Streaming data platform (Kafka → Flink → lake + serving tier) — see `roadmap/topics/data-platform-streaming.md`

**LLD patterns to know:**
- Rate limiter (token bucket vs sliding window)
- Circuit breaker
- Retry with exponential backoff + jitter
- Work queue with workers
- Leader election
- See `roadmap/system-design/lld-problems/` and `roadmap/topics/scripting-patterns.md` for worked examples

**Resources:** *System Design Interview* (Alex Xu, both volumes) for HLD, Refactoring Guru for LLD
patterns — full links in **Resources → System Design & NALSD**. Also:
write up your own team's production infrastructure as if you had to explain and defend every
decision out loud to a new teammate.

---

## Phase 4: Putting It Into Practice

By this point the goal shifts from *learning the material* to *applying it on real systems* —
shadowing on-call, taking part in postmortems, and running full troubleshooting sessions on
production (or production-like) infrastructure with a mentor.

### On real systems
- Shadow on-call for at least one full rotation before taking your own — watch how a senior SRE
  actually triages, not just what they conclude
- Take a real (or realistic, from the failure labs) incident and run the full loop yourself:
  symptoms → hypothesis → diagnose → RCA sentence → fix → prevention, with someone experienced
  reviewing your reasoning afterward
- Practice explaining your reasoning **out loud** as you go, not just at the end — this is the
  single biggest gap between "knows the material" and "is useful during a live incident"

### Communicating about incidents
The instinct that separates a strong SRE from a merely knowledgeable one is how they *talk about*
what they did, not just whether they got the right answer. A structure worth internalizing:

1. Always ask clarifying questions before diving in — even when you think you understand the ask
2. For multi-part questions or asks: repeat all parts back before answering any of them
3. Structure incident writeups and updates as: Situation → Task → Action → Result → **Measurement**
   (the Measurement is what makes it an SRE-quality writeup rather than a story — quantify the
   before/after, not just "it got better")
4. Favor "systemic prevention" framing over "heroism" framing — the goal of a postmortem is a
   system that doesn't need a hero next time, not a story about the hero this time
5. Blamelessness should come through naturally in how you write and talk about failures — that's
   a habit, not a policy you have to remember to apply

**SRE Book chapters for this phase:** *Being On-Call*, *Postmortem Culture: Learning from Failure*
— full phase-by-phase reading map in **Resources → SRE Practices & Reliability** (chapter guide).

By now you should have:
- Several written RCAs from the failure labs, in the same shape you'd use for a real postmortem
- Go proficiency (readable, production-safe code)
- Comfort running a full HLD/LLD design conversation out loud with a mentor

---

## Resources

Every external resource used across this curriculum, colocated and categorized here. Phase
sections above point back into this list rather than repeating full links.

### Linux & Performance
| Resource | Type | Phase | Notes |
|----------|------|-------|-------|
| Systems Performance — Gregg | Book | Phase 1 | Reference only |
| USE method (brendangregg.com/usemethod.html) | Article | Phase 1 | Structuring a live troubleshooting investigation |
| Linux perf tools full map (brendangregg.com/Perf/linux_perf_tools_full.png) | Reference | Phase 1 | Map of tool → subsystem |
| Linux Performance Analysis in 60,000 Milliseconds (netflixtechblog.com) | Article | Phase 1 | 60-second Linux troubleshooting checklist |
| syedali.net/engineer-interview-questions | Question bank | All | Self-testing on Linux/systems fundamentals |

### Distributed Systems & Kubernetes
| Resource | Type | Phase | Notes |
|----------|------|-------|-------|
| DDIA — Kleppmann | Book | Phase 1 | Selective: replication, partitioning, consensus |
| Kubernetes in Action — Lukša | Book | Phase 1–2 | Selective chapters |
| aosabook.org/en/distsys.html | Article | Phase 3 | Distributed systems architecture |
| [Google Tech Talks](https://www.youtube.com/playlist?list=PLSIUOFhnxEiC3YTdxwqZqgEY5imVL8U8J) | Video | All | Broad CS/infra talks — dip in whenever a topic overlaps |
| k9s | Tool | Phase 2 | Terminal UI for watching K8s failures in real time |
| stern | Tool | Phase 2 | Tail logs from multiple pods simultaneously |

### System Design & NALSD
| Resource | Type | Phase | Notes |
|----------|------|-------|-------|
| Google SRE Workbook — NALSD chapter (sre.google/workbook) | Book chapter | Phase 3 | Primary resource for the design framework |
| System Design Interview — Alex Xu (vol 1 + 2) | Book | Phase 3 | Good HLD reference despite the title |
| system-design-primer (github.com/donnemartin/system-design-primer) | Repo | Phase 3 | HLD reference |
| highscalability.com | Article | Phase 3 | Back-of-envelope estimation |
| Latency numbers every engineer should know (gist.github.com/hellerbarde/2843375) | Reference | Phase 3 | Constants for back-of-envelope math |
| refactoring.guru | Reference | Phase 3 | LLD patterns |

### SRE Practices & Reliability
| Resource | Type | Phase | Notes |
|----------|------|-------|-------|
| Google SRE Book (sre.google/sre-book) | Book | All phases | Selective chapters only — see chapter guide below |
| sre.google/sre-book/effective-troubleshooting | Article | Phase 2–3 | Troubleshooting methodology |
| Prometheus + Grafana | Tool | Phase 3 | Observe every failure through metrics |
| Litmus Chaos | Tool | Phase 3 | Structured chaos experiments |

**SRE Book chapter guide:**
| Chapter | Phase |
|---------|-------|
| Effective Troubleshooting | Phase 1 (Resource Priority Stack) |
| Embracing Risk | Phase 3 |
| Service Level Objectives | Phase 3 |
| Handling Overload | Phase 3 |
| Addressing Cascading Failures | Phase 3 |
| Being On-Call | Phase 4 |
| Postmortem Culture: Learning from Failure | Phase 4 |

---

## Repo structure

- `CHECKLIST.md` / `checklist.html` — the flat, checkable version of every topic below, organized by domain rather than by phase or date
- `roadmap/topics/` — deep-dive reference docs (Kubernetes internals, Linux & networking, AWS/EKS, system-design/observability, data-platform streaming, scripting patterns)
- `roadmap/failure-labs/` — hands-on break-it-yourself curricula (Kubernetes, data platforms) with manifests and assets
- `roadmap/system-design/` — the HLD/LLD framework plus worked LLD and distributed-systems problems
- `roadmap/scripting-practice/` — worked Python exercises (log parsing, rate limiter, LRU/TTL cache, top-K stream)
