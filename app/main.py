from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .auth import require_platform_key
from .config import ProviderConfig, get_settings
from .orchestrator import (
    PROVIDER_CATALOG,
    catalog_payload,
    execute_build,
    provider_config,
    rank_routes,
    validate_provider_config,
)
from .providers import OpenAIProvider, ProviderError, provider_for
from .session_auth import (
    SessionData,
    create_guest_session,
    get_preview,
    require_session,
    session_ttl_seconds,
)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="ARJUNA AI",
    version="0.3.1",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Arjuna-Provider", "X-Arjuna-Model", "X-Arjuna-Latency-Ms"],
)

_provider_cooldowns: dict[str, float] = {}


class ChatRequest(BaseModel):
    model: str = Field(default="auto", min_length=1, max_length=200)
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    free_only: bool = True
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=131072)


class GuestRequest(BaseModel):
    display_name: str = Field(default="Creator", max_length=80)


class ProviderConnectRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    api_key: str = Field(default="", max_length=4096)
    model: str = Field(default="", max_length=200)
    free_eligible: bool | None = None


class ProviderModelsRequest(BaseModel):
    api_key: str = Field(default="", max_length=4096)


class RouterRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=30000)
    free_only: bool = False


class BuildRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=30000)
    free_only: bool = False


def _security_headers(response: Response) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers[
        "Content-Security-Policy"
    ] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if settings.public_origin.startswith("https://"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


def _preview_security_headers(response: Response) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers[
        "Content-Security-Policy"
    ] = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"


@app.middleware("http")
async def protect_requests(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_request_bytes:
                response = JSONResponse(status_code=413, content={"detail": "Request body too large"})
                _security_headers(response)
                return response
        except ValueError:
            pass

    response = await call_next(request)
    if request.url.path.startswith("/api/previews/"):
        _preview_security_headers(response)
    else:
        _security_headers(response)
    if request.url.path.startswith(("/v1/", "/api/")):
        response.headers["Cache-Control"] = "no-store"
    return response


def _configured_providers() -> list[ProviderConfig]:
    return sorted((p for p in settings.providers if p.configured), key=lambda p: p.priority)


def _production_readiness() -> tuple[bool, list[str]]:
    problems: list[str] = []
    weak_keys = {"dev-local-key", "replace-with-a-long-random-key", "changeme", "change-me"}

    if not settings.platform_api_keys or any(key.lower() in weak_keys for key in settings.platform_api_keys):
        problems.append("platform_api_key_not_production_safe")
    if not _configured_providers():
        problems.append("no_model_provider_configured")
    if settings.production and not settings.public_origin.startswith("https://"):
        problems.append("public_origin_must_use_https")
    if settings.production and "gold-etechapp.com" not in settings.public_origin:
        problems.append("public_origin_domain_mismatch")

    return not problems, problems


def _select_candidates(payload: ChatRequest) -> list[tuple[ProviderConfig, str]]:
    providers = _configured_providers()
    requested_provider: str | None = None
    requested_model = payload.model.strip()

    if ":" in requested_model:
        prefix, model_name = requested_model.split(":", 1)
        if prefix and model_name:
            requested_provider = prefix.lower().strip()
            requested_model = model_name.strip()

    candidates: list[tuple[ProviderConfig, str]] = []
    now = time.monotonic()
    for provider in providers:
        if requested_provider and provider.name != requested_provider:
            continue
        if payload.free_only and not provider.free_eligible:
            continue
        if _provider_cooldowns.get(provider.name, 0) > now:
            continue
        model = provider.default_model if requested_model == "auto" else requested_model
        candidates.append((provider, model))
    return candidates


@app.get("/")
async def home() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=500, detail="Web UI is not installed")
    return FileResponse(index)


@app.get("/styles.css")
async def styles() -> FileResponse:
    return FileResponse(STATIC_DIR / "styles.css", media_type="text/css")


@app.get("/app.js")
async def frontend_js() -> FileResponse:
    return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript")


@app.get("/favicon.svg")
async def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/robots.txt")
async def robots() -> FileResponse:
    return FileResponse(STATIC_DIR / "robots.txt", media_type="text/plain")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    ready, problems = _production_readiness()
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": problems},
    )


# Browser product flow: free session -> BYOK -> smart route -> build -> sandbox preview.
@app.post("/api/auth/guest")
async def guest_login(payload: GuestRequest) -> dict[str, Any]:
    token, session = create_guest_session(payload.display_name)
    return {
        "token": token,
        "expires_in": session_ttl_seconds(),
        "user": {"name": session.display_name, "mode": "free_guest"},
    }


@app.get("/api/session")
async def session_info(session: SessionData = Depends(require_session)) -> dict[str, Any]:
    return {
        "user": {"name": session.display_name, "mode": "free_guest"},
        "expires_at": session.expires_at,
        "connected_providers": len(session.providers),
    }


@app.get("/api/providers")
async def browser_providers(session: SessionData = Depends(require_session)) -> dict[str, Any]:
    return {"data": catalog_payload(session)}


def _openai_config(api_key: str) -> ProviderConfig:
    server = next((item for item in settings.providers if item.name == "openai"), None)
    if not server:
        raise HTTPException(status_code=400, detail="OpenAI is not configured")
    key = api_key.strip() or (server.api_key if server.enabled else "")
    if not key:
        raise HTTPException(status_code=400, detail="Enter an OpenAI API key.")
    return ProviderConfig(
        name="openai", base_url=server.base_url, api_key=key,
        default_model=server.default_model, priority=server.priority,
        free_eligible=False, enabled=True,
    )


