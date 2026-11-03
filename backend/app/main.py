"""FastAPI entrypoint: serves the self-healing agent as a streaming (SSE) API."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .agent import SelfHealingAgent
from .config import get_settings
from .inference import InferenceError
from .models import RunRequest
from .sandbox import cleanup_leftovers

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

settings = get_settings()
# Public demo protection: each run costs a container and LLM credits.
run_slots = asyncio.Semaphore(settings.max_concurrent_runs)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Lifecycle discipline: destroy sandboxes orphaned by a previous crash.
    try:
        removed = await asyncio.to_thread(cleanup_leftovers)
        if removed:
            log.info("Removed %d leftover sandbox container(s)", removed)
    except Exception:
        log.warning("Docker unavailable at startup; sandbox runs will fail until it is up")
    yield


app = FastAPI(title="Blast Radius Zero — Self-Healing Code Runner", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "model": settings.vultr_model,
        "sandbox_image": settings.sandbox_image,
        "limits": {
            "timeout_s": settings.sandbox_timeout_seconds,
            "memory": settings.sandbox_memory,
            "cpus": settings.sandbox_cpus,
            "pids": settings.sandbox_pids_limit,
            "network": "disabled",
        },
    }


def _public_error(exc: Exception) -> str:
    """Message safe to show a public user; full details go to the server log."""
    if isinstance(exc, InferenceError):
        return "The language model request failed. Please try again shortly."
    if isinstance(exc, RuntimeError) and "Sandbox image" in str(exc):
        return "The sandbox is not ready on the server."
    return "Internal error while running the agent."


def _sse_error(message: str) -> str:
    return f"data: {json.dumps({'type': 'error', 'attempt': 0, 'message': message})}\n\n"


@app.post("/api/run")
async def run(req: RunRequest) -> StreamingResponse:
    """Stream the self-healing loop as Server-Sent Events."""

    async def event_stream():
        # The slot is taken inside the generator so it is always released, even
        # if the client disconnects before streaming starts.
        if run_slots.locked():
            yield _sse_error("All sandboxes are busy. Try again in a moment.")
            return
        async with run_slots:
            try:
                async for event in SelfHealingAgent().run(req.task, req.starting_code):
                    yield f"data: {event.model_dump_json()}\n\n"
            except Exception as exc:  # orchestrator-level failure
                log.exception("Agent run failed")
                yield _sse_error(_public_error(exc))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
