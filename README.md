# ARJUNA AI

ARJUNA AI is a standalone self-hosted AI gateway and playground that sits in front of multiple OpenAI-compatible model APIs and gives you:

- one `/v1/chat/completions` endpoint for your own apps;
- server-side API-key storage;
- free-first routing and provider fallback;
- provider/model registry;
- playground UI with response preview, latency and usage;
- provider cooldown after failures;
- Docker deployment;
- Render production Blueprint for `gold-etechapp.com`;
- no Replit or Google Cloud dependency.

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

The development platform key defaults to `dev-local-key`. Change `PLATFORM_API_KEYS` before any shared or production deployment.

## Production launch

Production is designed to run as one Docker web service on Render in Singapore. The committed `render.yaml` configures:

- service name `arjuna-ai`;
- Docker runtime;
- `/healthz` health checks;
- deploys only after GitHub checks pass;
- canonical origin `https://gold-etechapp.com`;
- custom domain `gold-etechapp.com`;
- secret environment variables for ARJUNA/provider credentials.

See `docs/DOMAIN_LAUNCH.md` for deployment and DNS instructions.

Do not use Render's free web-service plan for a production launch because free services can spin down when idle.

## Provider setup

Every provider requires four things:

```text
API_KEY
MODEL
BASE_URL
FREE_ELIGIBLE
```

Examples are in `.env.example` and `.env.production.example`.

The gateway intentionally does **not** hard-code model names. Model availability changes faster than the gateway architecture, so choose a current model from your provider account.

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

## Production hardening before unrestricted public SaaS launch

The current service is suitable for the ARJUNA command centre and controlled/private access. Before allowing unrestricted multi-user public access, add:

1. User accounts and per-user generated API keys stored as hashes.
2. Persistent quota/usage database (PostgreSQL/Redis).
3. Distributed rate limiting.
4. Billing/spend caps and provider quota polling where supported.
5. Audit logs without prompt/secret leakage.
6. Streaming and tool-calling compatibility tests per provider.
7. Abuse controls and content/safety policies appropriate to your service.
8. An authenticated admin console.
9. Sandbox execution if code/app preview generation is added.

## Next build phases

### Phase 2 — Secure ARJUNA AI Console
- login and admin RBAC;
- secure provider key management;
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
