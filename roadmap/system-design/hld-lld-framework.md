# What HLD Looks Like for SRE / Platform Roles

Typical problems:

- Multi‑tenant Kubernetes platform for 50 teams
- Observability stack for large microservices architecture
- Secrets management system across environments
- CI/CD platform with rollback and canary deployments
- Distributed rate limiter
- Cloud cost attribution system
- Incident management and alerting pipeline
- Zero‑downtime deployment system

---

# HLD Framework for SRE System Design

### 1. Clarify Requirements (2–3 min)

Ask:
- scale (users / requests)
- consistency requirements
- latency SLOs
- who the clients are
- what failure looks like

Jumping straight to design is a **red flag**.

### 2. Back‑of‑Envelope Estimation (2 min)

Estimate:
- storage
- requests per second
- bandwidth

### 3. High‑Level Architecture (5 min)

Draw:
- major components
- data flow

Don't deep dive yet.

### 4. Deep Dive (10–15 min)

Focus on **2–3 components**.

Discuss tradeoffs:

- consistency vs availability
- push vs pull
- sync vs async

### 5. Failure Modes & Reliability (5 min)

What happens when each component fails?

Discuss:
- SLOs
- monitoring
- fallback strategies

This is where **SRE instinct shows up most clearly**.

### 6. Tradeoffs

No design is perfect.

Explain:
- weaknesses
- how design changes at different scales

---

# What LLD Looks Like

LLD questions typically look like:

> "Walk me through how you'd implement X in code."

You don't need full class diagrams but must demonstrate good **interfaces and abstractions**.

Problems worth knowing:

- Rate limiter (**token bucket vs sliding window**)
- Circuit breaker pattern
- Retry with exponential backoff + jitter
- Simple work queue with workers
- Leader election

---

# Resources That Are Actually Good

## HLD

- **System Design Interview — Alex Xu**
- **Exponent YouTube channel**
- Write up your **own production infrastructure** as if you had to defend every decision out loud to a new hire

## LLD

- **Refactoring Guru (refactoring.guru)**

Don't buy courses for this. These problems are learnable from **first principles**.
