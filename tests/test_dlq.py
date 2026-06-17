import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from shared.redis_client import RedisClient, RedisConfig

@pytest.mark.asyncio
async def test_dlq_routing_on_max_retries():
    # Setup mock client
    config = RedisConfig(host="localhost", port=6379)
    client = RedisClient(config)
    client.client = AsyncMock()
    
    # Task that has reached max retries (3/3)
    failed_payload = {
        "task": {
            "run_id": "test-run-456",
            "retry_count": 3,
            "max_retries": 3,
            "enqueue_time": "2026-06-17T10:00:00Z"
        },
        "failed_at": "2026-06-17T10:05:00Z",
        "reason": "Max retries exceeded",
        "error_details": "LLM API continuous timeout error"
    }
    
    # Enqueue to DLQ
    await client.enqueue_dlq(failed_payload)
    
    # Verify client.rpush was called with the DLQ key
    client.client.rpush.assert_called_once_with(
        "agent_tasks:dlq",
        json.dumps(failed_payload)
    )
