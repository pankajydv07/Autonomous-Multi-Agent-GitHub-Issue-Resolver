# Quickstart Validation Guide: Distributed Workers & Reliability

This document outlines the validation procedures to verify the correctness, performance, and fault-tolerance features of the enhanced distributed execution system.

---

## 1. Prerequisites

Before running the verification scenarios, ensure your environment is set up:

1. **Docker Compose**: Installed and running on the host machine.
2. **Environment Variables**: A valid `.env` file containing:
   ```env
   DATABASE_URL="postgresql://postgres:postgres@db:5432/resolver?schema=public"
   REDIS_HOST="redis"
   REDIS_PORT=6379
   NEBIUS_API_KEY="your-nebius-key"
   GITHUB_TOKEN="your-github-token"
   ```

---

## 2. Setup and Execution Commands

### Build and Start Infrastructure
Start the database, Redis, Gateway, Orchestrator, Prometheus, and Grafana:
```bash
docker compose up --build -d
```

### Scale Worker Processes
To launch 3 concurrent worker processes:
```bash
docker compose up --build -d --scale worker=3
```

---

## 3. Verification Scenarios

### Scenario A: Concurrency & Distributed Lock Verification
1. **Action**: Submit 5 distinct issue resolution runs in rapid succession via the GraphQL gateway.
2. **Commands**:
   ```bash
   # Use curl or graphql-playground to submit runs
   curl -X POST http://localhost:4000/graphql \
     -H "Content-Type: application/json" \
     -d '{"query": "mutation { startRun(issue: \"Fix formatting bug in UI\", repoUrl: \"https://github.com/user/repo\") { id status } }"}'
   ```
3. **Expected Outcome**:
   - Check worker container logs. Tasks are processed concurrently across the 3 worker containers.
   - Search logs for `lock_acquired` and `lock_released`. Ensure no two workers process the same task ID.
   - The Gateway Dashboard or CLI shows multiple runs transitioning to `RUNNING` in parallel.

---

### Scenario B: Transient Faults and Exponential Backoff Retries
1. **Action**: Enqueue a task, then simulate transient LLM failures (e.g. inject network failures or rate limits for the first 2 attempts).
2. **Commands**:
   ```bash
   # Run local test suite simulating transient failure
   pytest tests/test_retries.py -v
   ```
3. **Expected Outcome**:
   - The worker tries to execute the task, catches the transient exception, log message reports retry attempt `#1` with an exponential delay.
   - The worker successfully retries and finishes the task on the 3rd attempt when the mock API begins returning success.
   - Prometheus metric `task_retry_total` increments by 2.

---

### Scenario C: Persistent Failures and Dead Letter Queue (DLQ)
1. **Action**: Enqueue a task with maximum retry count configured to 3, and keep the mock LLM API failing permanently.
2. **Commands**:
   ```bash
   # Run tests for DLQ processing
   pytest tests/test_dlq.py -v
   ```
3. **Expected Outcome**:
   - Worker attempts execution 3 times, logs failures, and moves the task payload to the `agent_tasks:dlq` Redis queue.
   - The database status of the corresponding run is marked as `FAILED`.
   - The metric `dlq_depth` increments to 1.

---

### Scenario D: Circuit Breaker Verification
1. **Action**: Simulate a prolonged outage of the LLM provider (5+ consecutive errors).
2. **Expected Outcome**:
   - The LLM circuit breaker trips and transitions from `CLOSED` to `OPEN`.
   - Subsequent task attempts immediately fail-fast with `CircuitBreakerOpenError` without calling the LLM API endpoint.
   - After the 60-second cooldown period, a task attempt transitions the breaker to `HALF_OPEN`.

---

### Scenario E: Graceful Worker Shutdown
1. **Action**: Trigger a task, and then send a terminate signal to the worker.
2. **Commands**:
   ```bash
   # Stop a worker container mid-run
   docker compose stop worker
   ```
3. **Expected Outcome**:
   - The worker catches `SIGTERM`.
   - Logs report: `Graceful shutdown initiated. Completing active task...`
   - The active task finishes processing and saves its state before the worker exits.
   - No new tasks are dequeued during shutdown.

---

## 4. Observability and Dashboards

### Scraping Metrics
Ensure Prometheus is scraping successfully:
```bash
curl http://localhost:8000/metrics
```

### Accessing Grafana Dashboard
1. Navigate to: `http://localhost:3000` (Grafana default port)
2. Login credentials: Admin/admin (default setup)
3. Open the **Worker Execution Dashboard** to visualize:
   - Active Workers count
   - Queue Depth (`agent_tasks` list length)
   - Task Processing Throughput
   - Circuit Breaker Status
