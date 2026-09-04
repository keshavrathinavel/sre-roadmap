# SRE Onboarding Primer

An onboarding primer for new SREs who have already joined the role and are ramping up on
the production systems they'll own: Kubernetes, cloud infrastructure, observability, and the data
platforms sitting alongside them.

See [`CLAUDE.md`](CLAUDE.md) for the full onboarding plan, phase-by-phase breakdown, and resource
list.

## Repo structure

- `CHECKLIST.md` / `checklist.html` — flat, checkable version of every topic,
  organized by domain rather than by phase
- `roadmap/topics/` — deep-dive reference docs (Kubernetes internals, Linux & networking,
  AWS/EKS, system design/observability, data-platform streaming, scripting patterns)
- `roadmap/failure-labs/` — hands-on break-it-yourself curricula (Kubernetes, data platforms)
  with manifests and assets
- `roadmap/system-design/` — the HLD/LLD framework plus worked LLD and distributed-systems
  problems
- `roadmap/scripting-practice/` — worked Python exercises (log parsing, rate limiter, LRU/TTL
  cache, top-K stream)
