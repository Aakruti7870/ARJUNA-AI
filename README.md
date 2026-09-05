# ARJUNA AI

ARJUNA AI is a standalone self-hosted AI gateway and playground that sits in front of multiple OpenAI-compatible model APIs and gives you:

- one `/v1/chat/completions` endpoint for your own apps;
- server-side API-key storage;
- free-first routing and provider fallback;
- provider/model registry;
- playground UI with response preview, latency and usage;
- provider cooldown after failures;
- Docker + Google Cloud Run starter deployment;
- no Replit dependency.

## Important limitation

"Open" does not mean "free". `*_FREE_ELIGIBLE=true` is an operator-controlled policy flag. Only mark a provider free-eligible when your current account/key has free quota or you are self-hosting its compute. Provider terms and quotas can change.

## Architecture

```text
Browser / Your Apps
        |
        v
ARJUNA AI
  |           |
  |           +--> Playground / Preview
  v
Free-first Model Router
  |
  +--> NVIDIA-compatible API
  +--> Gemini OpenAI-compatible API
  +--> Groq OpenAI-compatible API
  +--> OpenRouter (optional)
  +--> OpenAI (optional)
```

## Run locally

```bash
cp .env.example .env
# Add API keys and model names to .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Open `http://localhost:8080`.

The development platform key in the UI defaults to `dev-local-key`. Change `PLATFORM_API_KEYS` before any shared or production deployment.

## Provider setup

Every provider requires four things:

```text
API_KEY
MODEL
BASE_URL
FREE_ELIGIBLE
```

Examples are in `.env.example`.

The gateway intentionally does **not** hard-code model names. Model availability changes faster than the gateway architecture, so you choose a current model from your provider account.

## Call your own API

```bash
curl http://localhost:8080/v1/chat/completions \
  -H 'Authorization: Bearer YOUR_PLATFORM_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"auto",
    "free_only":true,
    "messages":[{"role":"user","content":"Explain this API design."}]
  }'
```

The response is passed through in OpenAI Chat Completions format. The selected route is returned in headers:

```text
X-Arjuna-Provider
X-Arjuna-Model
X-Arjuna-Latency-Ms
```

## Production hardening before public launch

This is an MVP scaffold, not a finished public SaaS. Before public users are allowed, add:

1. Secret Manager instead of plain environment files.
2. User accounts and per-user generated API keys stored as hashes.
3. Persistent quota/usage database (PostgreSQL/Redis).
4. Distributed rate limiting.
5. Billing/spend caps and per-provider quota polling where supported.
6. Audit logs without prompt/secret leakage.
7. Streaming and tool-calling compatibility tests per provider.
8. Abuse controls and content/safety policies appropriate to your service.
9. Private Cloud Run ingress or a proper auth layer for the admin UI.
10. Sandbox execution if you later add code/app preview generation.

## Next build phases

### Phase 2 — Secure ARJUNA AI Console
- login and admin RBAC;
- secure provider key management through Google Secret Manager;
- model discovery and health checks;
- usage dashboard and daily limits;
- API-key issuance for your applications.

### Phase 3 — Preview workspace
- temporary Git workspaces;
- isolated container builds;
- web/app preview URLs;
- approve/reject flow;
- PR creation only after approval.

### Phase 4 — Agents
- coding, testing, security, UI and deployment agents;
- GitHub/MCP/tool gateway;
- explicit production-write approvals;
- model selection per agent.
