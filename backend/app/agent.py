"""
The self-healing loop.

    generate → run in sandbox → if it fails, diagnose + patch → retry

Each step yields an AgentEvent so the API layer can stream the whole loop to
the UI in real time.
"""
import re
from typing import AsyncIterator

from .config import get_settings
from .inference import VultrInference
from .models import AgentEvent, ExecResult
from .sandbox import Sandbox

SYSTEM_PROMPT = """You are a careful Python engineer working inside a locked-down sandbox.
The sandbox has NO network access and only the standard library plus numpy, pandas, and matplotlib.
Write a COMPLETE, self-contained Python 3.11 script that accomplishes the user's task.
The script must print its result to stdout so the outcome is observable.
If you must produce a chart, save it to /tmp and print the path.
Return ONLY the code inside a single ```python fenced block. No prose."""

PATCH_PROMPT = """The previous script failed in the sandbox. Here is what happened.

--- CODE (attempt {attempt}) ---
{code}

--- STDOUT ---
{stdout}

--- STDERR / ERROR ---
{stderr}

Diagnose the failure in ONE short sentence, then provide a corrected COMPLETE script.
Respond in exactly this format:

DIAGNOSIS: <one sentence>
```python
<full corrected script>
```"""


def _extract_code(text: str) -> str:
    """Pull the first fenced code block; fall back to the raw text."""
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return (m.group(1) if m else text).strip()


def _extract_diagnosis(text: str) -> str:
    m = re.search(r"DIAGNOSIS:\s*(.+)", text)
    return m.group(1).strip() if m else "Patching based on the error output."


def _looks_successful(result: ExecResult) -> bool:
    return (
        result.exit_code == 0
        and not result.timed_out
        and not result.killed_oom
    )


class SelfHealingAgent:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.sandbox = Sandbox()

    async def run(self, task: str, starting_code: str | None = None) -> AsyncIterator[AgentEvent]:
        self.sandbox.ensure_image()
        llm = VultrInference()
        max_attempts = self.settings.max_attempts

        try:
            # ── Attempt 1: generate (or use provided code) ──
            if starting_code and starting_code.strip():
                code = starting_code.strip()
                yield AgentEvent(type="status", attempt=1,
                                 message="Starting from the code you provided.")
            else:
                yield AgentEvent(type="status", attempt=1,
                                 message="Asking Vultr Inference to write the first version…")
                raw = await llm.chat([
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": task},
                ])
                code = _extract_code(raw)

            for attempt in range(1, max_attempts + 1):
                yield AgentEvent(type="code", attempt=attempt, code=code,
                                 message=f"Attempt {attempt}: running in sandbox.")

                result = self.sandbox.run(code)
                yield AgentEvent(type="exec", attempt=attempt, result=result,
                                 message=_verdict_line(result))

                if _looks_successful(result):
                    yield AgentEvent(type="done", attempt=attempt, success=True,
                                     code=code, result=result,
                                     message=f"Solved on attempt {attempt}. Sandbox stayed contained throughout.")
                    return

                if attempt == max_attempts:
                    yield AgentEvent(type="done", attempt=attempt, success=False,
                                     code=code, result=result,
                                     message=f"Gave up after {max_attempts} attempts — "
                                             f"but every failure was absorbed by the sandbox.")
                    return

                # ── Heal: diagnose + patch ──
                yield AgentEvent(type="status", attempt=attempt,
                                 message="Feeding the error back to Vultr Inference for a patch…")
                raw = await llm.chat([
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": task},
                    {"role": "assistant", "content": f"```python\n{code}\n```"},
                    {"role": "user", "content": PATCH_PROMPT.format(
                        attempt=attempt, code=code,
                        stdout=result.stdout or "(empty)",
                        stderr=result.stderr or "(empty)",
                    )},
                ])
                yield AgentEvent(type="diagnosis", attempt=attempt,
                                 message=_extract_diagnosis(raw))
                code = _extract_code(raw)
        finally:
            await llm.aclose()


def _verdict_line(r: ExecResult) -> str:
    if r.timed_out:
        return f"⏱ Timed out and was killed ({r.duration_ms} ms). Host untouched."
    if r.killed_oom:
        return f"💥 OOM-killed by the memory cap ({r.duration_ms} ms). Host untouched."
    if r.exit_code == 0:
        return f"✓ Exited 0 in {r.duration_ms} ms."
    return f"✗ Exited {r.exit_code} in {r.duration_ms} ms."
