from __future__ import annotations

import asyncio
import hmac
import time
import uuid
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .router import ModelRouter
from .schemas import ApiKeyCreateRequest, ChatRequest, LoginRequest, PlaygroundRequest
from .security import SessionData, SessionManager, SlidingWindowLimiter, constant_time_equal
from .storage import Storage

settings = get_settings()
router = ModelRouter(settings)
storage = Storage(settings.database_url, settings.api_key_hash_secret)
sessions = SessionManager(settings.session_secret)
api_limiter = SlidingWindowLimiter(settings.rate_limit_per_minute)
login_limiter = SlidingWindowLimiter(settings.login_rate_limit_per_minute)

app = FastAPI(title=settings.app_name, version="0.2.0", docs_url="/api/docs", redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.public_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
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
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
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


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/privacy")
async def privacy():
    return FileResponse(STATIC_DIR / "privacy.html")


@app.get("/terms")
async def terms():
    return FileResponse(STATIC_DIR / "terms.html")


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js")
async def service_worker():
    return FileResponse(STATIC_DIR / "service-worker.js", media_type="application/javascript")


@app.get("/api/health")
async def health():
    return {"ok": True, "service": settings.app_name, "version": "0.2.0", "environment": settings.environment}


@app.get("/api/auth/status")
async def auth_status(arjuna_session: str | None = Cookie(default=None)):
    data = sessions.read(arjuna_session)
    authenticated = bool(data and data.email.lower() == settings.admin_email)
    return {"authenticated": authenticated, "email": data.email if authenticated else None, "csrf": data.csrf if authenticated else None}


@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request, response: Response):
    if not login_limiter.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many login attempts")
    valid_email = constant_time_equal(req.email.strip().lower(), settings.admin_email)
    valid_password = constant_time_equal(req.password, settings.admin_password)
    if not (valid_email and valid_password):
        await asyncio.sleep(0.15)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token, data = sessions.issue(settings.admin_email)
    response.set_cookie(
        "arjuna_session", token, httponly=True, secure=settings.cookie_secure,
        samesite="lax", max_age=43200, path="/",
    )
    return {"ok": True, "email": data.email, "csrf": data.csrf}


@app.post("/api/auth/logout")
async def logout(response: Response, _: SessionData = Depends(_csrf)):
    response.delete_cookie("arjuna_session", path="/")
    return {"ok": True}


@app.get("/api/dashboard")
async def dashboard(_: SessionData = Depends(_session)):
    stats = storage.dashboard_stats()
    provider_status = router.public_status()
    stats["providersReady"] = sum(1 for p in provider_status if p["configured"] and not p["cooldown"])
    stats["providersTotal"] = len(provider_status)
    return stats


@app.get("/api/providers")
async def providers(_: SessionData = Depends(_session)):
    return {"providers": router.public_status()}


@app.get("/api/keys")
async def list_keys(_: SessionData = Depends(_session)):
    return {"keys": storage.list_api_keys()}


@app.post("/api/keys")
async def create_key(req: ApiKeyCreateRequest, _: SessionData = Depends(_csrf)):
    record, raw = storage.create_api_key(req.name)
    return {"key": record, "secret": raw, "warning": "This secret is shown once. Store it securely."}


@app.delete("/api/keys/{key_id}")
async def revoke_key(key_id: str, _: SessionData = Depends(_csrf)):
    if not storage.revoke_api_key(key_id):
        raise HTTPException(status_code=404, detail="API key not found or already revoked")
    return {"ok": True}


@app.get("/api/usage")
async def usage(limit: int = 100, _: SessionData = Depends(_session)):
    return {"events": storage.recent_usage(max(1, min(limit, 500)))}


@app.post("/api/playground")
async def playground(req: PlaygroundRequest, _: SessionData = Depends(_session)):
    messages = []
    if req.system_prompt:
        messages.append({"role": "system", "content": req.system_prompt})
    messages.append({"role": "user", "content": req.prompt})
    payload = {"messages": messages, "temperature": req.temperature, "max_tokens": req.max_tokens}
    started = time.perf_counter()
    attempt = await router.route(payload, provider=req.provider, free_only=req.free_only, model=req.model)
    total_latency = int((time.perf_counter() - started) * 1000)
    storage.record_usage(api_key_id="console", provider=attempt.provider, model=attempt.model,
                         tokens=_usage_tokens(attempt.response), latency_ms=total_latency)
    try:
        content = attempt.response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = attempt.response
    return {
        "id": str(uuid.uuid4()), "provider": attempt.provider, "model": attempt.model,
        "providerLatencyMs": attempt.latency_ms, "totalLatencyMs": total_latency,
        "usage": attempt.response.get("usage"), "content": content, "raw": attempt.response,
    }


@app.get("/v1/models")
async def models(_: dict = Depends(_bearer_identity)):
    data = []
    for p in settings.providers:
        if p.configured:
            data.append({"id": p.default_model, "object": "model", "owned_by": p.name})
    return {"object": "list", "data": data}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest, identity: dict = Depends(_bearer_identity)):
    if req.stream:
        raise HTTPException(status_code=400, detail="Streaming is not enabled yet")
    payload = req.model_dump(exclude={"provider", "free_only", "model"}, exclude_none=True)
    payload["messages"] = [m.model_dump() for m in req.messages]
    started = time.perf_counter()
    attempt = await router.route(payload, provider=req.provider, free_only=req.free_only, model=req.model)
    total_latency = int((time.perf_counter() - started) * 1000)
    storage.record_usage(api_key_id=identity.get("id"), provider=attempt.provider, model=attempt.model,
                         tokens=_usage_tokens(attempt.response), latency_ms=total_latency)
    response = JSONResponse(content=attempt.response)
    response.headers["X-Arjuna-Provider"] = attempt.provider
    response.headers["X-Arjuna-Model"] = attempt.model
    response.headers["X-Arjuna-Latency-Ms"] = str(attempt.latency_ms)
    return response