def _openai_model_rank(model_id: str) -> tuple[int, str]:
    value = model_id.lower()
    preferred = value.startswith(("gpt-5", "o3", "o4", "gpt-4.1", "gpt-4o"))
    excluded = any(token in value for token in ("embedding", "moderation", "transcribe", "tts", "image", "whisper", "audio", "realtime"))
    return (0 if preferred and not excluded else 1 if not excluded else 2, value)


@app.post("/api/providers/openai/models")
async def openai_models(
    payload: ProviderModelsRequest,
    session: SessionData = Depends(require_session),
) -> dict[str, Any]:
    config = _openai_config(payload.api_key)
    try:
        models = await OpenAIProvider(config, settings).models()
    except ProviderError as exc:
        if exc.status_code == 401:
            detail = "OpenAI rejected this API key."
        elif exc.status_code == 403:
            detail = "OpenAI API access is not permitted for this key/project."
        elif exc.status_code == 429:
            detail = "OpenAI rate limit or quota was exceeded. Check project billing and limits."
        else:
            detail = "Could not fetch models from OpenAI. Try again shortly."
        raise HTTPException(status_code=exc.status_code or 502, detail=detail) from exc
    safe = [
        {"id": item["id"], "created": item.get("created"), "owned_by": item.get("owned_by")}
        for item in sorted(models, key=lambda item: _openai_model_rank(item["id"]))
    ]
    ids = {item["id"] for item in safe}
    configured = config.default_model if config.default_model in ids else ""
    selected = configured or (safe[0]["id"] if safe else "")
    return {"data": safe, "selected": selected, "configured_model_available": bool(configured)}


@app.post("/api/providers/connect")
async def connect_provider(
    payload: ProviderConnectRequest,
    session: SessionData = Depends(require_session),
) -> dict[str, Any]:
    try:
        api_key = payload.api_key
        if payload.provider.strip().lower() == "openai" and not api_key.strip():
            api_key = _openai_config("").api_key
        elif len(api_key.strip()) < 8:
            raise ValueError("API key is required")
        requested_config = provider_config(
            payload.provider,
            api_key,
            payload.model,
            payload.free_eligible,
        )
        config = await validate_provider_config(requested_config, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session.providers[config.name] = config
    meta = PROVIDER_CATALOG[config.name]
    return {
        "provider": config.name,
        "label": meta.label,
        "connected": True,
        "validated": True,
        "model": config.default_model,
        "model_recovered": config.default_model != requested_config.default_model,
        "free_eligible": config.free_eligible,
        "credential_storage": "server_session_memory",
    }


@app.delete("/api/providers/{provider_name}")
async def disconnect_provider(
    provider_name: str,
    session: SessionData = Depends(require_session),
) -> dict[str, Any]:
    name = provider_name.strip().lower()
    removed = session.providers.pop(name, None)
    return {"provider": name, "connected": False, "removed": removed is not None}


@app.post("/api/router/recommend")
async def recommend_route(
    payload: RouterRequest,
    session: SessionData = Depends(require_session),
) -> dict[str, Any]:
    routes = rank_routes(session, payload.prompt, payload.free_only)
    return {
        "recommended": routes[0] if routes else None,
        "routes": routes[:6],
        "requires_provider": not bool(routes),
    }


@app.post("/api/build")
async def build_project(
    payload: BuildRequest,
    session: SessionData = Depends(require_session),
) -> dict[str, Any]:
    try:
        return await execute_build(session, settings, payload.prompt, payload.free_only)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/previews/{preview_id}", response_class=HTMLResponse)
async def preview(preview_id: str) -> HTMLResponse:
    preview_html = get_preview(preview_id)
    if preview_html is None:
        raise HTTPException(status_code=404, detail="Preview not found or expired")
    return HTMLResponse(preview_html)


# OpenAI-compatible platform API for server-to-server clients.
@app.get("/v1/models", dependencies=[Depends(require_platform_key)])
async def models() -> dict[str, Any]:
    providers = [
        {
            "provider": p.name,
            "model": p.default_model,
            "free_eligible": p.free_eligible,
            "priority": p.priority,
        }
        for p in _configured_providers()
    ]
    return {"object": "list", "data": providers}


@app.post("/v1/chat/completions", dependencies=[Depends(require_platform_key)])
async def chat_completions(payload: ChatRequest, response: Response) -> dict[str, Any]:
    candidates = _select_candidates(payload)
    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No eligible model provider is currently available",
        )

    request_payload = payload.model_dump()
    for provider_config_item, model in candidates:
        provider = provider_for(provider_config_item, settings)
        try:
            attempt = await provider.chat(request_payload, model)
            response.headers["X-Arjuna-Provider"] = attempt.provider
            response.headers["X-Arjuna-Model"] = attempt.model
            response.headers["X-Arjuna-Latency-Ms"] = str(attempt.latency_ms)
            return attempt.response
        except ProviderError:
            _provider_cooldowns[provider_config_item.name] = (
                time.monotonic() + settings.provider_failure_cooldown_seconds
            )

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="All eligible model providers failed. Retry after the provider cooldown window.",
    )
