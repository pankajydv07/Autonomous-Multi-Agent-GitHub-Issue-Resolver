from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry

# Explicit collector registry to allow clean exporting
REGISTRY = CollectorRegistry()

# System Metrics
active_workers = Gauge(
    "active_workers",
    "Number of running worker processes currently online",
    registry=REGISTRY
)

queue_depth = Gauge(
    "queue_depth",
    "Current number of pending tasks in the Redis queue/stream",
    ["queue_name"],
    registry=REGISTRY
)

dlq_depth = Gauge(
    "dlq_depth",
    "Number of quarantine tasks in the Dead Letter Queue",
    ["queue_name"],
    registry=REGISTRY
)

task_processing_duration = Histogram(
    "task_processing_duration_seconds",
    "Time taken to process an issue resolution run",
    ["status"],
    registry=REGISTRY
)

task_queue_wait_duration = Histogram(
    "task_queue_wait_duration_seconds",
    "Time a task spends waiting in the queue before being dequeued",
    registry=REGISTRY
)

task_retry_total = Counter(
    "task_retry_total",
    "Cumulative number of task execution retries triggered",
    ["attempt"],
    registry=REGISTRY
)

task_execution_total = Counter(
    "task_execution_total",
    "Cumulative number of task runs completed",
    ["status"],
    registry=REGISTRY
)

llm_circuit_breaker_state = Gauge(
    "llm_circuit_breaker_state",
    "State of the LLM circuit breaker (0 = CLOSED, 1 = OPEN, 2 = HALF_OPEN)",
    ["provider"],
    registry=REGISTRY
)

llm_provider_latency = Histogram(
    "llm_provider_latency_seconds",
    "Latency of calls made to the LLM endpoint",
    ["provider", "status"],
    registry=REGISTRY
)
