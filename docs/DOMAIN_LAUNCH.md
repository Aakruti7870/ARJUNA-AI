# ARJUNA AI production launch — gold-etechapp.com

Production architecture:

```text
https://gold-etechapp.com
        |
        v
Render managed HTTPS / custom domain
        |
        v
ARJUNA AI Docker Web Service
Render region: Singapore
        |
        +-- static playground UI
        +-- /healthz
        +-- /readyz
        +-- /v1/models
        +-- /v1/chat/completions
        |
        v
Configured AI providers
```

No Google Cloud, Firebase, or Replit is required for this deployment.

## Why Render

ARJUNA AI is already packaged as one Docker web service that serves both the frontend and API. Render can build that Dockerfile from GitHub, run it as a web service, attach `gold-etechapp.com`, perform HTTP health checks, issue/renew TLS certificates, and redeploy after GitHub checks pass.

The Blueprint is committed at `/render.yaml`.

## Production compute

The Blueprint uses:

```text
Region: Singapore
Plan: 0.5c-512mb
```

This is intentionally a small paid always-on service. Do not use Render's free web-service plan for a public launch because free services spin down after inactivity and cold-start on the next request.

## 1. Connect Render

Use the Render integration in ChatGPT or sign in to Render and connect the GitHub repository:

```text
Aakruti7870/ARJUNA-AI
```

Create a **Blueprint** from the repository's `render.yaml`.

The service name is:

```text
arjuna-ai
```

## 2. Required secrets

The Blueprint will request secret values marked `sync: false`.

Required ARJUNA credential:

```text
PLATFORM_API_KEYS=<long random platform key>
```

At least one model provider must also be configured. NVIDIA is enabled by default in the Blueprint, so the minimum provider configuration is:

```text
NVIDIA_API_KEY=<secret>
NVIDIA_MODEL=<current NVIDIA NIM model id>
```

The remaining providers are disabled by default and can be enabled later from Render environment variables.

Never commit real provider keys to GitHub.

## 3. Deployment behavior

Render uses the repository Dockerfile and `/healthz` as the service health check.

The Blueprint uses:

```text
autoDeployTrigger: checksPass
```

That means changes on `main` deploy only after the linked GitHub checks pass.

The production runtime is configured with:

```text
APP_ENV=production
PUBLIC_ORIGIN=https://gold-etechapp.com
CORS_ORIGINS=https://gold-etechapp.com,https://www.gold-etechapp.com
```

## 4. Connect gold-etechapp.com

The Blueprint declares:

```text
gold-etechapp.com
```

as the custom domain.

After the Render service exists:

1. Open the ARJUNA AI web service in Render.
2. Open **Settings → Custom Domains**.
3. Confirm `gold-etechapp.com` is present.
4. Render will display the exact DNS record(s) required for the domain.
5. Add exactly those records at the DNS provider that manages `gold-etechapp.com`.
6. Remove conflicting old A/AAAA/CNAME records for the same host only when Render instructs you to replace them.
7. Verify the domain in Render.

Render automatically provisions and renews TLS and redirects HTTP traffic to HTTPS.

For the apex domain, Render also handles the corresponding `www` hostname/redirect behavior when the root custom domain is added.

## 5. Launch verification

After deployment and DNS verification:

```bash
curl -i https://gold-etechapp.com/healthz
curl -i https://gold-etechapp.com/readyz
curl -I https://gold-etechapp.com/
```

Expected:

```text
/healthz -> HTTP 200
/readyz  -> HTTP 200 only when the platform key and at least one provider are production-ready
/         -> HTTP 200 over HTTPS
```

Then verify an authenticated model call:

```bash
curl https://gold-etechapp.com/v1/chat/completions \
  -H 'Authorization: Bearer YOUR_PLATFORM_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"auto",
    "free_only":true,
    "messages":[{"role":"user","content":"Reply with ARJUNA ONLINE"}]
  }'
```

A successful routed call should return:

```text
X-Arjuna-Provider
X-Arjuna-Model
X-Arjuna-Latency-Ms
```

## Public-launch boundary

This deployment is suitable for the ARJUNA command centre and controlled/private users. The current gateway still uses a shared platform API key.

Before offering ARJUNA AI as an unrestricted multi-user public SaaS, add user accounts, per-user API keys, persistent quotas/rate limiting, abuse controls, audit logging, and billing/spend caps. Never embed the shared production platform key in public JavaScript.
