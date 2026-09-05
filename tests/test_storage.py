from app.storage import Storage


def test_key_lifecycle():
    store = Storage("sqlite+pysqlite:///:memory:", "secret"*8)
    row, secret = store.create_api_key("Test key")
    assert secret.startswith("arjuna_live_")
    assert store.verify_api_key(secret)["id"] == row["id"]
    assert store.revoke_api_key(row["id"])
    assert store.verify_api_key(secret) is None


def test_usage_stats():
    store = Storage("sqlite+pysqlite:///:memory:", "secret"*8)
    store.record_usage(api_key_id="x", provider="nvidia", model="m", tokens=123, latency_ms=42)
    stats = store.dashboard_stats()
    assert stats["requests24h"] == 1
    assert stats["tokens24h"] == 123


def test_provider_vault_override_and_custom_provider():
    from app.config import ProviderConfig
    store = Storage("sqlite+pysqlite:///:memory:", "secret"*8, "vault"*10)
    base = ProviderConfig(name="nvidia", base_url="https://base.test/v1", api_key="env-key", default_model="env-model",
                          priority=10, free_eligible=True, enabled=True, allowed_models=(), free_models=())
    store.upsert_provider(name="nvidia", base_url="https://override.test/v1", api_key="vault-key", default_model="free-model",
                          priority=5, free_eligible=True, enabled=True, allowed_models=["free-model"], free_models=["free-model"])
    providers = {p.name: p for p in store.effective_providers((base,))}
    assert providers["nvidia"].api_key == "vault-key"
    assert providers["nvidia"].base_url == "https://override.test/v1"
    assert providers["nvidia"].free_models == ("free-model",)
    assert "vault-key" not in str(store.provider_override_names())


def test_provider_vault_never_returns_secret_in_name_listing():
    store = Storage("sqlite+pysqlite:///:memory:", "secret"*8, "vault"*10)
    store.upsert_provider(name="custom", base_url="https://custom.test/v1", api_key="super-secret", default_model="m",
                          priority=50, free_eligible=True, enabled=True, allowed_models=[], free_models=[])
    assert store.provider_override_names() == {"custom"}
    assert store.delete_provider_override("custom")
