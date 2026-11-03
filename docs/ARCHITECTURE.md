# Architecture

## Components

1. **React UI** (`frontend/`) — submit a task, watch the self-healing loop stream in as a timeline of attempts (code → stdout/stderr → verdict → diagnosis → retry).
2. **FastAPI orchestrator** (`backend/app/`) — the only trusted component. It:
   - calls **Vultr Serverless Inference** to generate and patch code (`inference.py`),
   - runs the **self-healing loop** (`agent.py`),
   - dispatches each attempt to a **sandbox** (`sandbox.py`),
   - streams every step to the UI as SSE (`main.py`).
3. **Sandbox** — a throwaway Docker container per execution. The orchestrator talks to the host Docker daemon via the mounted socket.

## The self-healing loop

```
generate(task) ──► code
     │
     ▼
 ┌─────────────────────────────┐
 │ run in sandbox (attempt n)  │◄──────────────┐
 └─────────────┬───────────────┘               │
               ▼                                │
         success?  ── yes ──► done ✅           │
               │ no                             │
               ▼                                │
   diagnose(stdout, stderr) ──► patch ──────────┘  (until MAX_ATTEMPTS)
```

The model is given the task, its own previous code, and the exact stdout/stderr from the sandbox, and must answer with a one-line diagnosis plus a full corrected script.

## Why the blast radius is zero

The trust boundary is explicit: **the orchestrator never executes model output**, it only *ships it to a sandbox*. Inside the sandbox, `sandbox.py` sets:

| Control | Mechanism | Defeats |
|---|---|---|
| No network | `network_disabled=True` | data exfiltration, SSRF, reaching the Inference key |
| No secrets | `environment={}` | credential theft — there's nothing to steal |
| Memory cap | `mem_limit` + `memswap_limit` | OOM bombs eating host RAM |
| CPU cap | `nano_cpus` | CPU starvation of the host |
| PID cap | `pids_limit` | fork bombs |
| Wall-clock cap | `container.wait(timeout=…)` + `kill()` | infinite loops |
| Read-only FS | `read_only=True` + tmpfs `/tmp` | tampering, `rm -rf` on mounts |
| Non-root | `user=10001` | privilege use after an interpreter escape |
| Dropped caps | `cap_drop=["ALL"]`, `no-new-privileges` | kernel-capability abuse, setuid escalation |
| Lifecycle | `remove(force=True)` in `finally` | persistence between tasks |

Because of all this, a task whose "solution" is `rm -rf /`, a fork bomb, or `while True: pass` simply becomes another *handled failure* that the loop reports — the host, the orchestrator, and the API key are never at risk.

## Data flow for one request

```
POST /api/run {task}
  → agent.run()  (async generator)
      → Inference.chat()        # Vultr Serverless Inference
      → Sandbox.run(code)       # docker run … (contained)
      → yields AgentEvent(...)  # streamed to UI as text/event-stream
```

## Extensibility

`Sandbox` is a single class with one method (`run(code) -> ExecResult`). Swap its body for a gVisor runtime, E2B, OpenSandbox, or a per-task Vultr instance via the Vultr API without touching the agent or UI.
