"""Request/response and event schemas."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    task: str = Field(..., description="Plain-English task, or code to fix.")
    starting_code: Optional[str] = Field(
        None, description="Optional code to start from (e.g. a broken snippet)."
    )


class ExecResult(BaseModel):
    """Raw outcome of one sandbox execution."""
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    killed_oom: bool
    duration_ms: int


EventType = Literal[
    "status",      # human-readable progress line
    "code",        # model produced code for an attempt
    "exec",        # sandbox finished running an attempt
    "diagnosis",   # model's read of the failure + plan to patch
    "done",        # final success/failure
    "error",       # orchestrator-level error
]


class AgentEvent(BaseModel):
    type: EventType
    attempt: int = 0
    message: str = ""
    code: Optional[str] = None
    result: Optional[ExecResult] = None
    success: Optional[bool] = None
