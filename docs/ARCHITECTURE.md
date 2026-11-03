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
| No network | `network_mode="none"` | data exfiltration, SSRF, reaching the Inference key |
| No secrets | env holds only `HOME`/matplotlib hints | credential theft — there's nothing to steal |
| No host mounts | code passed as `python -I -c <code>` (≤ 64 KB) | reading/writing host files via a bind mount |
| Memory cap | `mem_limit` + `memswap_limit` | OOM bombs eating host RAM |
| CPU cap | `nano_cpus` | CPU starvation of the host |
| PID cap | `pids_limit` | fork bombs |
| Wall-clock cap | `container.wait(timeout=…)` + `kill()` | infinite loops |
| Log cap | json-file `max-size=1m` | print-floods filling the host disk |
| Read-only FS | `read_only=True` + 64 MB `noexec` tmpfs `/tmp` | tampering, `rm -rf`, dropping binaries |
| Non-root | `user=10001` | privilege use after an interpreter escape |
| Dropped caps | `cap_drop=["ALL"]`, `no-new-privileges` | kernel-capability abuse, setuid escalation |
| Lifecycle | `remove(force=True)` in `finally`; labelled leftovers purged at startup | persistence between tasks or across crashes |
| Optional gVisor | `SANDBOX_RUNTIME=runsc` | kernel exploits (user-space kernel) |

Because of all this, a task whose "solution" is `rm -rf /`, a fork bomb, or `while True: pass` simply becomes another *handled failure* that the loop reports — the host, the orchestrator, and the API key are never at risk.

## Protecting the public demo

- **Concurrency cap** — at most `MAX_CONCURRENT_RUNS` agent runs at once; extra requests get a "busy" error instead of spawning more containers.
- **Per-IP rate limit** — nginx allows ~6 runs/minute per client IP on `/api/run`.
- **Input caps** — task ≤ 8,000 chars, request body ≤ 64 KB.
- **API not exposed** — the backend binds to `127.0.0.1:8000`; the only public port is nginx on `:8080`.
- **Error hygiene** — clients see generic error messages; full exceptions go only to the server log.
- **Non-blocking orchestrator** — Docker calls run in worker threads, so one long run never stalls other users' streams.

## Known limitations (honest threat model)

- **Docker socket = host root.** The orchestrator needs `/var/run/docker.sock` to launch sandboxes, which is root-equivalent on the VM. The trust boundary is therefore *the orchestrator's own code*: it never executes model output and only creates containers with the fixed hardened config above. Stronger options: run sandboxes under gVisor (`SANDBOX_RUNTIME=runsc`), or move execution to a separate throwaway Vultr instance per task via the Vultr API.
- **Prompt injection from sandbox output.** Sandboxed code controls its own stdout/stderr, which is fed back to the model during healing. A hostile script can steer the model's next patch — but that patch also runs in the sandbox, and no secrets are in any prompt, so the blast radius stays inside the container.
- **Artifacts stay in the sandbox.** Files written to `/tmp` (e.g. charts) are destroyed with the container; returning them to the UI is a planned extension.

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
