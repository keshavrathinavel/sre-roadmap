# Linux Internals & Networking — Reference

> Consolidated into one topic reference.
> Pairs with the "Linux Internals" section of the roadmap — use this as the concrete
> detail underneath those topic headers, and `roadmap/failure-labs/kubernetes.md` for hands-on drills.
>
> **The narration habit to build for every command you run:** state **command → intent → signal**
> out loud. What are you running, why (what hypothesis does it test), and what does the output
> actually tell you. This is the single highest-leverage troubleshooting habit there is.

---

## Process model

- **fork/exec:** `fork()` clones the calling process (child gets a copy of the address space, **copy-on-write** — pages aren't actually duplicated until one side writes to them). `exec()` replaces the process image in place with a new program.
- **Zombie vs orphan:**
  - **Zombie** — child has exited but the parent hasn't called `wait()`/`waitpid()` yet, so the kernel keeps the exit status around as a defunct process table entry.
  - **Orphan** — parent died before the child; the child gets reparented to PID 1 (`init`/systemd), which reaps it automatically.
- **Process states:** `R` (running/runnable), `S` (interruptible sleep — waiting on an event, can be woken by a signal), `D` (**uninterruptible** sleep — usually waiting on disk I/O, *cannot* be killed or signaled until the I/O completes), `Z` (zombie), `T` (stopped/traced).
  - **D-state matters for load average** — see Scheduling below.
- **Signals:**
  - `SIGTERM` — graceful, catchable (a handler can clean up: close fds, flush buffers, drain connections).
  - `SIGKILL` — immediate, **uncatchable**, no handler runs. The kernel just removes the process.
  - `SIGSEGV` — invalid memory access.
  - `SIGCHLD` — sent to a parent when a child changes state (exits/stops); the trigger for `wait()`.
  - `SIGHUP` — historically "terminal hung up"; commonly repurposed as "reload config."
  - Signals can be **masked** (blocked temporarily) and have **default handlers** if the process doesn't install its own.

```
kernel ──SIGTERM──▶ app process
                      │
                      ▼
              signal handler fires
                      │
                      ▼
              cleanup runs (close fds, flush, etc.)
                      │
                      ▼
              process exits
                      │
                      ▼
   parent hasn't reaped it yet ──▶ ZOMBIE (defunct)
                      │
            parent calls wait() ──▶ reaped, gone
```

---

## Memory & virtual memory

- **Virtual address space:** every process gets its own isolated address space; the MMU + page tables translate virtual → physical addresses. This is what gives processes memory isolation.
- **Paging & demand paging:** memory is managed in fixed-size pages. **Demand paging** means pages are only brought into physical memory when actually touched, not eagerly on allocation.
- **Page faults:**
  - **Minor fault** — the page exists somewhere accessible (e.g. already in page cache, or a CoW page being shared) and just needs a mapping fixed up. Cheap.
  - **Major fault** — the page has to be fetched from disk. Expensive; a burst of major faults under memory pressure is a real symptom, not noise.
- **Page cache:** the kernel caches file-backed pages in RAM. It shows up as "used" memory but is **reclaimable** — this is why `free -h`'s "available" column matters more than "free."
- **RSS vs VSZ:**
  - **VSZ** (virtual size) — total virtual address space reserved, including memory that's mapped but never touched, shared libraries, etc. Often huge and not meaningful for "how much memory is this process really using."
  - **RSS** (resident set size) — physical memory actually resident right now. Closer to the real answer, but still double-counts shared pages (shared libs) across processes.
- **Swap:** when physical memory is exhausted, anonymous (non-file-backed) pages get written to disk and evicted from RAM. Swapping in is a major fault by definition.
- **OOM killer:** when the kernel can't satisfy a memory request and can't reclaim enough, it picks a victim process to kill based on `oom_score` (roughly: memory usage weighted by priority) and sends `SIGKILL`.
- **Overcommit:** the kernel by default allows processes to allocate (via `mmap`/`malloc`) more virtual memory than physically exists, betting that not all of it will actually be touched (demand paging). This is why a process can "successfully" allocate memory it will later get OOM-killed for actually using.
- **Working set vs limit:** a cgroup (container) can get OOM-killed even when the *node* has free memory — the cgroup's own memory limit is what's enforced, independent of node-wide availability. Diagnosing "how did this get OOM-killed with memory free on the node" starts here.
- **Distinguishing a memory leak from an undersized limit:** a leak shows RSS climbing steadily over hours; an undersized limit shows RSS hitting the ceiling almost immediately on startup. Check history in Prometheus (`container_memory_working_set_bytes`) rather than guessing from a single snapshot.

---

## Filesystem / VFS

- **File descriptors:** small integers a process uses to refer to open files/sockets/pipes. `0` = stdin, `1` = stdout, `2` = stderr by convention. `open()` returns the **lowest free** fd in that process's fd table. The fd table points into a system-wide **open file table**, which points to the underlying **inode**.
- **Inodes:** store file **metadata** (permissions, owner, size, timestamps, pointers to data blocks) — **not the filename**. The filename lives in the directory entry, which just maps a name to an inode number. That's *why* hard links work.
  - **Hard link** — a second directory entry pointing at the *same* inode. Deleting one name doesn't remove the data until the inode's link count hits zero.
  - **Soft (symbolic) link** — a separate small file whose contents are a path string to another file. Breaks if the target moves; has its own inode.
  - `stat` output surfaces inode fields directly: permissions, owner/group, size, mtime/atime/ctime, link count.
- **Walking `ls -l` at the syscall level:** `opendir()` the directory → `readdir()` each entry (gets name + inode number) → `stat()` each entry's inode to pull permissions/owner/size/mtime for the columns actually printed. This is a good one to be able to narrate cold — it ties filenames, directory entries, and inodes together in one flow.
- **Path resolution:** each component of a path is looked up in turn, following the directory entries down to the final inode; symlinks get resolved along the way (with a loop limit).
- **`/proc`:** a virtual filesystem exposing kernel/process state as files.
  - `/proc/[pid]/fd` — that process's open file descriptors (symlinks to what they point to).
  - `/proc/[pid]/maps` — that process's memory mappings (what's mapped where, and from what).
  - `/proc/meminfo`, `/proc/cpuinfo` — system-wide memory/CPU info.
