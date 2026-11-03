"""FastAPI entrypoint: serves the self-healing agent as a streaming (SSE) API."""
import asyncio
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .agent import SelfHealingAgent
from .config import get_settings
from .models import RunRequest

app = FastAPI(title="Blast Radius Zero — Self-Healing Code Runner")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.post("/api/run")
async def run(req: RunRequest) -> StreamingResponse:
    """Stream the self-healing loop as Server-Sent Events."""
    agent = SelfHealingAgent()

    async def event_stream():
        try:
            async for event in agent.run(req.task, req.starting_code):
                yield f"data: {event.model_dump_json()}\n\n"
                await asyncio.sleep(0)  # flush
        except Exception as exc:  # orchestrator-level failure
            err = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
