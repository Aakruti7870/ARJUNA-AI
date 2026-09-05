from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
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
    allowed_models: tuple[str, ...]
    free_models: tuple[str, ...]

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.api_key and self.base_url and self.default_model)


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    public_origin: str
    request_timeout_seconds: int
    provider_failure_cooldown_seconds: int
    platform_api_keys: tuple[str, ...]
    providers: tuple[ProviderConfig, ...]
    session_secret: str
    admin_email: str
    admin_password: str
    cookie_secure: bool
    database_url: str
    api_key_hash_secret: str
    rate_limit_per_minute: int
    login_rate_limit_per_minute: int
    allow_paid_routes: bool
    provider_vault_secret: str


def _provider(prefix: str, *, name: str, default_base_url: str, priority: int) -> ProviderConfig:
    return ProviderConfig(
        name=name,
        base_url=os.getenv(f"{prefix}_BASE_URL", default_base_url).rstrip("/"),
        api_key=os.getenv(f"{prefix}_API_KEY", "").strip(),
        default_model=os.getenv(f"{prefix}_MODEL", "").strip(),
        priority=_int(f"{prefix}_PRIORITY", priority),
        free_eligible=_bool(f"{prefix}_FREE_ELIGIBLE", False),
        enabled=_bool(f"{prefix}_ENABLED", True),
        allowed_models=_parse_keys(os.getenv(f"{prefix}_ALLOWED_MODELS", "")),
        free_models=_parse_keys(os.getenv(f"{prefix}_FREE_MODELS", "")),
    )


def _parse_keys(raw: str) -> tuple[str, ...]:
    return tuple(k.strip() for k in raw.split(",") if k.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    providers: Iterable[ProviderConfig] = (
        _provider("NVIDIA", name="nvidia", default_base_url="https://integrate.api.nvidia.com/v1", priority=10),
        _provider("GEMINI", name="gemini", default_base_url="https://generativelanguage.googleapis.com/v1beta/openai", priority=20),
        _provider("GROQ", name="groq", default_base_url="https://api.groq.com/openai/v1", priority=30),
        _provider("OPENROUTER", name="openrouter", default_base_url="https://openrouter.ai/api/v1", priority=40),
        _provider("OPENAI", name="openai", default_base_url="https://api.openai.com/v1", priority=50),
    )
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    settings = Settings(
        app_name=os.getenv("APP_NAME", "ARJUNA AI"),
        environment=environment,
        public_origin=os.getenv("PUBLIC_ORIGIN", "http://localhost:8080").rstrip("/"),
        request_timeout_seconds=_int("REQUEST_TIMEOUT_SECONDS", 90),
        provider_failure_cooldown_seconds=_int("PROVIDER_FAILURE_COOLDOWN_SECONDS", 60),
        platform_api_keys=_parse_keys(os.getenv("PLATFORM_API_KEYS", "dev-local-key")),
        providers=tuple(providers),
        session_secret=os.getenv("SESSION_SECRET", "dev-session-secret-change-me"),
        admin_email=os.getenv("ADMIN_EMAIL", "admin@arjuna.local").strip().lower(),
        admin_password=os.getenv("ADMIN_PASSWORD", "change-me-now"),
        cookie_secure=_bool("COOKIE_SECURE", environment == "production"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/arjuna.db"),
        api_key_hash_secret=os.getenv("API_KEY_HASH_SECRET", "dev-key-hash-secret-change-me"),
        rate_limit_per_minute=max(1, _int("RATE_LIMIT_PER_MINUTE", 60)),
        login_rate_limit_per_minute=max(1, _int("LOGIN_RATE_LIMIT_PER_MINUTE", 8)),
        allow_paid_routes=_bool("ALLOW_PAID_ROUTES", False),
        provider_vault_secret=os.getenv("PROVIDER_VAULT_SECRET", "dev-provider-vault-secret-change-me"),
    )
    if environment == "production":
        insecure = []
        if settings.session_secret.startswith("dev-") or len(settings.session_secret) < 32:
            insecure.append("SESSION_SECRET")
        if settings.api_key_hash_secret.startswith("dev-") or len(settings.api_key_hash_secret) < 32:
            insecure.append("API_KEY_HASH_SECRET")
        if settings.admin_password == "change-me-now" or len(settings.admin_password) < 12:
            insecure.append("ADMIN_PASSWORD")
        if "dev-local-key" in settings.platform_api_keys:
            insecure.append("PLATFORM_API_KEYS")
        if settings.provider_vault_secret.startswith("dev-") or len(settings.provider_vault_secret) < 32:
            insecure.append("PROVIDER_VAULT_SECRET")
        if insecure:
            raise RuntimeError("Unsafe production configuration: " + ", ".join(insecure))
    return settings
