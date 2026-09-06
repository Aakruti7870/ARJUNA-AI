# ARJUNA AI production launch — gold-etechapp.com

Target architecture:

```text
https://gold-etechapp.com
        |
        v
Firebase Hosting (SSL/CDN/custom domain)
        |
        +-- static ARJUNA AI playground
        |
        +-- /v1/*, /healthz, /readyz
               |
               v
        Cloud Run: arjuna-ai
        Region: asia-south1
```

This is intentionally used instead of direct Cloud Run domain mapping. Direct Cloud Run domain mapping is preview/limited and is not available in `asia-south1`; Firebase Hosting supports rewrites to Cloud Run in `asia-south1` and provides managed HTTPS/custom domains.

## 1. Google project prerequisites

Use one dedicated Google Cloud/Firebase project for ARJUNA AI. Do not reuse TrackMyRMC production resources.

Enable billing and the services needed by Cloud Run, Cloud Build/Artifact Registry and Firebase Hosting.

Deploy service name:

```text
arjuna-ai
```

Region:

```text
asia-south1
```

## 2. Provider secrets

Do not commit real provider/API keys to GitHub or `.env` files.

At minimum production needs:

```text
PLATFORM_API_KEYS=<long random ARJUNA platform key>
```

And at least one configured model provider with all of:

```text
<PROVIDER>_ENABLED=true
<PROVIDER>_API_KEY=<secret>
<PROVIDER>_MODEL=<current model id>
<PROVIDER>_BASE_URL=<provider URL>
<PROVIDER>_FREE_ELIGIBLE=true|false
```

Store provider keys using Google Secret Manager / Cloud Run secret bindings. Non-secret model IDs and routing priorities may be normal Cloud Run environment variables.

The production readiness endpoint intentionally returns HTTP 503 until the platform key is production-safe and at least one provider is fully configured.

## 3. GitHub Workload Identity Federation

Production deploy uses short-lived Google credentials. Do not add a JSON service-account key to the repository.

Create a Google Workload Identity Federation provider restricted to this GitHub repository:

```text
Aakruti7870/ARJUNA-AI
```

Add these GitHub repository settings:

Repository variable:

```text
GCP_PROJECT_ID=<your ARJUNA Google Cloud/Firebase project id>
```

Repository secrets:

```text
GCP_WIF_PROVIDER=<projects/.../workloadIdentityPools/.../providers/...>
GCP_DEPLOY_SERVICE_ACCOUNT=<deploy-service-account@PROJECT_ID.iam.gserviceaccount.com>
```

The deploy identity needs only the permissions required to deploy Cloud Run from source and deploy Firebase Hosting. Keep runtime provider secrets separate from the deploy identity.

## 4. First deployment

After this branch is merged to `main`, CI runs first. Production deployment is triggered only after the main-branch CI workflow succeeds.

The deployment will:

1. build/deploy the repository to Cloud Run as `arjuna-ai` in `asia-south1`;
2. set the public runtime origin to `https://gold-etechapp.com`;
3. verify the Cloud Run `/healthz` endpoint;
4. deploy the Firebase Hosting config that serves the static UI and rewrites API traffic to Cloud Run.

## 5. Connect gold-etechapp.com

In the Firebase console for the ARJUNA project:

1. Open **Hosting**.
2. Choose **Add custom domain**.
3. Enter `gold-etechapp.com`.
4. Complete domain ownership verification if requested.
5. Firebase will display the exact DNS records required for the domain.
6. Add exactly those records at the DNS provider for `gold-etechapp.com`.
7. Do not guess or copy IP addresses from another project/domain.
8. Wait until Firebase reports the domain as connected and the SSL certificate as active.

Add `www.gold-etechapp.com` separately and configure it to redirect to the apex domain if you want one canonical hostname.

## 6. Required production checks

Run these after DNS/SSL is active:

```bash
curl -i https://gold-etechapp.com/healthz
curl -i https://gold-etechapp.com/readyz
curl -I https://gold-etechapp.com/
```

Expected:

```text
/healthz -> HTTP 200
/readyz  -> HTTP 200 only when platform key + provider config are production-ready
/         -> HTTP 200 with HTTPS/security headers
```

Then test an authenticated request:

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

Confirm these response headers are present on a successful model call:

```text
X-Arjuna-Provider
X-Arjuna-Model
X-Arjuna-Latency-Ms
```

## 7. Public-launch boundary

This branch makes the gateway/domain deployment-ready, but the current authentication model is still a shared platform API key. That is suitable for a private/admin launch or controlled alpha.

Before opening ARJUNA AI as a public multi-user SaaS, add user accounts, per-user API keys, persistent quotas/rate limiting, abuse controls and billing/spend limits. Do not expose the shared production platform key in public frontend code.
