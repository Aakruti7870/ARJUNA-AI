from __future__ import annotations

import asyncio
import hmac
import html
import re
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .growth import PLATFORM_CATALOG, catalog as growth_catalog, condition_matches, normalize_tags, recommend_automation, score_lead
from .preview import analyze_preview
from .router import ModelRouter
from .schemas import (
    ApiKeyCreateRequest, AutomationCreateRequest, CampaignCreateRequest, ChatRequest,
    GrowthBrainRequest, GrowthConnectorUpsertRequest, LeadCreateRequest, LeadUpdateRequest,
    LoginRequest, PlaygroundRequest, PreviewAnalyzeRequest, ProposalCreateRequest, ProviderUpsertRequest,
)
from .security import SessionData, SessionManager, SlidingWindowLimiter, constant_time_equal
from .storage import Storage

settings = get_settings()
storage = Storage(settings.database_url, settings.api_key_hash_secret, settings.provider_vault_secret)
router = ModelRouter(settings, provider_loader=lambda: storage.effective_providers(settings.providers))
sessions = SessionManager(settings.session_secret)
api_limiter = SlidingWindowLimiter(settings.rate_limit_per_minute)
login_limiter = SlidingWindowLimiter(settings.login_rate_limit_per_minute)

app = FastAPI(title=settings.app_name, version="0.4.0", docs_url=None if settings.environment == "production" else "/api/docs", redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Arjuna-CSRF"],
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; frame-src 'self' data: blob:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(RuntimeError)
async def runtime_error_handler(_: Request, exc: RuntimeError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return (forwarded.split(",", 1)[0].strip() if forwarded else (request.client.host if request.client else "unknown"))


def _session(arjuna_session: str | None = Cookie(default=None)) -> SessionData:
    data = sessions.read(arjuna_session)
    if not data or data.email.lower() != settings.admin_email:
        raise HTTPException(status_code=401, detail="Console login required")
    return data


def _csrf(session: SessionData = Depends(_session), x_arjuna_csrf: str | None = Header(default=None)) -> SessionData:
    if not x_arjuna_csrf or not hmac.compare_digest(x_arjuna_csrf, session.csrf):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    return session


def _bearer_identity(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    for idx, allowed in enumerate(settings.platform_api_keys):
        if hmac.compare_digest(token, allowed):
            identity = {"id": f"env:{idx}", "name": "environment key"}
            if not api_limiter.allow(identity["id"]):
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            return identity
    row = storage.verify_api_key(token)
    if not row:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not api_limiter.allow(row["id"]):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    return row


def _usage_tokens(response: dict) -> int | None:
    usage = response.get("usage") or {}
    for key in ("total_tokens", "totalTokens"):
        value = usage.get(key)
        if isinstance(value, int):
            return value
    return None


def _lead_recipient(lead: dict[str, Any], channel: str) -> str | None:
    return lead.get("phone") if channel in {"whatsapp_business", "telegram", "sms"} else lead.get("email")


def _execute_growth_actions(actions: list[dict[str, Any]], payload: dict[str, Any], automation_id: str | None, event_type: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    lead = payload.get("lead") if isinstance(payload.get("lead"), dict) else None
    for action in actions:
        action_type = str(action.get("type") or "").strip()
        try:
            if action_type == "set_lead_status" and lead:
                updated = storage.update_lead(lead["id"], status=str(action.get("value") or "qualified"))
                if updated: lead = updated; payload["lead"] = updated
                results.append({"type": action_type, "ok": bool(updated)})
            elif action_type == "add_tag" and lead:
                tags = normalize_tags([*(lead.get("tags") or []), str(action.get("value") or "")])
                updated = storage.update_lead(lead["id"], tags=tags)
                if updated: lead = updated; payload["lead"] = updated
                results.append({"type": action_type, "ok": bool(updated)})
            elif action_type in {"create_followup", "notify", "webhook", "publish_campaign"}:
                channel = str(action.get("channel") or ("internal" if action_type == "notify" else "webhook"))
                recipient = _lead_recipient(lead, channel) if lead else None
                queued = storage.enqueue_outbox(
                    kind=action_type, channel=channel, recipient=recipient,
                    payload={"event": event_type, "automation_id": automation_id, "action": action, "context": payload},
                    delay_minutes=int(action.get("delay_minutes") or 0),
                )
                results.append({"type": action_type, "ok": True, "outbox_id": queued["id"], "status": "queued_for_approval"})
            else:
                results.append({"type": action_type or "unknown", "ok": False, "error": "Unsupported automation action"})
        except Exception as exc:
            results.append({"type": action_type or "unknown", "ok": False, "error": str(exc)[:240]})
    storage.record_automation_run(automation_id, event_type, "ok", {"results": results})
    return results


def _run_growth_event(event_type: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    all_results: list[dict[str, Any]] = []
    if event_type == "lead.created" and isinstance(payload.get("lead"), dict):
        all_results.extend(_execute_growth_actions(recommend_automation(payload["lead"]), payload, None, "smart.lead.created"))
    for rule in storage.list_automations(event_type):
        if condition_matches(rule.get("condition"), payload):
            all_results.extend(_execute_growth_actions(rule.get("actions") or [], payload, rule["id"], event_type))
    return all_results


@app.get("/")
async def index(): return FileResponse(STATIC_DIR / "index.html")

@app.get("/privacy")
async def privacy(): return FileResponse(STATIC_DIR / "privacy.html")

@app.get("/terms")
async def terms(): return FileResponse(STATIC_DIR / "terms.html")

@app.get("/manifest.webmanifest")
async def manifest(): return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")

@app.get("/service-worker.js")
async def service_worker(): return FileResponse(STATIC_DIR / "service-worker.js", media_type="application/javascript")

@app.get("/api/health")
async def health(): return {"ok": True, "service": settings.app_name, "version": "0.4.0", "environment": settings.environment}


@app.get("/api/auth/status")
async def auth_status(arjuna_session: str | None = Cookie(default=None)):
    data = sessions.read(arjuna_session); authenticated = bool(data and data.email.lower() == settings.admin_email)
    return {"authenticated": authenticated, "email": data.email if authenticated else None, "csrf": data.csrf if authenticated else None}

@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request, response: Response):
    if not login_limiter.allow(_client_ip(request)): raise HTTPException(status_code=429, detail="Too many login attempts")
    if not (constant_time_equal(req.email.strip().lower(), settings.admin_email) and constant_time_equal(req.password, settings.admin_password)):
        await asyncio.sleep(0.15); raise HTTPException(status_code=401, detail="Invalid email or password")
    token, data = sessions.issue(settings.admin_email)
    response.set_cookie("arjuna_session", token, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=43200, path="/")
    return {"ok": True, "email": data.email, "csrf": data.csrf}

@app.post("/api/auth/logout")
async def logout(response: Response, _: SessionData = Depends(_csrf)):
    response.delete_cookie("arjuna_session", path="/"); return {"ok": True}


@app.get("/api/dashboard")
async def dashboard(_: SessionData = Depends(_session)):
    stats = storage.dashboard_stats(); provider_status = router.public_status()
    stats["providersReady"] = sum(1 for p in provider_status if p["configured"] and not p["cooldown"])
    stats["providersTotal"] = len(provider_status); stats["growth"] = storage.growth_stats(); return stats

@app.get("/api/providers")
async def providers(_: SessionData = Depends(_session)):
    override_names = storage.provider_override_names(); base_names = {p.name for p in settings.providers}; output = router.public_status()
    for item in output: item["source"] = ("vault" if item["name"] in base_names else "custom") if item["name"] in override_names else "environment"
    return {"providers": output, "paidRoutesAllowed": settings.allow_paid_routes}

@app.post("/api/providers/{provider_name}")
async def upsert_provider(provider_name: str, req: ProviderUpsertRequest, _: SessionData = Depends(_csrf)):
    name = provider_name.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,49}", name): raise HTTPException(status_code=400, detail="Provider name must use lowercase letters, numbers, _ or -")
    if not (req.base_url.startswith("https://") or (settings.environment != "production" and req.base_url.startswith("http://"))): raise HTTPException(status_code=400, detail="Provider base URL must use HTTPS")
    storage.upsert_provider(name=name, base_url=req.base_url, api_key=req.api_key, default_model=req.default_model, priority=req.priority,
                            free_eligible=req.free_eligible, enabled=req.enabled, allowed_models=req.allowed_models, free_models=req.free_models)
    await router.clear_failure(name); return {"ok": True, "provider": next((p for p in router.public_status() if p["name"] == name), None)}

@app.delete("/api/providers/{provider_name}")
async def delete_provider(provider_name: str, _: SessionData = Depends(_csrf)):
    name = provider_name.strip().lower()
    if not storage.delete_provider_override(name): raise HTTPException(status_code=404, detail="Provider vault override not found")
    await router.clear_failure(name); return {"ok": True}


@app.get("/api/keys")
async def list_keys(_: SessionData = Depends(_session)): return {"keys": storage.list_api_keys()}

@app.post("/api/keys")
async def create_key(req: ApiKeyCreateRequest, _: SessionData = Depends(_csrf)):
    record, raw = storage.create_api_key(req.name); return {"key": record, "secret": raw, "warning": "This secret is shown once. Store it securely."}

@app.delete("/api/keys/{key_id}")
async def revoke_key(key_id: str, _: SessionData = Depends(_csrf)):
    if not storage.revoke_api_key(key_id): raise HTTPException(status_code=404, detail="API key not found or already revoked")
    return {"ok": True}

@app.get("/api/usage")
async def usage(limit: int = 100, _: SessionData = Depends(_session)): return {"events": storage.recent_usage(max(1, min(limit, 500)))}


@app.post("/api/preview/analyze")
async def preview_analyze(req: PreviewAnalyzeRequest, _: SessionData = Depends(_csrf)):
    return JSONResponse(content=analyze_preview(req.content, req.hint), headers={"Cache-Control": "no-store"})


# Growth OS: social connectivity, lead CRM, campaigns, proposals and automation.
@app.get("/api/growth/catalog")
async def get_growth_catalog(_: SessionData = Depends(_session)):
    connectors = {c["platform"]: c for c in storage.list_growth_connectors()}
    items = []
    for item in growth_catalog(): items.append({**item, "connection": connectors.get(item["id"])})
    return {"platforms": items}

@app.post("/api/growth/connectors/{platform}")
async def upsert_growth_connector(platform: str, req: GrowthConnectorUpsertRequest, _: SessionData = Depends(_csrf)):
    platform = platform.strip().lower()
    if platform not in PLATFORM_CATALOG: raise HTTPException(status_code=400, detail="Unsupported platform connector")
    storage.upsert_growth_connector(platform=platform, account_label=req.account_label, account_id=req.account_id,
                                    credentials=req.credentials, config=req.config, enabled=req.enabled)
    return {"ok": True, "connectors": storage.list_growth_connectors()}

@app.delete("/api/growth/connectors/{platform}")
async def delete_growth_connector(platform: str, _: SessionData = Depends(_csrf)):
    if not storage.delete_growth_connector(platform.strip().lower()): raise HTTPException(status_code=404, detail="Connector not configured")
    return {"ok": True}

@app.get("/api/growth/leads")
async def growth_leads(_: SessionData = Depends(_session)): return {"leads": storage.list_leads()}

@app.post("/api/growth/leads")
async def create_growth_lead(req: LeadCreateRequest, _: SessionData = Depends(_csrf)):
    payload = req.model_dump(); payload["tags"] = normalize_tags(payload.get("tags")); score, reasons, next_action = score_lead(payload)
    lead = storage.create_lead(payload, score=score, score_reasons=reasons, next_action=next_action)
    actions = _run_growth_event("lead.created", {"lead": lead, "source": "console"})
    return {"lead": storage.get_lead(lead["id"]), "automation": actions}

@app.patch("/api/growth/leads/{lead_id}")
async def update_growth_lead(lead_id: str, req: LeadUpdateRequest, _: SessionData = Depends(_csrf)):
    lead = storage.update_lead(lead_id, status=req.status, owner=req.owner, tags=normalize_tags(req.tags) if req.tags is not None else None, notes=req.notes)
    if not lead: raise HTTPException(status_code=404, detail="Lead not found")
    return {"lead": lead}

@app.get("/api/growth/campaigns")
async def growth_campaigns(_: SessionData = Depends(_session)): return {"campaigns": storage.list_campaigns()}

@app.post("/api/growth/campaigns")
async def create_growth_campaign(req: CampaignCreateRequest, _: SessionData = Depends(_csrf)):
    campaign = storage.create_campaign(req.model_dump()); actions = _run_growth_event("campaign.created", {"campaign": campaign})
    return {"campaign": campaign, "automation": actions, "publishing": "approval-gated"}

@app.get("/api/growth/proposals")
async def growth_proposals(_: SessionData = Depends(_session)): return {"proposals": storage.list_proposals()}

@app.post("/api/growth/proposals")
async def create_growth_proposal(req: ProposalCreateRequest, request: Request, _: SessionData = Depends(_csrf)):
    proposal, token = storage.create_proposal(req.model_dump()); share_url = str(request.base_url).rstrip("/") + "/p/" + token
    _run_growth_event("proposal.created", {"proposal": proposal, "share_url": share_url})
    return {"proposal": proposal, "share_url": share_url, "warning": "Share token is returned once; anyone with the link can view until expiry."}

@app.get("/p/{share_token}", response_class=HTMLResponse)
async def shared_proposal(share_token: str):
    proposal = storage.shared_proposal(share_token)
    if not proposal: raise HTTPException(status_code=404, detail="Proposal not found or expired")
    amount = "" if proposal.get("amount") is None else f"<div class='amount'>{html.escape(proposal['currency'])} {proposal['amount']:,.2f}</div>"
    body = html.escape(proposal["body"]).replace("\n", "<br>")
    return HTMLResponse(f"""<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(proposal['title'])}</title><style>body{{font-family:system-ui;background:#0c0d10;color:#f7f8fa;margin:0;padding:32px}}main{{max-width:820px;margin:auto;background:#13151a;border:1px solid #262b34;border-radius:24px;padding:32px}}h1{{font-size:38px}}.amount{{font-size:28px;font-weight:800;color:#f5a524;margin:20px 0}}.body{{line-height:1.7;color:#d7dbe2}}small{{color:#969da9}}</style></head><body><main><small>ARJUNA AI · Shared proposal</small><h1>{html.escape(proposal['title'])}</h1>{amount}<div class='body'>{body}</div><p><small>Expires {html.escape(str(proposal['expires_at']))}</small></p></main></body></html>""")

@app.get("/api/growth/automations")
async def growth_automations(_: SessionData = Depends(_session)): return {"automations": storage.list_automations(), "outbox": storage.list_outbox(100)}

@app.post("/api/growth/automations")
async def create_growth_automation(req: AutomationCreateRequest, _: SessionData = Depends(_csrf)):
    return {"automation": storage.create_automation(req.model_dump())}

@app.delete("/api/growth/automations/{automation_id}")
async def delete_growth_automation(automation_id: str, _: SessionData = Depends(_csrf)):
    if not storage.delete_automation(automation_id): raise HTTPException(status_code=404, detail="Automation not found")
    return {"ok": True}

@app.get("/api/growth/stats")
async def growth_stats(_: SessionData = Depends(_session)): return storage.growth_stats()

@app.post("/api/growth/brain")
async def growth_brain(req: GrowthBrainRequest, _: SessionData = Depends(_session)):
    prompt = (
        "You are ARJUNA Growth Brain. Produce a concise, execution-ready growth plan as JSON with keys: summary, audience, offer, "
        "channels, campaignIdeas, leadCapture, followUpSequence, proposalStrategy, automations, metrics, risks. "
        "Never claim a campaign was published. Respect platform policies and require human approval before spend or external publishing.\n\n"
        f"Goal: {req.goal}\nContext: {req.context or 'None'}\nAvailable channel types: {', '.join(PLATFORM_CATALOG.keys())}"
    )
    payload = {"messages": [{"role": "system", "content": "You are a growth operations strategist."}, {"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 5000}
    started = time.perf_counter(); attempt = await router.route(payload, provider=req.provider, free_only=req.free_only, model=req.model)
    latency = int((time.perf_counter() - started) * 1000)
    storage.record_usage(api_key_id="growth-brain", provider=attempt.provider, model=attempt.model, tokens=_usage_tokens(attempt.response), latency_ms=latency)
    try: content = attempt.response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError): content = attempt.response
    return {"provider": attempt.provider, "model": attempt.model, "latencyMs": latency, "content": content, "mode": "draft-only"}


@app.post("/api/playground")
async def playground(req: PlaygroundRequest, _: SessionData = Depends(_session)):
    messages = []
    if req.system_prompt: messages.append({"role": "system", "content": req.system_prompt})
    messages.append({"role": "user", "content": req.prompt})
    payload = {"messages": messages, "temperature": req.temperature, "max_tokens": req.max_tokens}; started = time.perf_counter()
    attempt = await router.route(payload, provider=req.provider, free_only=req.free_only, model=req.model); total_latency = int((time.perf_counter() - started) * 1000)
    storage.record_usage(api_key_id="console", provider=attempt.provider, model=attempt.model, tokens=_usage_tokens(attempt.response), latency_ms=total_latency)
    try: content = attempt.response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError): content = attempt.response
    return {"id": str(uuid.uuid4()), "provider": attempt.provider, "model": attempt.model, "providerLatencyMs": attempt.latency_ms,
            "totalLatencyMs": total_latency, "usage": attempt.response.get("usage"), "content": content, "raw": attempt.response}


@app.get("/v1/models")
async def models(_: dict = Depends(_bearer_identity)):
    return {"object": "list", "data": [{"id": p.default_model, "object": "model", "owned_by": p.name} for p in storage.effective_providers(settings.providers) if p.configured]}

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest, identity: dict = Depends(_bearer_identity)):
    if req.stream: raise HTTPException(status_code=400, detail="Streaming is not enabled yet")
    payload = req.model_dump(exclude={"provider", "free_only", "model"}, exclude_none=True); payload["messages"] = [m.model_dump() for m in req.messages]
    started = time.perf_counter(); attempt = await router.route(payload, provider=req.provider, free_only=req.free_only, model=req.model); total_latency = int((time.perf_counter() - started) * 1000)
    storage.record_usage(api_key_id=identity.get("id"), provider=attempt.provider, model=attempt.model, tokens=_usage_tokens(attempt.response), latency_ms=total_latency)
    response = JSONResponse(content=attempt.response); response.headers["X-Arjuna-Provider"] = attempt.provider; response.headers["X-Arjuna-Model"] = attempt.model; response.headers["X-Arjuna-Latency-Ms"] = str(attempt.latency_ms); return response

@app.post("/v1/leads")
async def capture_lead(req: LeadCreateRequest, identity: dict = Depends(_bearer_identity)):
    payload = req.model_dump(); payload["tags"] = normalize_tags(payload.get("tags")); score, reasons, next_action = score_lead(payload)
    lead = storage.create_lead(payload, score=score, score_reasons=reasons, next_action=next_action)
    actions = _run_growth_event("lead.created", {"lead": lead, "source": "api", "api_key_id": identity.get("id")})
    return {"id": lead["id"], "status": lead["status"], "score": lead["score"], "next_action": lead["next_action"], "automation_actions": len(actions)}
