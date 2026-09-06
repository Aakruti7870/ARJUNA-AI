from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_home_serves_playground():
    response = client.get("/")
    assert response.status_code == 200
    assert "ARJUNA AI" in response.text


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


def test_security_headers_are_present():
    response = client.get("/")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_readiness_rejects_default_development_key():
    response = client.get("/readyz")
    assert response.status_code == 503
    assert "platform_api_key_not_production_safe" in response.json()["checks"]
