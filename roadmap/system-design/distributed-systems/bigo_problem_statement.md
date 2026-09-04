
# Big(O) 2025 Problem Statement

## Scenario

On the distant moon of **Pandora**, humanity operates **seven advanced data centers** that store and retrieve scientific research data.

Researchers at the **Central Research Station** must be able to access and update data instantly.

However Pandora is hostile:

- Electromagnetic storms
- Seismic activity
- Na’vi disruptions
- Resource scarcity

At any moment **up to 40% of the network could fail**.

The system must still function **without data loss with only 60% capacity (4 nodes healthy)**.

Your task is to design a **resilient in‑memory key‑value data store** capable of:

- Surviving catastrophic failures
- Dynamically balancing incoming requests
- Ensuring **zero data loss**

---

# Implementation Details

## Data Specification

Data is stored **against a key**.

### Key

`location_id` represents a **research station or sensor site**.

Example:

```json
{
  "location_id": "PAND-67892"
}
```

Constraints:

- Length **< 12**
- Second half after hyphen can be **alphanumeric (case insensitive)**

Example:

```
PAND-asd2f
```

---

## Value / Data Payload

Sensor data stored for each location.

```json
{
  "id": "uuid4 value",
  "modification_count": 5,
  "seismic_activity": 4.8,
  "temperature_c": 50.2,
  "radiation_level": 215.3
}
```

Notes:

- `modification_count` must be **maintained by the datastore**
- It **will not be included in incoming payloads**

Field constraints:

| Field | Description |
|------|-------------|
| seismic_activity | Float between **0‑10**, typically **0‑1** |
| temperature_c | Positive float |
| radiation_level | Float **> 0** |
| decimal precision | **1 decimal point** |

---

# API Specification

Each data hub exposes **HTTP endpoints**.

---

## GET /<LOCATION_ID>

Retrieve stored data.

### Success

**HTTP 200**

```json
{
  "id": "3049e4b1-cc5b-441e-b127-f345259b0b9b",
  "modification_count": 5,
  "seismic_activity": 4.8,
  "temperature_c": -50.2,
  "radiation_level": 215.3,
  "location_id": "PAND-4561"
}
```

### Errors

| Status | Meaning |
|------|---------|
| 404 | Data not found |
| 500 | Unexpected error |

---

## PUT /<LOCATION_ID>

Create or update a value.

### Request

```json
{
  "seismic_activity": 2.1,
  "temperature_c": -34.2,
  "radiation_level": 401.9,
  "id": "3049e4b1-cc5b-441e-b127-f345259b0b9b"
}
```

### Success

| Status | Meaning |
|------|---------|
| 201 | Resource created/updated |

### Failures

| Status | Meaning |
|------|---------|
| 507 | Insufficient storage |
| 500 | Replication failure or server error |

---

## GET /health

Health check endpoint.

| Status | Meaning |
|------|---------|
| 200 | System ready |
| 503 | Service unavailable |

---

# General Constraints

1. Teams **cannot use libraries** that:
   - Simplify communication protocols
   - Handle membership protocols
   - Automatically distribute data

2. Teams may use **any runtime or technology** but **cannot use prebuilt datastores** such as:

```
Redis
DragonflyDB
etc.
```

3. Dataset size: **~8GB**

4. Infrastructure:

- **7 EC2 machines**
- **2 vCPU**
- **4 GiB RAM each**

5. **Disk usage (EBS) is not allowed** — datastore must be **in‑memory**.

---

# Evaluation Criteria

Teams either **PASS Big(O)** or **FAIL Big(O)**.

### Pass Criteria

- **0% data loss after crashing 3 nodes (~40% of cluster)**

Only **accepted writes** are used to evaluate consistency.

---

# Winner Categories

Teams that pass Big(O) fall into categories.

### Category 1 — The Data Titans

Stored **> 7GB** of data.

### Category 2 — The Storage Strategists

Stored **4GB – 7GB** of data.

### Category 3 — The Replication Rookies

Stored **< 4GB** of data.

---

# Bonus Points

Teams are ranked using:

### Throughput

```
Points = Total cluster throughput (writes RPS)
```

### P99 Latency

```
Points = (1 / P99 latency in ms) * 1e5
```

### Total Score

```
Total = TP + P99
```

---

# Edge Case Evaluation

If **no team passes Big(O)**:

```
Points = (1 / % Data Loss) * 100
```

---

# Deliverables & Deployment

Infrastructure provisioning is handled using:

- **Terraform**
- **Ansible**

Teams must provide:

- **Docker image**
- Stored in **AWS ECR**

Each node receives two environment variables:

### CURRENT_NODE_IP

IP address of the node running the container.

### ALL_NODE_IPS

Comma-separated list of all nodes in the cluster.

Example:

```
10.0.0.1,10.0.0.2,10.0.0.3...
```

Order is **consistent across all containers**.

---

# Timeline

| Date | Event |
|-----|------|
| Feb 3 2025 | Registrations open |
| Feb 10 2025 | Problem statement release |
| Feb 24 2025 | Checkpoint 1 |
| Mar 10 2025 | Checkpoint 2 |
| Apr 7 2025 | Submissions close |
| Apr 7‑28 2025 | Team showcase |
| Apr 30 2025 | Winner announcement |

### Checkpoint 1

Teams share **progress updates**.

### Checkpoint 2

Teams submit:

- Local test results
- Surprise problem extension

---

# Evaluation Process

1. AWS infrastructure is provisioned.
2. Client waits for all nodes to return **200 from `/health`**.
3. Client begins sending **write and read requests**.
4. Writes stop when **all servers reject writes**.
5. **3 random nodes are crashed**.
6. Client reads all accepted writes to verify data integrity.

---

# Node Crash Rules

- Evaluation crashes **3 nodes at the end of writes**.
- If a node crashes earlier due to bugs, it counts toward the **40% failure limit**.

Example:

```
1 node fails during writes
→ only 2 additional nodes may fail later
```

Node failure detection uses the **/health endpoint**.

---

# Multiple Test Runs

Each solution is tested **3 times** to reduce randomness.

The **best performance metrics** determine leaderboard ranking.

---

# Throughput Calculation

Cluster throughput is determined using the **provided load testing tool**.

Teams can configure:

- Number of **virtual users**
- Test parameters

Metrics reported:

- **Requests per second (RPS)**
- **P99 latency**
