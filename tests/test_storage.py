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
