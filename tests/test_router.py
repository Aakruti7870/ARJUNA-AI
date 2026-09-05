from app.config import ProviderConfig, Settings
from app.router import ModelRouter


def provider(name, priority, free=True, key="x", model="m"):
    return ProviderConfig(name=name, base_url="https://example.test/v1", api_key=key, default_model=model,
                          priority=priority, free_eligible=free, enabled=True, allowed_models=(), free_models=())


def settings(providers):
    return Settings(app_name="test", environment="test", public_origin="http://localhost",
                    request_timeout_seconds=1, provider_failure_cooldown_seconds=60,
                    platform_api_keys=("test",), providers=tuple(providers), session_secret="x"*40,
                    admin_email="admin@test", admin_password="secure-password-123", cookie_secure=False,
                    database_url="sqlite+pysqlite:///:memory:", api_key_hash_secret="y"*40,
                    rate_limit_per_minute=60, login_rate_limit_per_minute=8, allow_paid_routes=True)


def test_free_only_filters_paid_provider():
    router = ModelRouter(settings([provider("paid", 1, free=False), provider("free", 2, free=True)]))
    assert [p.name for p in router.candidates(provider=None, free_only=True)] == ["free"]


def test_priority_order():
    router = ModelRouter(settings([provider("second", 20), provider("first", 10)]))
    assert [p.name for p in router.candidates(provider=None, free_only=False)] == ["first", "second"]


def test_provider_filter():
    router = ModelRouter(settings([provider("a", 10), provider("b", 20)]))
    assert [p.name for p in router.candidates(provider="b", free_only=False)] == ["b"]


def test_unconfigured_provider_is_removed():
    router = ModelRouter(settings([provider("missing", 1, key=""), provider("ready", 2)]))
    assert [p.name for p in router.candidates(provider=None, free_only=False)] == ["ready"]


def test_free_only_rejects_arbitrary_model_without_free_allowlist():
    router = ModelRouter(settings([provider("free", 1, free=True, model="free-model")]))
    assert router.candidates(provider=None, free_only=True, model="expensive-model") == []


def test_free_models_allowlist():
    p = provider("free", 1, free=True, model="default")
    p = ProviderConfig(**{**p.__dict__, "free_models": ("default", "other-free")})
    router = ModelRouter(settings([p]))
    assert [x.name for x in router.candidates(provider=None, free_only=True, model="other-free")] == ["free"]
