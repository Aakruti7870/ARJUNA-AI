# ARJUNA AI

ARJUNA AI is a standalone AI command centre, growth operating system and OpenAI-compatible gateway. It is intentionally independent from every other project, domain, database and deployment.

## Launch portal v0.4

The web portal includes:

- secure administrator console login with signed HttpOnly session cookies and CSRF protection;
- responsive dashboard and installable PWA shell;
- multi-provider playground with free-first routing and automatic fallback;
- NVIDIA, Gemini, Groq, OpenRouter and OpenAI-compatible provider adapters;
- encrypted provider credential vault with add/edit/reset controls in the web console;
- per-provider allowed-model and free-model policies, plus `ALLOW_PAID_ROUTES=false` as the default zero-spend guard;
- generated ARJUNA API keys stored as keyed hashes and shown only once;
- `/v1/chat/completions`, `/v1/models` and `/v1/leads` API endpoints;
- per-key in-process rate limiting;
- usage metadata dashboard (provider, model, tokens, latency, status — prompts/responses are not persisted);
- SQLite for local development and PostgreSQL-compatible `DATABASE_URL` for persistent production data;
- security headers, production secret validation, Docker, Cloud Run deployment starter and GitHub Actions CI;
- starter Terms and Privacy pages that must be replaced/reviewed for the final legal entity and launch jurisdiction.

## Independent Preview Lab

The Preview Lab is provider-independent and deliberately separated from model execution. It includes:

- automatic HTML, Markdown, JSON and text detection;
- fenced-output extraction;
- static active-content and remote-resource risk scanning;
- risk score, completeness score, structure analysis and content fingerprinting;
- sandboxed rendering with scripts and network resources disabled;
- desktop, tablet and mobile viewport simulation;
- source view and baseline/current line comparison;
- local browser snapshots that are not uploaded to the server;
- direct handoff from Playground output and Growth Brain output.

Preview analysis does not execute submitted code and the analysis endpoint returns `Cache-Control: no-store`.

## Growth OS

Growth OS adds an independent growth and sales control plane on top of the AI router.

### Channel Hub

Connector definitions are included for:

- Meta Ads / Facebook / Instagram;
- Instagram publishing and engagement surfaces;
- WhatsApp Business;
- Google Ads;
- YouTube;
- LinkedIn Ads;
- TikTok Ads;
- X Ads;
- Telegram;
- Email;
- generic inbound/outbound webhooks.

Connector credentials entered in the authenticated console are encrypted at rest and are never returned by the management API.

### Lead intelligence

- manual lead capture and authenticated API capture through `/v1/leads`;
- source, contact, company, message, tags and metadata;
- automatic intent scoring and next-action recommendation;
- priority classification for high-intent leads;
- built-in smart follow-up queueing plus custom event rules.

### Campaign Studio

- multi-channel campaign drafts;
- objective, daily budget, currency, audience and creative payloads;
- campaign records remain draft-first until the corresponding official platform integration is authenticated and approved.

### Proposal sharing

- lead-linked or standalone proposals;
- amount, currency and expiry;
- share tokens are shown through the generated URL and stored only as keyed hashes;
- expired or invalid share tokens are rejected;
- public proposal rendering escapes proposal content before display.

### Smart Automation

Rules can react to events such as `lead.created`, `campaign.created` and `proposal.created`. Current supported actions include:

- `set_lead_status`;
- `add_tag`;
- `create_followup`;
- `notify`;
- `webhook`;
- `publish_campaign`.

External side effects are deliberately written to an approval-gated outbox instead of being sent or published automatically. This prevents an AI plan or malformed rule from spending advertising budget or messaging customers without an explicit production integration and approval policy.

### Growth Brain

Growth Brain routes through the normal ARJUNA free-first model router and can draft an execution-ready growth plan covering audience, offer, channels, campaign ideas, lead capture, follow-up sequence, proposal strategy, automation, metrics and risks. Its output is a plan, not evidence that any external campaign has been published.

## Important platform limitation

A connector card or stored credential is **not** the same as live publishing access. Meta, Google, LinkedIn, TikTok, X and other platforms require their own official developer applications, OAuth/access-token flows, permissions/scopes, account eligibility and sometimes app review. ARJUNA must pass those platform-specific requirements before activating live ad creation, posting, messaging or spend.

## Critical AI-cost assumption

Open-source or open-weight models are not automatically free to run. `*_FREE_ELIGIBLE=true` is an operator policy switch. Set it only when the connected account currently has free quota or the compute is self-hosted. In free-only mode ARJUNA will not accept an arbitrary model outside the configured free-model policy.

## Local run

```bash
cp .env.example .env
# Set ADMIN_EMAIL, ADMIN_PASSWORD, SESSION_SECRET, API_KEY_HASH_SECRET,
# PROVIDER_VAULT_SECRET and at least one provider key/model.
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Open `http://localhost:8080`.

Provider secrets can be supplied from environment secrets or entered through the authenticated Provider Vault. Provider and Growth OS connector secrets are encrypted at rest using the ARJUNA vault key; plaintext credentials are never returned by their management APIs.

## Production minimum

Before public launch:

1. Set `ENVIRONMENT=production`.
2. Put bootstrap secrets, `PROVIDER_VAULT_SECRET` and infrastructure credentials in a dedicated secret manager; never commit `.env`.
3. Use a persistent PostgreSQL `DATABASE_URL`; Cloud Run local disk is not durable.
4. Set a dedicated ARJUNA production domain and `PUBLIC_ORIGIN`.
5. Keep `COOKIE_SECURE=true` behind HTTPS.
6. Configure AI provider quotas/spend controls and verify each provider's current terms.
7. Register the required official social/advertising developer applications and implement their OAuth, scopes, webhook verification and token rotation before enabling external publishing.
8. Keep ad spend, customer messaging and external publishing approval-gated until audit logs, idempotency and retry protections are complete.
9. Replace the starter Privacy/Terms text with reviewed legal documents and a real contact address.
10. Add managed/WAF-level rate limiting if exposing the API at scale; the built-in limiter is per process.
11. Add centralized logs/metrics and alerting.
12. Run AI-provider and social-platform integration tests using dedicated low-quota/test accounts before production activation.

## API examples

AI gateway:

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

Lead capture:

```bash
curl https://YOUR-ARJUNA-DOMAIN/v1/leads \
  -H 'Authorization: Bearer arjuna_live_...' \
  -H 'Content-Type: application/json' \
  -d '{
    "source":"website lead form",
    "name":"Example Buyer",
    "email":"buyer@example.com",
    "message":"Please send pricing and arrange a demo."
  }'
```

Selected AI route is returned in:

```text
X-Arjuna-Provider
X-Arjuna-Model
X-Arjuna-Latency-Ms
```

## Next launch milestone

The next production milestone is infrastructure and official connector completion: dedicated ARJUNA domain, PostgreSQL, secret manager, AI provider credentials, social-platform OAuth applications, webhook verification, outbox workers, approval/audit controls, centralized monitoring, distributed rate limiting and deployment verification. None of those resources should be shared with an unrelated project.
