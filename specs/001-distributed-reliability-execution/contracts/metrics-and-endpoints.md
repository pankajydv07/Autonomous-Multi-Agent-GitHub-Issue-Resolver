# Interface Contracts: Metrics and Health Endpoints

This document defines the external interfaces for system observability, health checks, and metrics collection.

---

## 1. Prometheus Metrics Endpoint

The worker and orchestrator processes expose a `/metrics` scrape target at port `8000` (or as configured). The metrics format conforms to the Prometheus text-based exposition format.

### Exposed Metrics

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `active_workers` | Gauge | None | Number of running worker processes currently online. |
| `queue_depth` | Gauge | `queue_name` | Current number of pending tasks in the Redis queue/stream. |
| `dlq_depth` | Gauge | `queue_name` | Number of quarantine tasks in the Dead Letter Queue. |
| `task_processing_duration_seconds` | Histogram | `status` | Time taken to process an issue resolution run (from dequeue to completion/failure). |
| `task_queue_wait_duration_seconds` | Histogram | None | Time a task spends waiting in the queue before being dequeued by a worker. |
| `task_retry_total` | Counter | `attempt` | Cumulative number of task execution retries triggered. |
| `task_execution_total` | Counter | `status` | Cumulative number of task runs completed (values: `success`, `failure`). |
| `llm_circuit_breaker_state` | Gauge | `provider` | State of the LLM circuit breaker (`0 = CLOSED`, `1 = OPEN`, `2 = HALF_OPEN`). |
| `llm_provider_latency_seconds` | Histogram | `provider`, `status` | Latency of calls made to the LLM endpoint. |

---

## 2. Health Check Endpoint

Exposed on both the Gateway and the Orchestrator service.

### API Contract: `GET /health`

- **Port**: `8000` (Orchestrator) / `4000` (GraphQL Gateway / Health)
- **Response Type**: `application/json`

#### Successful Response (Status 200 OK)
```json
{
  "status": "healthy",
  "timestamp": "2026-06-17T10:15:00Z",
  "services": {
    "database": "up",
    "redis": "up",
    "workers": {
      "active": 3,
      "status": "nominal"
    }
  }
}
```

#### Degraded Response (Status 503 Service Unavailable)
If any critical dependency is offline:
```json
{
  "status": "unhealthy",
  "timestamp": "2026-06-17T10:15:00Z",
  "services": {
    "database": "up",
    "redis": "down",
    "workers": {
      "active": 0,
      "status": "offline"
    }
  },
  "error": "Redis connection refused"
}
```