- **Permissions:** standard rwx bits for user/group/other via `chmod`/`chown`; **sticky bit** (on a directory, only the file's owner can delete/rename their own files within it — e.g. `/tmp`); **setuid/setgid** (a program runs with the *file owner's* privileges rather than the invoking user's).

---

## Scheduling & CPU

- **Context switch:** the kernel saves the current process/thread's CPU register state and restores another's. Not free — it costs cache locality (TLB, L1/L2) on top of the raw save/restore.
- **Run queue:** the set of runnable-but-not-currently-running tasks waiting for CPU time.
- **CFS (Completely Fair Scheduler):** Linux's default scheduler; approximates giving each runnable task a fair share of CPU time over time, using a virtual-runtime accounting scheme rather than fixed time slices.
- **Load average ≠ CPU utilization.** Load average counts **runnable + uninterruptible-sleep (`D`-state)** tasks, not just CPU-busy ones. A box can show a high load average while CPU sits near idle if a lot of processes are blocked in `D` state waiting on slow disk I/O. **This is a classic trap** — "high load, low CPU" almost always points at I/O wait, not compute.
- **Threads vs processes:** threads within a process **share** the address space (heap, globals, open fds) but have their own stack and registers; processes are fully isolated. Shared memory means threads need explicit synchronization (locks/mutexes) to avoid race conditions; processes need explicit IPC to communicate at all.
- **The Python GIL:** the Global Interpreter Lock serializes execution of Python bytecode — only one thread runs Python code at a time even on a multi-core box. Implication: threading helps for **I/O-bound** work (the GIL is released while waiting on I/O) but does **not** parallelize **CPU-bound** work — use multiprocessing (separate processes, separate GILs) or a native extension for that.
  - The clean decision rule: **I/O-bound → threading or asyncio; CPU-bound → multiprocessing** (or push the hot path to native code).

---

## IPC (inter-process communication)

- **Pipes** — a unidirectional byte stream between related processes (e.g. shell `|`); simple, kernel-buffered, no persistence.
- **Shared memory** — a memory segment mapped into multiple processes' address spaces; fastest IPC (no copying through the kernel on each message) but requires explicit synchronization since there's no built-in message framing.
- **Semaphores** — a counter-based synchronization primitive for controlling access to a shared resource across processes (or threads); can allow N concurrent holders, not just 0/1.
- **Mutexes** — a binary lock, typically used *within* a process between threads for mutual exclusion.
- **When to pick which:** pipes for simple one-way streaming between related processes; shared memory when you need high-throughput data exchange and can manage your own synchronization; semaphores/mutexes to guard the actual critical sections once data is shared.

---

## Cgroups & namespaces

These two primitives are what a container actually *is* — see the Docker/container internals section in `topics/kubernetes-internals.md` for how K8s builds on them.

- **Namespaces isolate what a process can *see*:** `pid` (its own process tree), `net` (its own network stack/interfaces), `mnt` (its own filesystem mounts), `uts` (hostname), `ipc` (its own IPC objects), `user` (UID/GID mapping).
- **Cgroups control what a process can *use*:** CPU, memory, I/O, and PID-count limits enforced by the kernel — this is the actual mechanism behind Kubernetes resource requests/limits.

---

## Syscalls & tracing tools

- **Mode switch / protection rings:** the CPU distinguishes **user space** (restricted, where normal programs run) from **kernel space** (full hardware access). A syscall is the controlled doorway from one to the other — the CPU switches ring/privilege level, the kernel does the privileged work, then control returns to user space.
- **Key syscalls to know cold:** `fork`, the `exec` family, `open`, `read`, `write`, `stat`, `opendir`/`readdir`, `mmap`. Being able to name which syscalls a given command must be issuing (e.g. `curl example.com` → `socket`, `connect`, `sendto`, `recvfrom`, `write`) is a strong signal.
- **Tracing tools:**
  - `strace` — traces syscalls a process makes (and their arguments/return values). The go-to for "why is this process stuck/slow at the OS boundary."
  - `ltrace` — traces library calls instead of syscalls.
  - `perf` — CPU profiling, hardware counters, flame-graph-style analysis.
  - `eBPF` — programmable in-kernel tracing/observability; the modern successor to a lot of ad-hoc tracing (Brendan Gregg's tooling leans heavily on this).

---

## Networking stack — trace a request end to end

The narration to build: **DNS resolution → TCP handshake → socket/kernel → application**, at every layer naming what's happening and what would signal a failure there.

### DNS resolution path
Stub resolver (on the client, reads `/etc/resolv.conf`) → recursive resolver (usually your ISP/org resolver, does the legwork) → root nameserver → TLD nameserver → authoritative nameserver for the domain. The recursive resolver caches results per TTL so most queries never walk the full chain.

### TCP
- **3-way handshake:** `SYN` → `SYN-ACK` → `ACK`. Establishes sequence numbers in both directions before any data flows.
- **4-way teardown:** `FIN`/`ACK` in each direction (can collapse to 3 packets if one side combines FIN+ACK).
- **Why `TIME_WAIT` exists:** the side that sent the final `ACK` holds the connection in `TIME_WAIT` for **2×MSL** (maximum segment lifetime) to guarantee any stray/duplicate late-arriving segments from the old connection are drained before the same 4-tuple (src IP/port, dst IP/port) can be reused. It's a correctness safeguard, not a leak — though a huge number of `TIME_WAIT` sockets can itself become an ephemeral-port exhaustion problem on a high-churn server.
- **TCP states worth recognizing in `ss -tan`:** `ESTABLISHED`, `TIME_WAIT`, `CLOSE_WAIT`. **`CLOSE_WAIT` buildup is a specific, classic symptom: the remote side closed, but *your* application never called `close()` on the socket** — a file-descriptor leak in the app, not a network problem. A pile of sockets stuck in `CLOSE_WAIT` (not `TIME_WAIT`) is the tell.
- **Flow control vs congestion control:** flow control (the receive window) protects the *receiver* from being overwhelmed; congestion control (slow start, etc.) protects the *network path* from being overwhelmed. Different problems, different mechanisms.
- **TCP vs UDP:** TCP gives ordered, reliable, connection-oriented delivery with flow/congestion control — pick it when correctness and ordering matter more than latency. UDP is fire-and-forget, no ordering/retransmission guarantees — pick it for latency-sensitive or loss-tolerant traffic (DNS queries, video/voice, some metrics pipelines) where the application layer handles any reliability it needs itself.

### TLS
Asymmetric crypto (public/private key) is used only to negotiate and exchange a **symmetric** session key (asymmetric crypto is too slow to encrypt bulk traffic with). Certificates prove the server's identity is bound to that public key, chained up to a trusted CA. **SNI** (Server Name Indication) lets a client tell the server which hostname it wants *before* the TLS handshake completes, which is what allows one IP to serve TLS for multiple hostnames.

### "What happens when you type a URL and hit Enter?"
The canonical end-to-end walk, worth being able to deliver in under a minute: **DNS resolution → TCP connect (3-way handshake) → TLS handshake (if https) → HTTP request/response → browser renders.** Every system-design and troubleshooting round expects you can expand any one of these steps on request.

### L4 vs L7 load balancing
- **L4** — balances on IP/port only; fast, protocol-agnostic, can't see HTTP paths/headers.
- **L7** — terminates HTTP (or gRPC, etc.) and can route on host/path/headers, do content-based routing, retries, etc. Costs more (has to actually parse the protocol). This is the same distinction as "a Service is L4, an Ingress is L7" in Kubernetes.

### CIDR / subnets / NAT (basics)
CIDR notation (`10.0.0.0/16`) expresses a network address plus a prefix length denoting how many bits are the fixed network portion vs the variable host portion. Subnetting splits a network into smaller ranges (e.g. public vs private subnets in a VPC). **NAT** rewrites private (non-routable) addresses to a routable public address (and back for return traffic) so private hosts can reach the internet without each needing a public IP.

### The three failure signatures to distinguish, always
| Symptom | What actually happened | Where you'd see it |
|---|---|---|
| **Connection refused** | A `RST` came back immediately — something is listening on that IP but *nothing is listening on that port* (or a firewall actively rejected it). | Fast failure, `curl` errors out immediately. |
| **Timeout** | The `SYN` was dropped silently — no response at all. Usually a firewall/security-group/NetworkPolicy silently dropping the packet, or the host is genuinely unreachable. | Slow failure, hangs until client-side timeout. |
| **Reset mid-stream** | A connection was `ESTABLISHED` and working, then got an `RST` partway through — something (app crash, a stateful firewall dropping the connection, a load balancer idle-timeout) tore it down after the fact. | Was working, then abruptly errors. |

This is the single most useful disambiguating habit in networking troubleshooting: **the failure mode tells you what layer broke.** A silent drop (timeout) points at something enforcing policy (firewall/NetworkPolicy/security group); an active refusal (RST) points at "nothing is there to answer."

### Tools and what each one actually reveals
| Tool | Reveals |
|---|---|
| `ss -tanp` | Current sockets and their states (`ESTABLISHED`, `TIME_WAIT`, `CLOSE_WAIT`, …), with owning process. |
| `dig` / `nslookup` | DNS resolution — what a name resolves to, and via which record/server. |
| `curl -v` | Full request lifecycle with timing — DNS, connect, TLS, headers, body — one command, one layer at a time. |
| `tcpdump` | Raw packet capture — ground truth when higher-level tools disagree with reality. |
| `traceroute` / `mtr` | The routing path a packet takes and where along it latency/loss appears. |
| `nc -zv host port` | Raw TCP connectivity check — "is anything listening here," independent of the app protocol. |
| `pg_isready` | Postgres-specific readiness check (an example of a protocol-specific health probe). |

---

## Debugging scenarios worth being able to narrate cold

For each, the discipline is: **state the symptom → form a hypothesis → name the one command that would confirm or kill it → name the disambiguating signal.**

1. **Unreachable server** — is it connection refused (nothing listening / firewall rejecting) or a timeout (packet silently dropped)? That distinction alone tells you whether to look at the app or the network policy.
2. **Slow server** — is it actually CPU-bound, or waiting on I/O? Check load average vs CPU% first; a high load average with idle CPU means `D`-state processes waiting on disk/network, not a compute problem.
3. **High load, low CPU** — the load-average trap above: something is stuck in uninterruptible sleep. Look for disk I/O stalls (`iostat`), not CPU hogs.
4. **Full disk, "can't fork"** — a surprising one: `fork()` can fail not just from memory pressure but because logging/temp-file writes fail when disk is full, and some allocation paths need disk-backed swap or scratch space. Confirm with `df -h` before chasing a red herring in application code.
5. **DNS broken for one specific service** — same-namespace calls work, cross-namespace or external calls don't (or vice versa) → points at search-path/`ndots` behavior or a specific record, not a cluster-wide DNS outage. See the CoreDNS section in `topics/kubernetes-internals.md` for the full mechanism.

### General-purpose diagnostic commands and what they tell you
| Tool | Use it for |
|---|---|
| `ps aux`, `top`, `pidstat` | Per-process CPU/memory, and process state (watch for `D`). |
| `vmstat` | System-wide memory, swap, and CPU-wait breakdown at a glance. |
| `iostat` | Disk I/O throughput/latency — confirms or kills an I/O-wait hypothesis. |
| `lsof` | What files/sockets a process (or a port) has open — great for "who's holding this file/port." |
| `df` / `du` | Disk space at the filesystem level (`df`) vs directory/file level (`du`). |
| `netstat` / `ss` | Legacy vs modern socket/connection inspection. Prefer `ss`. |
| `strace` | Syscall-level trace when a process is stuck and you don't know why. |

### Clarifying questions to ask before touching a keyboard, in any incident
1. What changed recently? (deployments, node upgrades, config/infra changes, cert rotations)
2. When did this start, exactly — and does that correlate with a change?
3. Has this happened before? Recurring issues have patterns.
4. What's the blast radius — one host/pod, one service, one namespace, everything?
5. Any upstream/downstream services affected?
6. Who made the last change, and what was it?

And before running anything: **(1)** Is this live or historical? **(2)** Am I looking for symptoms or root cause? **(3)** Is this CPU, memory, I/O, network, or application-level? **(4)** What's the lowest-cost, highest-signal command to start with?
