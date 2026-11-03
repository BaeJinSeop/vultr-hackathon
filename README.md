# Blast Radius Zero — Self-Healing Code Runner

An AI agent that **writes code, runs it in an isolated Vultr sandbox, reads the errors, patches itself, and retries** — with the entire heal loop streamed live to your browser.

> Built for the **Vultr Agent Rush Hackathon**. Every line of agent-generated code executes inside a throwaway Docker sandbox on a Vultr VM. `rm -rf /`, fork bombs, infinite loops, and OOM attempts are absorbed by the sandbox and never touch the host. **Blast radius: zero.**

---

## What it does

1. You describe a task in plain English (e.g. *"compute the 1000th prime"*, or paste broken code).
2. The orchestrator asks **Vultr Serverless Inference** to generate Python.
3. The code runs in a **fresh, network-less, resource-capped Docker container**.
4. If it fails (exception, timeout, OOM), the agent feeds the traceback back to the model, gets a **patch**, and retries — up to N attempts.
5. Every attempt (code → stdout/stderr → verdict → patch) streams to the UI in real time over SSE.

## Why it wins on "Blast Radius Zero"

| Containment focus | How this project enforces it |
|---|---|
| **Process isolation** | Each run is a separate Docker container. The agent never executes on the host or in the API process. |
| **Secret hygiene** | The Vultr Inference API key lives only in the orchestrator. The sandbox container has **no env vars, no network**, so it cannot exfiltrate anything. |
| **Resource limits** | Every container: `--memory`, `--cpus`, `--pids-limit`, wall-clock timeout, `--network none`, read-only root FS, non-root user, dropped capabilities. |
| **Lifecycle discipline** | Containers run with `--rm` and are force-killed + removed after each task. Nothing persists. |

## Architecture

```
┌────────────┐   SSE    ┌──────────────────────────┐   OpenAI-compatible   ┌───────────────────────────┐
│  React UI  │ <──────  │  FastAPI Orchestrator     │ ───────────────────►  │ Vultr Serverless Inference │
│ (timeline) │  task →  │  (Vultr VM)               │                       │ api.vultrinference.com/v1  │
└────────────┘          │  - self-healing loop      │ <───────────────────  └───────────────────────────┘
                        │  - event stream           │
                        └──────────┬────────────────┘
                                   │ docker run (per attempt)
                                   ▼
                        ┌──────────────────────────┐
                        │  Sandbox container        │  no network · mem/cpu/pids caps
                        │  (throwaway, non-root)    │  read-only FS · caps dropped · --rm
                        └──────────────────────────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Quick start (local)

Requires Docker + Python 3.11 + Node 18.

```bash
cp .env.example .env         # put your Vultr Inference API key in .env
docker build -t sandbox-runner:latest ./sandbox
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
# in another terminal
cd frontend && npm install && npm run dev
```

Open http://localhost:5173.

## Deploy on Vultr

See [docs/VULTR_SETUP.md](docs/VULTR_SETUP.md) — provisioning the VM, getting a Serverless Inference key, and running the stack with `docker-compose`.

## Demo video

The containment moment is scripted in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md): we hand the agent a task whose "solution" is `rm -rf /` / a fork bomb / an infinite loop and show the sandbox absorbing it while the host stays untouched.

## Tech

- **Backend:** FastAPI, Docker SDK, SSE
- **LLM:** Vultr Serverless Inference (OpenAI-compatible)
- **Sandbox:** Docker (non-root, `--network none`, cgroup limits)
- **Frontend:** React + Vite + TypeScript
