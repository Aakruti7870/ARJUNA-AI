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
    public_origin: str
    request_timeout_seconds: int
    provider_failure_cooldown_seconds: int
    platform_api_keys: tuple[str, ...]
    providers: tuple[ProviderConfig, ...]


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


def _parse_keys(raw: str) -> tuple[str, ...]:
    return tuple(k.strip() for k in raw.split(",") if k.strip())


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
    return Settings(
        app_name=os.getenv("APP_NAME", "ARJUNA AI"),
        public_origin=os.getenv("PUBLIC_ORIGIN", "http://localhost:8080"),
        request_timeout_seconds=_int("REQUEST_TIMEOUT_SECONDS", 90),
        provider_failure_cooldown_seconds=_int("PROVIDER_FAILURE_COOLDOWN_SECONDS", 60),
        platform_api_keys=_parse_keys(os.getenv("PLATFORM_API_KEYS", "dev-local-key")),
        providers=tuple(providers),
    )
