# Vultr setup & deployment

You said you have a Vultr account but no VM or Inference key yet. Here's the full path from zero to a public demo URL.

## 1. Get a Serverless Inference API key (required)

All agent LLM calls must go through Vultr Serverless Inference.

1. Vultr console → **Products** → **Serverless** → **Inference**.
2. Create an Inference subscription if you don't have one.
3. Open it → **API Keys** → create a key. Copy it.
4. List available models (so you can pick one for `VULTR_MODEL`):

   ```bash
   curl https://api.vultrinference.com/v1/models \
     -H "Authorization: Bearer YOUR_KEY"
   ```

   Put a chat-capable model id (e.g. a Llama 3.3 70B instruct variant) in `.env` as `VULTR_MODEL`.
   For the "Chart Anything"-style tasks a vision model isn't required, but one is available if you extend the project.

> The base URL is `https://api.vultrinference.com/v1` and the API is OpenAI-compatible, so the client in `backend/app/inference.py` just points at it.

## 2. Provision a Vultr VM

1. Vultr console → **Deploy** → **Cloud Compute** (shared CPU is fine to start).
2. **OS:** Ubuntu 24.04 LTS.
3. **Plan:** at least 2 vCPU / 4 GB RAM (sandbox containers need headroom). 4 vCPU / 8 GB is comfortable for the demo.
4. Add your SSH key, deploy, and note the public IP.

## 3. Install Docker on the VM

```bash
ssh root@YOUR_VM_IP
curl -fsSL https://get.docker.com | sh
docker --version && docker compose version
```

## 4. Open the firewall ports

In the Vultr console add a **Firewall Group** allowing inbound:
- `22` (SSH)
- `8080` (frontend — nginx also proxies `/api` to the backend)

Do **not** open `8000`: the backend listens on loopback only and is reached through nginx.

Attach it to the instance.

## 5. Deploy the stack

```bash
git clone YOUR_PUBLIC_REPO_URL blast-radius-zero
cd blast-radius-zero

cp .env.example .env
nano .env                       # paste VULTR_INFERENCE_API_KEY and set VULTR_MODEL

# Build the locked-down sandbox image the orchestrator will launch
docker build -t sandbox-runner:latest ./sandbox

# Build + run frontend and backend
docker compose up --build -d
```

Your public demo URL is now **http://YOUR_VM_IP:8080**.

### Verify

```bash
curl http://localhost:8000/api/health        # shows model + sandbox limits
docker compose logs -f backend               # watch the loop
```

## 6. (Optional) HTTPS + a real domain

Point a domain's A record at the VM, then put Caddy in front for automatic TLS:

```bash
docker run -d --name caddy --network host \
  caddy:2 caddy reverse-proxy --from your-domain.com --to :8080
```

## 7. (Optional) Vultr API for per-task throwaway instances

The hackathon allows using the Vultr API to spin up and destroy a fresh instance per task for an even stronger isolation story. This project uses per-task **containers** by default (faster, same containment guarantees). If you want per-task **VMs**, create a Vultr API key (Account → API) and extend `backend/app/sandbox.py` with a provider that calls the Vultr Instances API and tears the instance down in its `finally` block — the `Sandbox` interface (`run(code) -> ExecResult`) stays the same.

## Cost note

Participants get $200 in Vultr credits. A small Cloud Compute VM plus modest Inference usage over the build period fits comfortably within that.
