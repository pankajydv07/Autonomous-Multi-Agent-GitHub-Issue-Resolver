import asyncio
import datetime
import json
import os
import signal
import sys
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from prometheus_client import start_http_server

# Import main to reuse graph structure and configure its globals
import main
from shared.llm_client import create_llm_client, CircuitBreakerError
from shared.redis_client import create_redis_client
from shared.metrics import (
    REGISTRY,
    active_workers,
    queue_depth,
    dlq_depth,
    task_processing_duration,
    task_queue_wait_duration,
    task_retry_total,
    task_execution_total,
    llm_circuit_breaker_state,
)
from src.state import AgentState, RunStatus

logger = structlog.get_logger(__name__)

# Unique ID for this worker instance
worker_id = f"worker-{uuid.uuid4()}"

# Graceful shutdown event
shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    logger.info("received_shutdown_signal", signal=sig, worker_id=worker_id)
    shutdown_event.set()

async def process_task(task_payload: dict, orchestrator) -> None:
    run_id = task_payload["run_id"]
    retry_count = task_payload.get("retry_count", 0)
    max_retries = task_payload.get("max_retries", 3)
    enqueue_time_str = task_payload.get("enqueue_time")

    lock_key = f"lock:run:{run_id}"
    lock_ttl_ms = 600000  # 10 minutes

    # Try to acquire distributed lock
    acquired = await main.redis_client.acquire_lock(lock_key, worker_id, lock_ttl_ms)
    if not acquired:
        logger.warn("task_already_locked", run_id=run_id, worker_id=worker_id)
        return

    logger.info("lock_acquired", run_id=run_id, worker_id=worker_id)
    start_time = datetime.datetime.utcnow()

    # Track queue wait time
    if enqueue_time_str:
        try:
            enqueue_time = datetime.datetime.fromisoformat(enqueue_time_str)
            wait_time = (start_time - enqueue_time).total_seconds()
            task_queue_wait_duration.observe(wait_time)
        except Exception as e:
            logger.warn("failed_to_parse_enqueue_time", error=str(e))

    try:
        # Load state from Redis
        state_key = f"run:state:{run_id}"
        state_json = await main.redis_client.cache_get(state_key)
        
        if state_json:
            state = AgentState.model_validate(state_json)
        else:
            # Fallback if state was not initialized in Redis
            state = AgentState(
                run_id=run_id,
                issue=task_payload.get("issue", "Unknown Issue"),
                repo_url=task_payload.get("repo_url", "")
            )

        state.status = RunStatus.RUNNING
        state.add_log("worker", f"Started processing on worker: {worker_id}")
        await main.redis_client.cache_set(state_key, state.model_dump())

        # Execute Graph
        result = await orchestrator.execute(state)

        # Save back to Redis
        await main.redis_client.cache_set(state_key, result.model_dump())
        
        if result.status == RunStatus.COMPLETED:
            task_execution_total.labels(status="success").inc()
            logger.info("task_completed_successfully", run_id=run_id)
        else:
            # If the graph reported failure, raise exception to trigger retry
            raise RuntimeError(result.error or "Graph execution finished with FAILED status")

    except Exception as e:
        logger.exception("task_execution_failed", run_id=run_id, error=str(e))
        task_execution_total.labels(status="failure").inc()

        # Handle Retries
        if retry_count < max_retries:
            next_retry = retry_count + 1
            task_retry_total.labels(attempt=str(next_retry)).inc()
            
            # Calculate backoff
            backoff_delay = 1.0 * (2.0 ** retry_count)
            logger.info("scheduling_retry", run_id=run_id, next_attempt=next_retry, delay_seconds=backoff_delay)
            
            # Wait backoff delay
            await asyncio.sleep(backoff_delay)

            # Re-enqueue
            task_payload["retry_count"] = next_retry
            await main.redis_client.enqueue_task(task_payload)
        else:
            # Move to DLQ
            logger.error("max_retries_reached", run_id=run_id, max_retries=max_retries)
            dlq_payload = {
                "task": task_payload,
                "failed_at": datetime.datetime.utcnow().isoformat(),
                "reason": "Max retries exceeded",
                "error_details": str(e)
            }
            await main.redis_client.enqueue_dlq(dlq_payload)
            dlq_depth.labels(queue_name="agent_tasks").inc()

            # Update final state to FAILED
            state_key = f"run:state:{run_id}"
            state_json = await main.redis_client.cache_get(state_key)
            if state_json:
                state = AgentState.model_validate(state_json)
                state.status = RunStatus.FAILED
                state.error = f"Max retries exceeded. Last error: {str(e)}"
                state.add_log("worker", f"Execution failed after {max_retries} attempts.")
                await main.redis_client.cache_set(state_key, state.model_dump())

    finally:
        # Release distributed lock
        await main.redis_client.release_lock(lock_key, worker_id)
        logger.info("lock_released", run_id=run_id, worker_id=worker_id)

        # Record processing duration
        duration = (datetime.datetime.utcnow() - start_time).total_seconds()
        task_processing_duration.labels(status="processed").observe(duration)

async def main_loop():
    logger.info("worker_starting", worker_id=worker_id)
    
    # Setup signal handlers
    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: shutdown_event.set())
    else:
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    # Initialize clients
    main.llm_client = create_llm_client(os.environ.get("NEBIUS_API_KEY", ""))
    redis_host = os.environ.get("REDIS_HOST", "redis")
    redis_port = int(os.environ.get("REDIS_PORT", "6379"))
    main.redis_client = create_redis_client(host=redis_host, port=redis_port)
    await main.redis_client.connect()

    orchestrator = main.create_graph(main.redis_client)

    # Start Prometheus metrics exporter server
    start_http_server(8000, registry=REGISTRY)
    logger.info("metrics_server_started", port=8000)

    # Increment active workers gauge
    active_workers.inc()

    try:
        while not shutdown_event.is_set():
            # Update metrics gauges
            q_len = await main.redis_client.get_queue_depth()
            queue_depth.labels(queue_name="agent_tasks").set(q_len)

            dlq_len = await main.redis_client.get_dlq_depth()
            dlq_depth.labels(queue_name="agent_tasks").set(dlq_len)

            # Update circuit breaker metric
            if hasattr(main.llm_client, 'breaker'):
                llm_circuit_breaker_state.labels(provider="nebius").set(main.llm_client.breaker.state)

            # Dequeue next task (timeout of 1s to allow loop check)
            task_payload = await main.redis_client.dequeue_task(timeout=1)
            if task_payload:
                logger.info("task_dequeued", run_id=task_payload.get("run_id"))
                await process_task(task_payload, orchestrator)
            
            # Yield to other tasks
            await asyncio.sleep(0.1)

    except Exception as e:
        logger.exception("worker_error_in_main_loop", error=str(e))
    finally:
        active_workers.dec()
        await main.llm_client.close()
        await main.redis_client.close()
        logger.info("worker_stopped", worker_id=worker_id)

if __name__ == "__main__":
    asyncio.run(main_loop())
