# Axiom Logging & Vector Shipper Guide

This document explains how structured logs from the SpacePoint VPS containers are shipped to **[Axiom](https://axiom.co)** using **Vector**, and how to query the resulting telemetry dashboards.

---

## 1. Architecture Overview

- **Source**: FastAPI/Uvicorn (`spacepoint-api`), ARQ worker (`spacepoint-worker`), and video transcoding worker (`spacepoint-worker-video`) emit structured JSON logs to stdout.
- **Log Enrichment** (`app/core/log_context.py`):
  - Injects `request_id`, `client_ip`, `user_label`.
  - Automatically parses `method`, `path`, and `status_code` into top-level JSON fields for Uvicorn access records.
  - Automatically measures `duration_ms` (request latency) in ASGI middleware and attaches it to access logs.
  - **Noise Filter**: Silences routine `200 OK` / `304 Not Modified` pings for `/notifications/me`, `/health`, and `/health/worker`. Errors (`4xx` / `5xx`) on these endpoints are never silenced.
- **Shipper** (`ops/vector/vector.toml`): A lightweight Vector container (~15–20 MB RAM) tails Docker logs via `/var/run/docker.sock`, unwraps the JSON, and streams them over HTTPS directly to Axiom.

---

## 2. Setting Up on the VPS

### Step 1: Configure Environment Variables
On the VPS, edit `/etc/spacepoint/env`:
```bash
sudo nano /etc/spacepoint/env
```
Append your Axiom credentials:
```env
AXIOM_TOKEN=xaat-your-ingest-token-here
AXIOM_DATASET=spacepoint
```

### Step 2: Deploy Vector
Run the automated deployment script from the project root:
```bash
sudo bash ops/deploy-vector.sh
```

This will:
1. Verify `AXIOM_TOKEN` and `AXIOM_DATASET` in `/etc/spacepoint/env`.
2. Sync `ops/vector/vector.toml` to `/etc/spacepoint/vector.toml`.
3. Pull `timberio/vector:0.43.0-alpine`.
4. Start `spacepoint-vector` with `--restart unless-stopped`.

### Step 3: Verify Vector Logs
```bash
docker logs -f spacepoint-vector
```
You should see:
```text
Vector has started.
```
As traffic hits the site, batches will stream to your Axiom dataset.

---

## 3. Useful Axiom Dashboard Queries (APL)

In your Axiom dataset tab, click **Query** or create a **Dashboard** using these queries:

### 1. HTTP Status Code Breakdown (Pie / Bar Chart)
```kusto
['spacepoint']
| where isnotnull(status_code)
| summarize count() by tostring(status_code)
```

### 2. Top API Routes by Request Volume
```kusto
['spacepoint']
| where isnotnull(path)
| summarize Requests=count() by method, path
| top 25 by Requests
```

### 3. P95 & Average Latency by Endpoint (APM Performance)
```kusto
['spacepoint']
| where isnotnull(duration_ms)
| summarize Avg_ms=round(avg(duration_ms), 1), P95_ms=round(percentile(duration_ms, 95), 1), count=count() by path
| top 20 by P95_ms
```

### 4. Recent Errors & Unhandled Exceptions
```kusto
['spacepoint']
| where status_code >= 400 or level in ("ERROR", "CRITICAL")
| project _time, status_code, method, path, user_label, client_ip, message, exc_info
| sort by _time desc
```

### 5. Top Active Users / Student Actions
```kusto
['spacepoint']
| where user_label != "-"
| summarize Actions=count() by user_label
| top 25 by Actions
```
