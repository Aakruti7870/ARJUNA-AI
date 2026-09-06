from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .auth import require_platform_key
from .config import ProviderConfig, get_settings
from .providers import OpenAICompatibleProvider, ProviderError

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="ARJUNA AI",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
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


def _security_headers(response: Response) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers[
        "Content-Security-Policy"
    ] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if settings.public_origin.startswith("https://"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


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
    _security_headers(response)
    if request.url.path.startswith("/v1/"):
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
    for provider_config, model in candidates:
        provider = OpenAICompatibleProvider(provider_config, settings)
        try:
            attempt = await provider.chat(request_payload, model)
            response.headers["X-Arjuna-Provider"] = attempt.provider
            response.headers["X-Arjuna-Model"] = attempt.model
            response.headers["X-Arjuna-Latency-Ms"] = str(attempt.latency_ms)
            return attempt.response
        except ProviderError:
            _provider_cooldowns[provider_config.name] = (
                time.monotonic() + settings.provider_failure_cooldown_seconds
            )

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="All eligible model providers failed. Retry after the provider cooldown window.",
    )
