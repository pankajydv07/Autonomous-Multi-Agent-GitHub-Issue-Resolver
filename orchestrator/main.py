import uuid
from contextlib import asynccontextmanager
import sys
from pathlib import Path

# Add project root and parent to path
sys.path.insert(0, str(Path(__file__).parent))  # orchestrator/
sys.path.insert(0, str(Path(__file__).parent.parent))  # project root

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402
import structlog  # noqa: E402

from src.graph import LangGraphOrchestrator  # noqa: E402
from src.state import AgentState, AgentProgress, RunStatus  # noqa: E402
from shared.llm_client import create_llm_client  # noqa: E402
from shared.redis_client import create_redis_client  # noqa: E402
from agents.code_reader.agent import run as code_reader_run  # noqa: E402
from agents.planner.agent import run as planner_run  # noqa: E402
from agents.code_writer.agent import run as code_writer_run  # noqa: E402
from agents.test_writer.agent import run as test_writer_run  # noqa: E402
from agents.pr_agent.agent import run as pr_agent_run  # noqa: E402

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)

logger = structlog.get_logger(__name__)


class StartRunRequest(BaseModel):
    issue: str
    repo_url: str


class RunResponse(BaseModel):
    id: str
    issue: str
    repo_url: str
    status: str
    created_at: str


runs_store: dict[str, AgentState] = {}
llm_client = None
redis_client = None
orchestrator = None


def create_graph(redis_client) -> LangGraphOrchestrator:
    graph = LangGraphOrchestrator()

    def make_progress_callback(run_id: str):
        async def progress_callback(progress: AgentProgress):
            if redis_client:
                await redis_client.publish_update(
                    run_id,
                    {
                        "agent_name": progress.agent_name,
                        "event_type": progress.event_type,
                        "content": progress.content,
                        "timestamp": progress.timestamp,
                    }
                )
        return progress_callback

    async def code_reader_node(state: AgentState) -> AgentState:
        state.set_progress_callback(make_progress_callback(state.run_id))
        return await code_reader_run(state, llm_client)

    async def planner_node(state: AgentState) -> AgentState:
        state.set_progress_callback(make_progress_callback(state.run_id))
        return await planner_run(state, llm_client)

    async def code_writer_node(state: AgentState) -> AgentState:
        state.set_progress_callback(make_progress_callback(state.run_id))
        return await code_writer_run(state, llm_client)

    async def test_writer_node(state: AgentState) -> AgentState:
        state.set_progress_callback(make_progress_callback(state.run_id))
        return await test_writer_run(state, llm_client)

    async def pr_agent_node(state: AgentState) -> AgentState:
        state.set_progress_callback(make_progress_callback(state.run_id))
        return await pr_agent_run(state, llm_client)

    graph.add_node("code_reader", code_reader_node)
    graph.add_node("planner", planner_node)
    graph.add_node("code_writer", code_writer_node)
    graph.add_node("test_writer", test_writer_node)
    graph.add_node("pr_agent", pr_agent_node)

    graph.add_edge("code_reader", "planner")
    graph.add_edge("planner", "code_writer")
    graph.add_edge("code_writer", "test_writer")
    graph.add_edge("test_writer", "pr_agent")

    return graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm_client, redis_client, orchestrator
    import os

    llm_client = create_llm_client(os.environ.get("NEBIUS_API_KEY", ""))
    redis_host = os.environ.get("REDIS_HOST", "redis")
    redis_port = int(os.environ.get("REDIS_PORT", "6379"))
    redis_client = create_redis_client(host=redis_host, port=redis_port)
    await redis_client.connect()
    orchestrator = create_graph(redis_client)

    logger.info("orchestrator_started")
    yield

    await llm_client.close()
    await redis_client.close()
    logger.info("orchestrator_stopped")


app = FastAPI(title="Agent Orchestrator", lifespan=lifespan)


from datetime import datetime
from shared.metrics import REGISTRY
from prometheus_client import generate_latest
from fastapi import Response

@app.post("/api/runs", response_model=RunResponse)
async def start_run(request: StartRunRequest):
    run_id = str(uuid.uuid4())
    state = AgentState(run_id=run_id, issue=request.issue, repo_url=request.repo_url)
    state.status = RunStatus.PENDING

    # Save state to Redis cache
    state_key = f"run:state:{run_id}"
    await redis_client.cache_set(state_key, state.model_dump())
    await redis_client.client.sadd("all_runs", run_id)

    # Enqueue task
    task_payload = {
        "run_id": run_id,
        "issue": request.issue,
        "repo_url": request.repo_url,
        "retry_count": 0,
        "max_retries": 3,
        "enqueue_time": datetime.utcnow().isoformat()
    }
    await redis_client.enqueue_task(task_payload)
    logger.info("run_enqueued", run_id=run_id)

    return RunResponse(
        id=state.run_id,
        issue=state.issue,
        repo_url=state.repo_url,
        status=state.status.value,
        created_at=state.created_at.isoformat(),
    )


