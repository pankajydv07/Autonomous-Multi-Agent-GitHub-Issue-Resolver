from contextlib import asynccontextmanager
import json
from typing import Any, Optional

import redis.asyncio as redis
import structlog

logger = structlog.get_logger(__name__)


class RedisConfig:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.db = db
        self.password = password


class RedisClient:
    QUEUE_KEY = "agent_tasks"
    UPDATES_CHANNEL = "agent_updates"

    def __init__(self, config: RedisConfig) -> None:
        self.config = config
        self.client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        self.client = redis.Redis(
            host=self.config.host,
            port=self.config.port,
            db=self.config.db,
            password=self.config.password,
            decode_responses=True,
        )
        await self.client.ping()
        logger.info("redis_connected", host=self.config.host, port=self.config.port)

    async def close(self) -> None:
        if self.client:
            await self.client.close()

    async def enqueue_task(self, task: dict[str, Any]) -> None:
        if not self.client:
            raise RuntimeError("Redis client not connected")
        task_json = json.dumps(task)
        await self.client.rpush(self.QUEUE_KEY, task_json)
        logger.info("task_enqueued", task_id=task.get("run_id"))

    async def dequeue_task(self, timeout: int = 0) -> Optional[dict[str, Any]]:
        if not self.client:
            raise RuntimeError("Redis client not connected")
        result = await self.client.blpop(self.QUEUE_KEY, timeout=timeout)
        if result:
            _, task_json = result
            return json.loads(task_json)
        return None

    async def publish_update(self, run_id: str, message: dict[str, Any]) -> None:
        if not self.client:
            raise RuntimeError("Redis client not connected")
        channel = f"{self.UPDATES_CHANNEL}:{run_id}"
        await self.client.publish(channel, json.dumps(message))
        logger.info("update_published", run_id=run_id, channel=channel)

    async def subscribe_to_updates(self, run_id: str) -> redis.client.PubSub:
        if not self.client:
            raise RuntimeError("Redis client not connected")
        pubsub = self.client.pubsub()
        channel = f"{self.UPDATES_CHANNEL}:{run_id}"
        await pubsub.subscribe(channel)
        return pubsub

    async def cache_set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if not self.client:
            raise RuntimeError("Redis client not connected")
        value_json = json.dumps(value)
        if ttl:
            await self.client.setex(key, ttl, value_json)
        else:
            await self.client.set(key, value_json)

    async def cache_get(self, key: str) -> Optional[Any]:
        if not self.client:
            raise RuntimeError("Redis client not connected")
        value_json = await self.client.get(key)
        if value_json:
            return json.loads(value_json)
        return None

    async def cache_delete(self, key: str) -> None:
        if not self.client:
            raise RuntimeError("Redis client not connected")
        await self.client.delete(key)

    async def acquire_lock(self, lock_key: str, val: str, ttl_ms: int) -> bool:
        if not self.client:
            raise RuntimeError("Redis client not connected")
        res = await self.client.set(lock_key, val, nx=True, px=ttl_ms)
        return bool(res)

    async def release_lock(self, lock_key: str, val: str) -> bool:
        if not self.client:
            raise RuntimeError("Redis client not connected")
        lua = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        res = await self.client.eval(lua, 1, lock_key, val)
        return bool(res)

    @asynccontextmanager
    async def lock(self, lock_key: str, val: str, ttl_ms: int):
        acquired = await self.acquire_lock(lock_key, val, ttl_ms)
        try:
            yield acquired
        finally:
            if acquired:
                await self.release_lock(lock_key, val)

    async def enqueue_dlq(self, payload: dict[str, Any]) -> None:
        if not self.client:
            raise RuntimeError("Redis client not connected")
        await self.client.rpush(f"{self.QUEUE_KEY}:dlq", json.dumps(payload))
        logger.info("dlq_enqueued", run_id=payload.get("task", {}).get("run_id"))

    async def get_queue_depth(self) -> int:
        if not self.client:
            return 0
        return await self.client.llen(self.QUEUE_KEY)

    async def get_dlq_depth(self) -> int:
        if not self.client:
            return 0
        return await self.client.llen(f"{self.QUEUE_KEY}:dlq")


def create_redis_client(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None,
) -> RedisClient:
    config = RedisConfig(host=host, port=port, db=db, password=password)
    return RedisClient(config)
