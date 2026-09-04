# Scripting & Coding Patterns for SRE Work

> The DSA parallel track in the roadmap (NeetCode 150 / LeetCode top-150) covers general algorithm
> patterns. This file is the narrower, SRE-flavored set: the specific small systems and scripts
> that come up disproportionately often in SRE screens, because they map directly to real
> production tooling (rate limiters, caches, log parsers, retry logic).
>
> Write these in Python first, then mirror in Go once you're comfortable — that's the "Go learning"
> parallel track in practice.

---

## The habits that matter more than the code

- **Clarify the constraint before writing a line:** in-place? O(n) time? Bounded memory? Thread-safe? These change the right answer.
- **Narrate as: approach → edge cases → complexity.** Edge cases get probed hard in any real review — empty input, single element, all-duplicate input, capacity-zero, etc.
- **Clarity over cleverness.** A readable, correct solution beats a dense one-liner that's hard to reason about under time pressure.
- **Use `logging`, not `print`, and generators over building giant lists** when narrating "production-safe" style — these are cheap signals that you write code meant to run unattended, not just once.

---

## Log parsing and aggregation

The most commonly reported SRE scripting question: parse a log file, extract structured fields, aggregate, and emit a summary.

- **Core toolkit:** `re` for pattern extraction, `collections.Counter` for frequency counts, plain dict accumulation for grouped stats (e.g. per-minute buckets).
- **Must skip malformed lines without crashing** — real logs always have some garbage lines; a regex that doesn't match should be a `continue`, not an exception.
- **Common asks layered on top of basic parsing:**
  - Top-N IPs by 5xx count.
  - Requests-per-minute (or per-status-code) time-bucketed histogram.
  - Error rate per time bucket (`errors / total`, rounded).
  - Emit the summary as JSON or CSV, sorted deterministically (e.g. by time).
- **Generators for large files:** read and `yield` one parsed record at a time instead of building a full list in memory — the difference between a script that works on a 10MB log and one that works on a 10GB log.

## Retry with exponential backoff + jitter

A resilience pattern that shows up as both an LLD question and a live-coding question.

- **Mechanism:** on attempt `n` (starting at 0), wait roughly `base_delay * 2**n` seconds before the next retry, capped at some `max_delay` so it doesn't grow unbounded.
- **Jitter is not optional:** add randomness to the delay so that many clients retrying the same failure don't all retry in lockstep and re-cause the overload they're backing off from.
- **On success:** return immediately. **On exhaustion:** re-raise the last exception — don't silently swallow a permanent failure.
- **Narrate it as:** "this is what stops a transient blip from turning into a thundering-herd retry storm against a service that's already struggling."

## Rate limiting — token bucket

The canonical LLD-and-live-coding rate limiter.

- **The question it answers per request:** "is this allowed right now?"
- **Mechanism:** tokens refill at a fixed rate (the sustained limit) up to a max capacity (the burst it tolerates); each request costs 1 token (or more); no token available → reject.
- **Lazy refill, not a background timer:** on each call, compute how many tokens have dripped in since the last access — `tokens = min(capacity, tokens + elapsed * rate)` — rather than running a separate ticking thread.
- **Use a monotonic clock** (`time.monotonic()` in Python), never wall-clock time, since wall-clock can jump backward (NTP adjustment, DST) and silently break the math.
- **Natural follow-up progression (expect to be asked for these live):**
  1. Make it thread-safe — the lock must wrap the *entire* check-and-decrement sequence together, not just the decrement (otherwise it's a check-then-act race — TOCTOU).
  2. Make it per-client — one bucket per API key/IP, e.g. via a `defaultdict`.
  3. Reimplement as a sliding window instead — more precise, different tradeoff (O(n) memory to track individual request timestamps vs O(1) for token bucket).

## LRU (and LRU+TTL) cache

Extremely common, and a natural "now make it thread-safe / now add TTL" extension to ask for on the spot.

- **Both operations must be O(1):** `get(key)` returns the value if present (and counts as a "use," making the key most-recently-used) or `-1`/`None` if absent; `put(key, value)` inserts or updates, evicting the least-recently-used entry first if at capacity.
- **Standard approach:** a dict mapping key → node for O(1) lookup, plus a doubly linked list to track usage order (MRU at one end, LRU at the other). On any touch, move the node to the MRU end; on eviction, pop the LRU end and delete it from the dict.
- **The edge-case trick:** use two sentinel/dummy nodes (`head`, `tail`) that always exist — real entries live between them, so insert/remove never has to null-check a neighbor.
- **TTL extension:** store an expiry timestamp per entry; check it on `get` (and optionally sweep lazily) so entries expire even without an explicit eviction trigger.

## Top-K from a stream

The streaming cousin of "Kth largest" — the shape behind most SRE dashboards and alerts (top-K talkers by bandwidth, top-K endpoints by error count, hot-key/noisy-neighbor detection, slowest queries by p99).

The core insight: the stream doesn't fit in memory and doesn't end, so you can't sort it — you maintain the answer incrementally as elements arrive. There are **two distinct problems** hiding under one name — know which one you're being asked:
- **(A) Top-K by value** — the K largest values seen so far (e.g. "Kth largest in a stream"). A min-heap of size K: push each new value, and whenever the heap exceeds size K, pop the smallest. O(log k) per element.
- **(B) Top-K by frequency** — the K *most frequent* items (e.g. hottest cache keys). A hashmap of counts plus a heap over the counts; at real scale (too many distinct keys to count exactly), this is where a Count-Min Sketch or similar probabilistic structure takes over.

## Concurrent health checker / bounded port scanner

- **The trap:** spawning one thread/task per target with no limit will exhaust file descriptors or overwhelm the target concurrently.
- **The fix:** bounded concurrency — a semaphore or a fixed-size worker pool — so you control how many checks are in flight at once regardless of how many targets there are.

## REST API fetch-and-aggregate

Given an API returning JSON by ID (or a paginated list), retrieve and process results.

- **The SRE-flavored extensions that turn this from a toy into a real answer:** retries (with backoff — see above), pagination handling, and graceful handling of partial failure (some IDs fail — do you fail the whole batch, or return partial results with the failures logged/reported separately?).

## Config rollback script

- **The requirements that matter:** atomicity (the rollback either fully applies or doesn't touch anything — no half-applied state) and idempotency (running it twice has the same effect as running it once).

## File/directory traversal with size rollups

- A `du`-style DFS: walk a directory tree, summing file sizes up through each directory, without loading the whole tree into memory unnecessarily. Tests whether you reach for recursion/an explicit stack cleanly and handle symlinks/permission errors without crashing the whole traversal.
