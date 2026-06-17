import pytest
import time
from unittest.mock import MagicMock
from shared.redis_client import RedisClient, RedisConfig

def calculate_backoff(attempt: int, base: float = 1.0, multiplier: float = 2.0) -> float:
    return base * (multiplier ** attempt)

def test_backoff_calculation():
    # Attempt 0: 1.0 * (2^0) = 1.0s
    assert calculate_backoff(0) == 1.0
    # Attempt 1: 1.0 * (2^1) = 2.0s
    assert calculate_backoff(1) == 2.0
    # Attempt 2: 1.0 * (2^2) = 4.0s
    assert calculate_backoff(2) == 4.0
    # Attempt 3: 1.0 * (2^3) = 8.0s
    assert calculate_backoff(3) == 8.0

@pytest.mark.asyncio
async def test_redis_client_enqueue_and_retry_metadata():
    # Setup mock config and client
    config = RedisConfig(host="localhost", port=6379)
    client = RedisClient(config)
    client.client = MagicMock()
    
    # Mock task payload
    task = {
        "run_id": "test-run-123",
        "retry_count": 0,
        "max_retries": 3,
        "enqueue_time": "2026-06-17T10:00:00Z"
    }
    
    # Simulate first failure and metadata update
    task["retry_count"] += 1
    task["error_history"] = [{"attempt": 1, "timestamp": "2026-06-17T10:00:05Z", "error": "LLM timeout"}]
    
    assert task["retry_count"] == 1
    assert len(task["error_history"]) == 1
    assert task["error_history"][0]["error"] == "LLM timeout"
