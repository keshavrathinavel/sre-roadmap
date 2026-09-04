# AWS & EKS — Reference

> A concrete-detail companion to the "Cloud Security" section of the roadmap and to the
> Kubernetes topic file — this is the AWS-specific substrate underneath a lot of the K8s and
> reliability material elsewhere in this repo.

---

## IAM & security

- **Roles vs users vs policies:** users are long-lived identities (people, or legacy service credentials); roles are assumed temporarily and issue short-lived credentials — prefer roles for anything a workload does. Policies are the actual permission documents attached to either.
- **Least privilege:** grant only the specific actions/resources a workload needs, not broad wildcard access. This is a design discipline, not a checkbox — it bounds the blast radius of any single compromised credential.
- **Instance profiles:** the mechanism that lets an EC2 instance assume an IAM role without embedding credentials on the box.
- **OIDC federation:** lets an external identity provider (or Kubernetes' own OIDC-compliant service account tokens — see IRSA below) assume AWS roles without long-lived AWS credentials ever existing outside AWS.

## Networking (VPC)

- **Subnets — public vs private:** a public subnet has a route to an internet gateway; a private subnet doesn't, and reaches the internet (if at all) via a NAT gateway in a public subnet.
- **Route tables:** control which subnet's traffic goes where — the mechanism that actually makes a subnet "public" or "private."
- **Security groups vs NACLs:** security groups are **stateful** (allow the return traffic of an allowed request automatically) and attach to instances/ENIs; NACLs are **stateless** (you must explicitly allow both directions) and apply at the subnet boundary. Security groups are the day-to-day tool; NACLs are a coarser, subnet-wide backstop.
- **NAT gateway:** lets private-subnet resources reach the internet outbound (e.g. to pull a package) without being reachable inbound.
- **CIDR / subnetting basics** are covered in `topics/linux-and-networking.md` — the AWS-specific piece on top is just "which subnet range did you carve out for which tier."

## EKS specifics

- **Managed control plane:** AWS runs the API server and etcd for you, across multiple AZs — you don't operate this layer directly, but you should still be able to describe what's happening behind it (see the control-plane/data-plane split in `topics/kubernetes-internals.md`).
- **Node groups:** **managed** (AWS handles the underlying EC2 lifecycle for you), **self-managed** (you own the ASG/launch template yourself), or **Fargate** (no nodes to manage at all — pods run on serverless compute, at a cost and flexibility tradeoff).
- **VPC CNI:** EKS's default networking plugin gives pods **real VPC IP addresses** directly, rather than an overlay network. The consequence: pod IP capacity is bounded by **ENI (elastic network interface) IP-per-node density limits** — a real, recurring symptom is pods stuck in `ContainerCreating` because the node has run out of assignable IPs, not because of a scheduling or image-pull problem. Know this as a distinct failure mode from the generic `ContainerCreating` causes.
- **IRSA (IAM Roles for Service Accounts):** gives an individual Kubernetes **pod** its own scoped IAM role via OIDC federation between the cluster's OIDC provider and AWS IAM — instead of every pod on a node inheriting the node's (much broader) IAM role. This is the AWS-specific implementation of "least privilege at the pod level."
- **Cluster access control:** the `aws-auth` ConfigMap (or the newer EKS access entries API) maps AWS IAM identities to Kubernetes RBAC — this is the join point between AWS-level identity and in-cluster permissions.
- **Node autoscaling:** the Cluster Autoscaler (reactive, adds nodes when pods are unschedulable) or **Karpenter** (more flexible, provisions right-sized nodes directly rather than only scaling a fixed node group).
- **Control-plane logging:** EKS can ship control-plane component logs (API server, audit, scheduler, controller-manager) to CloudWatch — worth enabling before you need them for an incident, not during one.

## Storage — S3

- **Durability vs availability:** S3 is designed for extremely high durability (commonly cited as "eleven nines") for the *objects themselves* — that's a different guarantee from *availability* (whether a request succeeds right now). Don't conflate the two in an answer.
- **Strong read-after-write consistency:** a `GET` immediately after a successful `PUT` of the same key is guaranteed to see the new data (this used to be a real distinction to know for S3 specifically — treat it as a given now, but be ready to explain what the guarantee actually means).
- **Bucket policies, versioning, lifecycle rules:** policy = resource-based access control at the bucket level; versioning = keep prior versions of an object instead of overwriting (protects against accidental deletes/overwrites, at a storage-cost tradeoff); lifecycle rules = automatic transitions to cheaper storage tiers or expiry after N days — the mechanism behind sane log/data retention cost control.

## Messaging — SQS, SNS, Lambda

- **SQS:** a **pull**-based queue. Consumers poll for messages; **at-least-once** delivery (a message can be delivered more than once, so consumers must be idempotent); **visibility timeout** — once a consumer receives a message it becomes invisible to other consumers for a window, and if the consumer doesn't ack (delete) it in time, it becomes visible again for redelivery. That's the mechanism behind "a crashed consumer doesn't lose the message, but a slow one might get duplicate deliveries."
- **SNS:** a **push**-based pub/sub service — fan-out to many subscribers (including SQS queues, Lambda, HTTP endpoints) from one publish.
- **The SNS→SQS fan-out pattern:** publish once to SNS, have multiple SQS queues subscribed, so multiple independent consumers each get their own durable, at-least-once queue off a single event — decouples "one event happened" from "N different systems need to react to it, each at their own pace."
- **Lambda:** event-driven, serverless compute. Key operational characteristic: **cold starts** — the latency hit when a new execution environment has to be initialized for a request, which matters for latency-sensitive paths and is a real SLO consideration, not just a footnote.
- **DLQs (dead-letter queues) + idempotency:** the standard pattern for at-least-once systems — route messages that fail processing repeatedly to a DLQ for inspection instead of retrying forever or dropping them, and design consumers to be idempotent (safe to process the same message twice) since at-least-once delivery guarantees duplicates will happen eventually.

## Compute — EC2

- **Instance types:** different families trade off CPU/memory/network/storage ratios for different workload shapes (compute-optimized, memory-optimized, general purpose, etc.) — the same instinct as choosing K8s resource requests, one layer down.
- **Auto-scaling groups (ASGs) + launch templates:** ASGs keep a target number of instances running (and can scale on a metric); launch templates define what a new instance actually looks like (AMI, instance type, user data, IAM instance profile) when the ASG creates one.

## Observability — CloudWatch

Metrics, logs, and alarms are AWS's native (and often first layer of) observability — the same three-pillars thinking from `topics/system-design-observability.md` applies, just with CloudWatch as one possible backend rather than self-hosted Prometheus/Loki.

## ECS vs EKS

Pick ECS when you want AWS-native container orchestration with less operational surface area and don't need Kubernetes' portability or ecosystem; pick EKS when you need the Kubernetes API/ecosystem itself (portability across clouds, existing K8s tooling, Helm charts, operators) and are willing to own the additional complexity that comes with it.

## GCP ↔ AWS translation cheat sheet

Useful when a design prompt or a job description names the "other" cloud and the real question is whether your mental model transfers: GKE↔EKS, GCS↔S3, Dataproc↔managed Spark, Dataflow↔managed streaming, Pub/Sub↔Kafka-ish messaging, BigQuery↔the warehouse, Cloud Monitoring↔CloudWatch.
