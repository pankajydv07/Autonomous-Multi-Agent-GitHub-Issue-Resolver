# Research: Distributed Worker Architecture & Reliability Features

## 1. Queue Architecture: Redis Lists vs. Redis Streams

### Decision
We will use **Redis Lists** combined with a reliable queue pattern and distributed locking, extending the existing `RedisClient` implementation.

### Rationale
- The existing codebase already uses Redis Lists (`rpush` and `blpop`) in [redis_client.py](file:///run/media/pankaj/PANKAJ/VScode/githubissue/Autonomous-Multi-Agent-GitHub-Issue-Resolver/shared/redis_client.py).
- For reliable task processing (avoiding job loss if a worker crashes), we will track the state of active tasks in a PostgreSQL table (e.g., updating the run status to `IN_PROGRESS` and tracking heartbeats) and use a Redis distributed lock. If a worker dies, its lock will expire, and a heartbeat timeout check can reclaim the task.
- This avoids adding the complexity of consumer group offset management that comes with Redis Streams, while keeping the architecture robust.

### Alternatives Considered
- **Redis Streams**: Offers native consumer groups and message safety (PEL). However, it requires significant refactoring of the current queue ingestion logic and introduces additional state tracking overhead. Given our Postgres db tracks the runs, Postgres is our source of truth for execution states, making List + Postgres state synchronization a better fit.

---

## 2. Distributed Locking Strategy

### Decision
Implement a **Redis-based Distributed Lock** using the `SET lock_key worker_id NX PX duration` command, wrapped in an asynchronous context manager within `RedisClient`.

### Rationale
- Standard industry pattern (Redlock-lite) for single-instance Redis.
- Mutual exclusion is guaranteed (via `NX` parameter).
- Deadlock prevention is built-in (via `PX` parameter setting a TTL on the lock).
- Easy to release safely by verifying that the worker releasing the lock is the one that acquired it (using a Lua script).

### Alternatives Considered
- **PostgreSQL advisory locks**: While reliable, using Redis for locking keeps memory-access performance high and avoids putting transactional/locking lock overhead on our main relational database.
- **Redlock Algorithm**: Redlock is designed for multi-instance Redis clusters. Since our deployment uses a single Redis container, a single-instance Redis lock is safe and sufficient.

---

## 3. Circuit Breaker for LLM Providers

### Decision
Implement a custom, in-memory **Circuit Breaker** class in Python. It will wrap LLM calls in [llm_client.py](file:///run/media/pankaj/PANKAJ/VScode/githubissue/Autonomous-Multi-Agent-GitHub-Issue-Resolver/shared/llm_client.py).

### Rationale
- Zero external dependencies.
- Can be configured with custom thresholds (e.g., 5 consecutive failures) and cooldown recovery periods (e.g., 60 seconds).
- It will transition between `CLOSED` (normal operation), `OPEN` (failing fast immediately without calling the LLM), and `HALF_OPEN` (testing the API with a single request to see if it has recovered).

### Alternatives Considered
- **pybreaker Library**: A popular library, but implementing it ourselves is straightforward, keeps dependencies slim, and allows us to customize the exception handling and structured logging easily.

---

## 4. Observability and Metrics

### Decision
We will use the official Python `prometheus_client` library to expose metrics on a dedicated port in the worker process. We will add a Prometheus scraper container and a Grafana instance to the `docker-compose.yml` configuration.

### Rationale
- Prometheus is the industry standard for scraping time-series performance metrics.
- Exposing a `/metrics` HTTP endpoint is lightweight and does not block worker execution.
- Grafana integrates seamlessly with Prometheus to provide real-time dashboards for queue depths, latency, and throughput.

### Alternatives Considered
- **StatsD / InfluxDB**: Requires pushing metrics instead of pulling, which introduces more configuration/setup overhead compared to Prometheus's simple pull model.
