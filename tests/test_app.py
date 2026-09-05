from fastapi.testclient import TestClient

from app.main import app


def test_health_and_console_login():
    client = TestClient(app)
    health = client.get('/api/health')
    assert health.status_code == 200
    assert health.json()['service'] == 'ARJUNA AI'

    login = client.post('/api/auth/login', json={'email': 'admin@arjuna.local', 'password': 'change-me-now'})
    assert login.status_code == 200
    csrf = login.json()['csrf']

    dashboard = client.get('/api/dashboard')
    assert dashboard.status_code == 200

    created = client.post('/api/keys', headers={'X-Arjuna-CSRF': csrf}, json={'name': 'CI key'})
    assert created.status_code == 200
    assert created.json()['secret'].startswith('arjuna_live_')
