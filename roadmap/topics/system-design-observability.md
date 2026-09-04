# Worked Example — Observability Stack for a Microservices Platform

> **Prompt:** *"Design a monitoring/observability stack for a microservices platform."*
> This is a fully worked HLD answer for a classic SRE system-design prompt — read it as a script
> you could deliver out loud. The framework headers match `roadmap/system-design/hld-lld-framework.md`. Points worth defending
> cold in a live design walkthrough are marked **✅ KNOW COLD**.

---

## 0. The 30-second framing (say this first)

> "Observability is **three pillars — metrics, logs, traces** — plus alerting on top. Metrics tell me *something is wrong* and are cheap to keep long-term. Logs tell me *what* happened in detail. Traces tell me *where* in a request's path across services it went wrong. I'll design an ingest → store → query → alert pipeline for each, then talk SLOs and how the monitoring system itself fails. I'll bias toward an existing stack — Prometheus + Loki + Tempo + Grafana, or the OpenTelemetry + a vendor backend route — rather than building from scratch."

That sentence alone signals seniority: you scoped it, named the pillars, and refused to reinvent the wheel.

**✅ KNOW COLD — the three pillars and what each answers:**
| Pillar | Answers | Cardinality | Cost to retain |
|--------|---------|-------------|----------------|
| **Metrics** | "Is it broken? By how much, over time?" | Low (aggregated numbers) | Cheap → keep months |
| **Logs** | "What exactly happened in this event?" | High (every line) | Expensive → keep days/weeks |
| **Traces** | "Where in the request path, across N services, did latency/errors come from?" | High → **sampled** | Expensive → sample |

---

## 1. Clarify (≈2 min) — ask before you draw

Jumping to architecture without this is the #1 red flag. Ask 3–4 of these, then state your assumptions:

- **Scale:** How many services? Hosts/pods? Roughly what request volume? *(Drives the back-of-envelope.)*
- **Who consumes it?** On-call engineers, dashboards for leadership, or both?
- **Build vs buy?** Self-hosted (Prometheus/Grafana) or managed (Datadog/Grafana Cloud)? Most orgs do a mix.
- **Retention & compliance:** How long must we keep metrics vs logs? Any PII/audit-log rules?
- **What's the SLO posture?** Are we already on error budgets, or is this greenfield?
- **Multi-tenancy / multi-region?** Do teams need isolated views?

**State assumptions out loud so you can proceed:**
> "I'll assume ~200 microservices on Kubernetes, ~50k requests/sec aggregate, self-hosted-first with a managed escape hatch, on-call engineers as primary users, 13-month metric retention for capacity trends, 14-day log retention. Multi-tenant by team."

**✅ KNOW COLD:** the *reason* you clarify is that observability cost and design are dominated by **cardinality and retention**, and those are policy questions, not engineering ones. You can't size the system until you know them.

---

## 2. Back-of-envelope (≈3 min) — show you can size it

Keep it rough. The point is feasibility instinct, not precision.

**Metrics (Prometheus model):**
- 200 services × ~10 pods × ~200 time series each ≈ **~400k active series**. (A "series" = a unique metric + label-set, e.g. `http_requests_total{service=x,code=500,...}`.)
- Scrape every 15s. ~400k series × ~2 bytes/sample (compressed) → roughly **~50 GB/month** raw-ish. Comfortably one beefy Prometheus or a small sharded setup.
- **The real risk isn't volume, it's cardinality.** One bad label (`user_id`, `request_id`, raw URL with IDs) multiplies series into the millions and OOMs Prometheus. *Call this out — it's the SRE tell.*

**Logs:**
- 50k req/s × ~1 log line/req × ~1 KB ≈ **50 MB/s ≈ ~4 TB/day** if you log everything. This is why you **sample, level-filter (drop DEBUG in prod), and set short retention**. Logs are the expensive pillar.

**Traces:**
- 50k req/s fully traced is absurd to store. **Sample** — e.g. head-sample 1%, or tail-sample to keep all errors/slow traces. ~500 traces/s stored is sane.

**✅ KNOW COLD — the one-liner conclusion:** *"Metrics are cheap and bounded unless cardinality explodes; logs and traces are firehoses, so I control them with sampling, filtering, and retention. Sizing observability is really about controlling cardinality and volume, not raw throughput."*

---

## 3. High-level architecture (≈5 min) — the layered pipeline

Every pillar has the same shape: **instrument → collect/agent → store → query/visualize → alert.** Draw it as columns.

