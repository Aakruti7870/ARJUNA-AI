# ARJUNA AI

ARJUNA AI is a standalone AI command centre and OpenAI-compatible gateway. It is intentionally independent from every other project, domain, database and deployment.

## Launch portal v0.2

The web portal now includes:

- secure administrator console login with signed HttpOnly session cookies and CSRF protection;
- responsive dashboard and installable PWA shell;
- multi-provider playground with free-first routing and automatic fallback;
- NVIDIA, Gemini, Groq, OpenRouter and OpenAI-compatible provider adapters;
- generated ARJUNA API keys stored as keyed hashes and shown only once;
- `/v1/chat/completions` and `/v1/models` OpenAI-style endpoints;
- per-key in-process rate limiting;
- usage metadata dashboard (provider, model, tokens, latency, status — prompts/responses are not persisted);
- SQLite for local development and PostgreSQL-compatible `DATABASE_URL` for persistent production data;
- security headers, production secret validation, Docker, Cloud Run deployment starter and GitHub Actions CI;
- starter Terms and Privacy pages that must be replaced/reviewed for the final legal entity and launch jurisdiction.

## Critical assumption

Open-source or open-weight models are not automatically free to run. `*_FREE_ELIGIBLE=true` is an operator policy switch. Set it only when the connected account currently has free quota or the compute is self-hosted.

## Local run

```bash
cp .env.example .env
# Set ADMIN_EMAIL, ADMIN_PASSWORD, SESSION_SECRET, API_KEY_HASH_SECRET and at least one provider key/model.
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Open `http://localhost:8080`.

## Production minimum

Before public launch:

1. Set `ENVIRONMENT=production`.
2. Put all secrets in a dedicated secret manager; never commit `.env`.
3. Use a persistent PostgreSQL `DATABASE_URL`; Cloud Run local disk is not durable.
4. Set a production domain and `PUBLIC_ORIGIN`.
5. Keep `COOKIE_SECURE=true` behind HTTPS.
6. Configure provider quotas/spend controls and verify each provider's current terms.
7. Replace the starter Privacy/Terms text with reviewed legal documents and a real contact address.
8. Add managed/WAF-level rate limiting if exposing the API at scale; the built-in limiter is per process.
9. Add centralized logs/metrics and alerting.
10. Run provider integration tests using dedicated low-quota test keys before enabling paid fallback.

## API example

```bash
curl https://YOUR-ARJUNA-DOMAIN/v1/chat/completions \
  -H 'Authorization: Bearer arjuna_live_...' \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "auto",
    "free_only": true,
    "messages": [{"role":"user","content":"Hello from ARJUNA AI"}]
  }'
```

Selected route is returned in:

```text
X-Arjuna-Provider
X-Arjuna-Model
X-Arjuna-Latency-Ms
```

## Next launch milestone

The next production milestone is infrastructure completion: dedicated ARJUNA domain, PostgreSQL instance, secret manager, provider credentials, centralized monitoring, distributed rate limiting and deployment verification. None of those resources should be shared with an unrelated project.
