from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _csv(raw: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in raw.split(",") if value.strip())


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    default_model: str
    priority: int
    free_eligible: bool
    enabled: bool

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.api_key and self.base_url and self.default_model)


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    public_origin: str
    cors_origins: tuple[str, ...]
    max_request_bytes: int
    request_timeout_seconds: int
    provider_failure_cooldown_seconds: int
    platform_api_keys: tuple[str, ...]
    providers: tuple[ProviderConfig, ...]

    @property
    def production(self) -> bool:
        return self.environment.lower() == "production"


def _provider(prefix: str, *, name: str, default_base_url: str, priority: int) -> ProviderConfig:
    return ProviderConfig(
        name=name,
        base_url=os.getenv(f"{prefix}_BASE_URL", default_base_url).rstrip("/"),
        api_key=os.getenv(f"{prefix}_API_KEY", "").strip(),
        default_model=os.getenv(f"{prefix}_MODEL", "").strip(),
        priority=_int(f"{prefix}_PRIORITY", priority),
        free_eligible=_bool(f"{prefix}_FREE_ELIGIBLE", False),
        enabled=_bool(f"{prefix}_ENABLED", True),
    )


def get_settings() -> Settings:
    providers: Iterable[ProviderConfig] = (
        _provider(
            "NVIDIA",
            name="nvidia",
            default_base_url="https://integrate.api.nvidia.com/v1",
            priority=10,
        ),
        _provider(
            "GEMINI",
            name="gemini",
            default_base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            priority=20,
        ),
        _provider(
            "GROQ",
            name="groq",
            default_base_url="https://api.groq.com/openai/v1",
            priority=30,
        ),
        _provider(
            "OPENROUTER",
            name="openrouter",
            default_base_url="https://openrouter.ai/api/v1",
            priority=40,
        ),
        _provider(
            "OPENAI",
            name="openai",
            default_base_url="https://api.openai.com/v1",
            priority=50,
        ),
    )

    public_origin = os.getenv("PUBLIC_ORIGIN", "http://localhost:8080").rstrip("/")
    configured_cors = _csv(os.getenv("CORS_ORIGINS", ""))

    return Settings(
        app_name=os.getenv("APP_NAME", "ARJUNA AI"),
        environment=os.getenv("APP_ENV", "development"),
        public_origin=public_origin,
        cors_origins=configured_cors or (public_origin,),
        max_request_bytes=max(1024, _int("MAX_REQUEST_BYTES", 1_048_576)),
        request_timeout_seconds=max(1, _int("REQUEST_TIMEOUT_SECONDS", 90)),
        provider_failure_cooldown_seconds=max(1, _int("PROVIDER_FAILURE_COOLDOWN_SECONDS", 60)),
        platform_api_keys=_csv(os.getenv("PLATFORM_API_KEYS", "dev-local-key")),
        providers=tuple(providers),
    )