```
                       ┌─────────────────────────────────────────────┐
   App / service       │   Instrumentation (libraries in each svc)    │
   (200 microsvcs)     │   metrics: client lib  | logs: stdout JSON   │
                       │   traces: OpenTelemetry SDK                   │
                       └───────────────┬──────────────────────────────┘
                                       │
                    ┌──────────────────┼───────────────────┐
                    ▼                  ▼                   ▼
              METRICS              LOGS                 TRACES
        ┌──────────────┐   ┌──────────────────┐  ┌──────────────────┐
 AGENT  │ Prometheus    │   │ Fluent Bit /      │  │ OTel Collector    │
        │ (scrape /     │   │ Promtail (node    │  │ (receives spans,  │
        │  metrics)     │   │  agent, tails     │  │  batches, samples)│
        │  + exporters  │   │  container stdout)│  │                   │
        └──────┬───────┘    └────────┬─────────┘  └────────┬─────────┘
               ▼                     ▼                      ▼
 STORE   ┌──────────┐         ┌──────────┐           ┌──────────┐
         │ Prom TSDB │         │ Loki /   │           │ Tempo /  │
         │ (+ Thanos │         │ Elastic  │           │ Jaeger   │
         │  / Mimir  │         │  / OpenS │           │          │
         │  for long │         │          │           │          │
         │  term)    │         │          │           │          │
         └────┬─────┘          └────┬─────┘           └────┬─────┘
              └──────────────┬──────┴───────────┬──────────┘
                             ▼                  ▼
 QUERY/VIZ            ┌─────────────┐    ┌──────────────┐
                      │  Grafana    │    │ Alertmanager │ ◀── Prometheus
                      │ (dashboards,│    │ (dedupe,     │     alert rules
                      │  explore,   │    │  route,      │
                      │  correlate) │    │  silence)    │──▶ PagerDuty / Slack
                      └─────────────┘    └──────────────┘
```

**The flow in words:**
1. **Instrument:** each service exposes a `/metrics` endpoint (pull model), writes **structured JSON logs to stdout**, and emits **traces via the OpenTelemetry SDK**.
2. **Collect:**
   - Metrics — **Prometheus scrapes** `/metrics` every 15s (pull). It discovers targets via Kubernetes service discovery.
   - Logs — a **node-level agent** (Fluent Bit / Promtail) tails container stdout and ships to the log store. *Apps should never write log files or ship logs themselves — the platform does it.*
   - Traces — the **OTel Collector** receives spans, batches, samples, and forwards.
3. **Store:** Prometheus TSDB (+ Thanos/Mimir for long-term & global query); Loki/Elasticsearch for logs; Tempo/Jaeger for traces.
4. **Query/visualize:** **Grafana** as the single pane of glass over all three — and the killer feature is **correlation** (jump from a metric spike → the traces in that window → the logs for that trace via shared `trace_id`).
5. **Alert:** Prometheus evaluates alert rules → **Alertmanager** dedupes/groups/routes → PagerDuty/Slack.

**✅ KNOW COLD — pull vs push:**
- **Prometheus = pull** (it scrapes targets). Pros: Prometheus controls load, easy to tell if a target is *down* (scrape fails = `up == 0`), no app-side buffering. Cons: needs service discovery; awkward for short-lived/batch jobs → use the **Pushgateway** for those.
- **Logs/traces = push** (agents/SDKs send data out). Makes sense — they're event streams, not numbers you sample on a clock.
- Be ready to say *why* each pillar uses the model it does.

**✅ KNOW COLD — OpenTelemetry (OTel):** the vendor-neutral standard for instrumenting metrics/logs/traces. **The point is decoupling:** instrument your code once against OTel, and you can swap the backend (Tempo today, Datadog tomorrow) without touching app code. Mentioning OTel signals you're current.

---

## 4. Deep dive — pick 2 components (≈10 min)

The framework says deep-dive *two*. Pick the two with the richest SRE tradeoffs: **(A) the metrics store at scale** and **(B) the alerting pipeline.**

### Deep dive A — Metrics storage & scaling (Prometheus → Thanos/Mimir)

**The problem:** a single Prometheus is one box — limited by its RAM/disk, no HA, and data dies with the node. At 200 services that breaks.

