import pytest
from unittest.mock import AsyncMock
from shared.redis_client import RedisClient, RedisConfig

@pytest.mark.asyncio
async def test_distributed_lock_acquisition_and_exclusion():
    # Setup mock client
    config = RedisConfig(host="localhost", port=6379)
    client = RedisClient(config)
    client.client = AsyncMock()
    
    # Mock first client set command (acquires lock)
    client.client.set.return_value = True
    
    lock_key = "lock:run:123"
    worker_1 = "worker-1"
    worker_2 = "worker-2"
    ttl = 600000
    
    # Worker 1 acquires lock
    res1 = await client.acquire_lock(lock_key, worker_1, ttl)
    assert res1 is True
    client.client.set.assert_called_once_with(lock_key, worker_1, nx=True, px=ttl)
    
    # Mock second client set command (fails to acquire lock)
    client.client.set.reset_mock()
    client.client.set.return_value = False
    
    # Worker 2 tries to acquire lock
    res2 = await client.acquire_lock(lock_key, worker_2, ttl)
    assert res2 is False
    client.client.set.assert_called_once_with(lock_key, worker_2, nx=True, px=ttl)
