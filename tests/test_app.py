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


def test_provider_vault_console_flow():
    client = TestClient(app)
    login = client.post('/api/auth/login', json={'email': 'admin@arjuna.local', 'password': 'change-me-now'})
    assert login.status_code == 200
    csrf = login.json()['csrf']

    payload = {
        'base_url': 'https://example.test/v1',
        'api_key': 'provider-secret-for-test',
        'default_model': 'free-model',
        'priority': 7,
        'free_eligible': True,
        'enabled': True,
        'allowed_models': ['free-model'],
        'free_models': ['free-model'],
    }
    saved = client.post('/api/providers/custom-test', headers={'X-Arjuna-CSRF': csrf}, json=payload)
    assert saved.status_code == 200

    providers = client.get('/api/providers')
    assert providers.status_code == 200
    custom = next(p for p in providers.json()['providers'] if p['name'] == 'custom-test')
    assert custom['source'] == 'custom'
    assert custom['defaultModel'] == 'free-model'
    assert 'provider-secret-for-test' not in providers.text

    models = client.get('/v1/models', headers={'Authorization': 'Bearer dev-local-key'})
    assert models.status_code == 200
    assert any(m['id'] == 'free-model' and m['owned_by'] == 'custom-test' for m in models.json()['data'])

    removed = client.delete('/api/providers/custom-test', headers={'X-Arjuna-CSRF': csrf})
    assert removed.status_code == 200