**How it scales (know this progression):**
1. **Single Prometheus** — fine to start. Local TSDB, 15-day retention.
2. **Functional sharding / HA pairs** — run two identical Prometheis (HA) or shard by team/namespace. Now you have multiple data silos and no unified view.
3. **Thanos or Mimir** on top — gives you:
   - **Long-term storage** by shipping TSDB blocks to **object storage (S3)** — cheap, durable, near-infinite retention.
   - **Global query view** across all shards (Thanos Querier fans out).
   - **Deduplication** of the HA pairs.
   - **Downsampling** for fast long-range queries (you don't need 15s resolution for a 1-year graph).

**The tradeoff to state:** more moving parts and operational cost vs. HA + long retention + global view. For 200 services you *need* this; for 10 services you absolutely don't (don't over-architect — say that).

**✅ KNOW COLD — the cardinality trap (this is THE metrics gotcha):**
> A time series is unique per label combination. Putting a high-cardinality value in a label — `user_id`, `request_id`, `email`, raw URL with IDs — creates a near-infinite number of series, blowing up memory and killing Prometheus. **Rule: labels are for bounded, low-cardinality dimensions (service, endpoint, status_code, region). High-cardinality identifiers belong in logs/traces, not metric labels.** If you say only one smart thing in this whole design walkthrough, make it this.

### Deep dive B — Alerting pipeline (the part that pages humans)

**The problem:** raw alerts are useless or harmful. Too few → you miss outages. Too many → **alert fatigue**, on-call ignores everything, real pages get lost. Alerting design *is* SRE.

**Pipeline:** Prometheus evaluates **alert rules** (PromQL expressions) → fires to **Alertmanager** → Alertmanager **groups, dedupes, silences, and routes** → notifier (PagerDuty for pages, Slack for FYI).

**✅ KNOW COLD — alert on symptoms (SLOs), not causes:**
- **Bad:** "CPU > 80%." So what? High CPU might be fine. This pages humans for non-problems.
- **Good:** "p99 latency > 500ms for 5 min" or "error rate > 1% of requests" — i.e. alert on **user-facing symptoms** tied to your SLOs. If users aren't affected, don't page.
- This is straight from the Google SRE book ("symptom-based alerting"). Naming it is a strong signal.

**✅ KNOW COLD — alert hygiene levers:**
- **`for:` duration** — only fire if the condition holds for N minutes (kills flapping).
- **Grouping** — one notification for "20 pods of service X down," not 20 pages.
- **Severity routing** — `page` (wake someone) vs `ticket`/`warning` (Slack, look at it tomorrow). **Not everything deserves a 3am page.**
- **Silences / inhibition** — suppress downstream alerts when the upstream cause already fired (e.g. node down → don't also page for every pod on it).
- **Runbook link in every alert** — the alert should tell the responder what to check first.

**The tradeoff:** sensitivity vs noise. Tight thresholds catch more but page more. You tune with error budgets — page hard when you're burning budget fast, ticket when slow (**multi-window burn-rate alerts**: page on fast burn, ticket on slow burn).

---

## 5. Failure modes & SLOs (≈5 min) — where SRE instinct shows up most clearly

Most people design the happy path and stop. Don't.

### 5a. "Who watches the watchmen?" — monitoring the monitoring

**✅ KNOW COLD — the single most important failure-mode point:** *The observability stack must not share fate with the thing it observes, and it must not silently die.*

- **If Prometheus dies, you go blind — and worse, alerts stop firing, so it looks calm.** Defense: a **dead-man's-switch** alert — a rule that *always* fires; if the page *stops* arriving, the pipeline is broken. (Alertmanager → an external watchdog like Dead Man's Snitch.)
- **Don't host monitoring on the same cluster/region it monitors.** If the cluster goes down, your monitoring goes down with it exactly when you need it. Run it separately (or meta-monitor it from outside).
- **Cascading failure risk:** a flood of logs/metrics during a big incident can overload the observability backend right when it matters most. Defenses: **rate-limit/backpressure at the agents, sampling, and resource isolation** so observability can't take down (or be taken down with) prod.

### 5b. Per-component failure modes (rapid-fire — shows breadth)

| Component | Failure | Mitigation |
|-----------|---------|------------|
| Prometheus | OOM from cardinality explosion | Cardinality limits, recording rules, sharding |
| Prometheus | Single node dies → data loss | HA pair + remote-write to Thanos/Mimir + S3 |
| Log agent | Backpressure, can't keep up | Buffer + drop oldest / sample; never block the app |
| Log store | Disk fills (logs are huge) | Retention policy, index lifecycle mgmt, alert on store disk |
| Alertmanager | Down → no pages fire | Run it HA (clustered, ≥2); dead-man's-switch catches total failure |
| Trace backend | Storage blows up | Sampling (head + tail); short retention |
| Grafana | Down | It's read-only/stateless-ish; HA replicas; not on the page path so lower severity |