@app.get("/api/runs", response_model=list[RunResponse])
async def get_runs(limit: int = 50, offset: int = 0):
    run_ids = await redis_client.client.smembers("all_runs")
    runs = []
    for r_id in run_ids:
        state_json = await redis_client.cache_get(f"run:state:{r_id}")
        if state_json:
            runs.append(AgentState.model_validate(state_json))

    runs.sort(key=lambda x: x.created_at, reverse=True)
    runs = runs[offset : offset + limit]
    return [
        RunResponse(
            id=r.run_id,
            issue=r.issue,
            repo_url=r.repo_url,
            status=r.status.value,
            created_at=r.created_at.isoformat(),
        )
        for r in runs
    ]


@app.get("/api/runs/{run_id}")
async def get_run_details(run_id: str):
    state_json = await redis_client.cache_get(f"run:state:{run_id}")
    if not state_json:
        raise HTTPException(status_code=404, detail="Run not found")
    state = AgentState.model_validate(state_json)
    return {
        "id": state.run_id,
        "issue": state.issue,
        "repo_url": state.repo_url,
        "status": state.status.value,
        "error": state.error,
        "plan": state.plan,
        "patch": state.patch,
        "tests": state.tests,
        "pr_url": state.pr_url,
        "logs": state.logs,
        "created_at": state.created_at.isoformat(),
        "updated_at": state.updated_at.isoformat(),
    }


@app.get("/api/runs/{run_id}/state")
async def get_run_state(run_id: str):
    state_json = await redis_client.cache_get(f"run:state:{run_id}")
    if not state_json:
        raise HTTPException(status_code=404, detail="Run not found")
    state = AgentState.model_validate(state_json)
    return state.model_dump()


@app.get("/api/runs/{run_id}/logs")
async def get_run_logs(run_id: str):
    state_json = await redis_client.cache_get(f"run:state:{run_id}")
    if not state_json:
        raise HTTPException(status_code=404, detail="Run not found")
    state = AgentState.model_validate(state_json)
    return state.logs


@app.post("/api/runs/{run_id}/retry")
async def retry_run(run_id: str):
    state_json = await redis_client.cache_get(f"run:state:{run_id}")
    if not state_json:
        raise HTTPException(status_code=404, detail="Run not found")

    state = AgentState.model_validate(state_json)
    state.status = RunStatus.PENDING
    state.error = None
    state.add_log("orchestrator", "Retry triggered by user")

    await redis_client.cache_set(f"run:state:{run_id}", state.model_dump())

    # Enqueue task
    task_payload = {
        "run_id": run_id,
        "issue": state.issue,
        "repo_url": state.repo_url,
        "retry_count": 0,
        "max_retries": 3,
        "enqueue_time": datetime.utcnow().isoformat()
    }
    await redis_client.enqueue_task(task_payload)
    logger.info("retry_enqueued", run_id=run_id)

    return RunResponse(
        id=state.run_id,
        issue=state.issue,
        repo_url=state.repo_url,
        status=state.status.value,
        created_at=state.created_at.isoformat(),
    )


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    state_json = await redis_client.cache_get(f"run:state:{run_id}")
    if not state_json:
        raise HTTPException(status_code=404, detail="Run not found")

    state = AgentState.model_validate(state_json)
    state.status = RunStatus.CANCELLED
    state.add_log("orchestrator", "Run cancelled by user")
    await redis_client.cache_set(f"run:state:{run_id}", state.model_dump())

    return RunResponse(
        id=state.run_id,
        issue=state.issue,
        repo_url=state.repo_url,
        status=state.status.value,
        created_at=state.created_at.isoformat(),
    )


@app.get("/health")
async def health():
    db_ok = "up"
    redis_ok = "up" if redis_client and redis_client.client else "down"
    return {
        "status": "healthy" if redis_ok == "up" else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": db_ok,
            "redis": redis_ok
        }
    }


@app.get("/metrics")
async def metrics():
    # Update quick stats before returning
    if redis_client:
        from shared.metrics import queue_depth, dlq_depth
        q_len = await redis_client.get_queue_depth()
        queue_depth.labels(queue_name="agent_tasks").set(q_len)
        dlq_len = await redis_client.get_dlq_depth()
        dlq_depth.labels(queue_name="agent_tasks").set(dlq_len)

    return Response(content=generate_latest(REGISTRY), media_type="text/plain")

