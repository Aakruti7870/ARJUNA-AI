import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestrator import PROVIDER_CATALOG, _recovery_candidates, provider_config


client = TestClient(app)


@pytest.fixture(autouse=True)
def stub_live_provider_validation(monkeypatch):
    async def _validated(config, settings):
        return config

    monkeypatch.setattr("app.main.validate_provider_config", _validated)


def _guest_headers(name: str = "Tester") -> dict[str, str]:
    response = client.post("/api/auth/guest", json={"display_name": name})
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_home_serves_arjuna_product_flow():
    response = client.get("/")
    assert response.status_code == 200
    assert "ARJUNA AI" in response.text
    assert "Live Preview" in response.text
    assert "CONTINUE FREE" in response.text


def test_health_endpoint():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_models_requires_platform_key():
    response = client.get("/v1/models")
    assert response.status_code == 401


def test_chat_requires_platform_key():
    response = client.post(
        "/v1/chat/completions",
        json={"model": "auto", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 401


def test_free_guest_session_is_usable():
    response = client.post("/api/auth/guest", json={"display_name": "Krushna"})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["name"] == "Krushna"
    assert body["user"]["mode"] == "free_guest"
    assert body["expires_in"] >= 900

    session = client.get("/api/session", headers={"Authorization": f"Bearer {body['token']}"})
    assert session.status_code == 200
    assert session.json()["connected_providers"] == 0


def test_provider_catalog_requires_session():
    response = client.get("/api/providers")
    assert response.status_code == 401


def test_provider_catalog_guides_nvidia_kimi_key_source():
    headers = _guest_headers("Catalog Test")
    response = client.get("/api/providers", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    nvidia = next(item for item in data if item["provider"] == "nvidia")
    kimi = next(item for item in data if item["provider"] == "kimi")
    assert nvidia["suggested_model"] == "moonshotai/kimi-k2.5"
    assert "NVIDIA API key" in nvidia["key_hint"]
    assert kimi["suggested_model"] == "kimi-k2.5"
    assert "Moonshot/Kimi Platform API key" in kimi["key_hint"]


def test_nvidia_recovery_candidates_include_known_models():
    config = provider_config(
        "nvidia",
        "nvapi-test-secret-123456789",
        "wrong-model",
        True,
    )
    models = [candidate.default_model for candidate in _recovery_candidates(config)]
    assert models[0] == "wrong-model"
    assert "moonshotai/kimi-k2.5" in models
    assert "meta/llama-3.3-70b-instruct" in models


def test_connect_multiple_provider_key_without_echoing_secret():
    headers = _guest_headers()
    secret = "nvapi-test-secret-123456789"
    connect = client.post(
        "/api/providers/connect",
        headers=headers,
        json={
            "provider": "nvidia",
            "api_key": secret,
            "model": "test-model",
            "free_eligible": True,
        },
    )
    assert connect.status_code == 200
    assert secret not in connect.text
    assert connect.json()["connected"] is True
    assert connect.json()["validated"] is True
    assert connect.json()["credential_storage"] == "server_session_memory"

    catalog = client.get("/api/providers", headers=headers)
    assert catalog.status_code == 200
    nvidia = next(item for item in catalog.json()["data"] if item["provider"] == "nvidia")
    assert nvidia["connected"] is True
    assert nvidia["model"] == "test-model"
    assert secret not in catalog.text


def test_smart_router_recommends_connected_provider_without_calling_it():
    headers = _guest_headers("Router Test")
    connect = client.post(
        "/api/providers/connect",
        headers=headers,
        json={
            "provider": "groq",
            "api_key": "gsk-test-secret-123456",
            "model": "test-fast-model",
            "free_eligible": True,
        },
    )
    assert connect.status_code == 200
    response = client.post(
        "/api/router/recommend",
        headers=headers,
        json={"prompt": "Build a responsive CRM dashboard", "free_only": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recommended"]["provider"] == "groq"
    assert body["recommended"]["task"] == "coding"
    assert body["recommended"]["free_eligible"] is True


def test_disconnect_provider():
    headers = _guest_headers("Disconnect Test")
    connect = client.post(
        "/api/providers/connect",
        headers=headers,
        json={
            "provider": "gemini",
            "api_key": "gemini-test-secret-12345",
            "model": "test-model",
            "free_eligible": True,
        },
    )
    assert connect.status_code == 200
    response = client.delete("/api/providers/gemini", headers=headers)
    assert response.status_code == 200
    assert response.json()["removed"] is True


def test_preview_not_found_is_isolated_for_framing():
    response = client.get("/api/previews/not-a-real-preview")
    assert response.status_code == 404
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in response.headers["content-security-policy"]


def test_security_headers_are_present():
    response = client.get("/")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_readiness_rejects_default_development_key():
    response = client.get("/readyz")
    assert response.status_code == 503
    assert "platform_api_key_not_production_safe" in response.json()["checks"]