### 5c. SLOs — define them crisply (don't hand-wave)

**✅ KNOW COLD — the vocabulary, used correctly:**
- **SLI (Indicator):** the *measurement* — e.g. *"proportion of HTTP requests served < 300ms"* or *"proportion of successful (non-5xx) requests."*
- **SLO (Objective):** the *target* for the SLI — e.g. *"99.9% of requests succeed over a rolling 28 days."*
- **SLA (Agreement):** the *contract* with consequences (refunds/penalties) — usually looser than the SLO. Internal monitoring targets the **SLO**, not the SLA.
- **Error budget:** `100% − SLO`. At 99.9%, you may "fail" 0.1% → **~43 min/month** of allowed badness. **It's a budget you spend** — burn it slow on risk-free days, and when it's exhausted you freeze risky deploys and prioritize reliability. This reframes reliability vs velocity as a *number*, not an argument. *This is the most Google/SRE thing you can say.*

> **The "four golden signals" — name them as your default SLI menu:** **Latency, Traffic, Errors, Saturation.** (Google SRE book.) For most services, SLOs on latency + errors are the core.

---

## 6. Tradeoffs & wrap (≈2 min) — no design is free

Close by naming weaknesses honestly — this is what separates a strong design answer from a shallow one.

- **Build vs buy:** Self-hosted (Prometheus/Grafana/Loki/Tempo) = no per-host vendor bill, full control, but **you operate it** (it's a real ops burden at scale). Managed (Datadog/Grafana Cloud/Honeycomb) = fast, less toil, but **gets very expensive at high cardinality/volume** and is lock-in. Pragmatic real answer: *self-host metrics (cheap, high-volume), consider managed for traces/long-tail.*
- **Metrics vs logs vs traces budget:** can't keep everything forever. Metrics long (cheap, trend/capacity), logs short (expensive), traces sampled. This is a deliberate cost allocation, not an accident.
- **Cardinality vs insight:** more labels = more query power = more cost/risk. Constant tension; govern it.
- **Push vs pull:** chose pull for metrics (knows when targets vanish), push for logs/traces (event streams).
- **Sampling tradeoff:** sampling traces saves money but you *might* miss the one trace you needed → tail-sampling (keep all errors/slow) mitigates but is more complex.

**Closing line:**
> "So: a three-pillar pipeline — Prometheus+Thanos for metrics, Loki/Elastic for logs, Tempo/Jaeger for traces, unified in Grafana, OpenTelemetry for instrumentation, symptom-based SLO alerting through Alertmanager. The two things I'd defend hardest: **govern cardinality**, and **make sure the monitoring can't fail silently** — a dead-man's switch and out-of-band hosting. I'd start simple — single Prometheus + Grafana — and only add Thanos/sharding when scale demands it."

---

## TL;DR — the 8 things to be able to say cold

1. **Three pillars:** metrics (is it broken?), logs (what happened?), traces (where in the path?). Metrics cheap/long, logs expensive/short, traces sampled.
2. **Pipeline shape per pillar:** instrument → collect/agent → store → query (Grafana) → alert (Alertmanager). Same shape, three times.
3. **Pull (Prometheus, scrapes `/metrics`) vs push (logs/traces).** Know *why* each.
4. **Cardinality trap:** never put `user_id`/`request_id`/raw-URL in a metric label. High-cardinality IDs go in logs/traces. ← say this and you sound senior.
5. **Scaling metrics:** single Prom → HA/shard → Thanos/Mimir (S3 long-term, global query, dedupe, downsample). Don't add it until scale needs it.
6. **Alert on symptoms (SLOs), not causes.** Latency/error-rate, not CPU%. Tune with `for:`, grouping, severity routing, runbook links — avoid alert fatigue.
7. **Failure mode that wins the round:** monitoring must not fail silently or share fate with prod → **dead-man's switch** + host it out-of-band.
8. **SLI / SLO / SLA / error budget** — define each precisely; four golden signals = **Latency, Traffic, Errors, Saturation**.

> **If you only memorize three phrases:** *"govern cardinality," "alert on symptoms not causes," "who watches the watchmen — dead-man's switch."* Those three are the difference between a generic answer and an SRE answer.
