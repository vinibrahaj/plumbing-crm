import time

import pytest
from fastapi.testclient import TestClient

from app.db import connect
from app.main import app
from app.security import hash_password

PASSWORD = 'test-password-123'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'test.db'))
    with TestClient(app) as c:
        with connect() as db:
            encoded = hash_password(PASSWORD)
            for uid, role in [(1, 'manager'), (2, 'customer'), (3, 'customer'),
                              (4, 'plumber'), (5, 'plumber'), (6, 'plumber')]:
                db.execute('INSERT INTO users(id,name,email,password_hash,role,address) VALUES (?,?,?,?,?,?)',
                           (uid, f'Person {uid}', f'user{uid}@example.com', encoded, role, 'Private home'))
            db.execute("INSERT INTO services VALUES (1,'Leak repair',8500,1)")
            db.execute("INSERT INTO services VALUES (2,'Pipe installation',20000,2)")
            db.executemany('INSERT INTO skills VALUES (?,?)', [(4, 1), (4, 2), (5, 2)])
        yield c


def auth(client, uid):
    response = client.post('/api/auth/login', json={'email': f'user{uid}@example.com', 'password': PASSWORD})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def job(client, headers, **extra):
    response = client.post('/api/jobs', headers=headers, json={
        'customer_id': 2, 'service_id': 1, 'description': 'Kitchen leak', 'address': 'Job address', **extra,
    })
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_job_lifecycle_and_price_snapshot(client):
    manager = auth(client, 1)
    jid = job(client, manager)
    url = f'/api/jobs/{jid}'
    assert client.patch(url + '/status', headers=manager, json={'status': 'finished'}).status_code == 409
    assert client.patch(url + '/status', headers=manager, json={'status': 'in_progress'}).status_code == 409
    assert client.put(url + '/assignments', headers=manager, json={'plumber_ids': [4]}).status_code == 200
    assert client.patch(url + '/status', headers=manager, json={'status': 'in_progress'}).status_code == 200
    assert client.put(url + '/assignments', headers=manager, json={'plumber_ids': []}).status_code == 409
    assert client.patch(url + '/status', headers=manager, json={'status': 'finished'}).status_code == 200
    assert client.patch(url + '/status', headers=manager, json={'status': 'in_progress'}).status_code == 409
    with connect() as db:
        db.execute('UPDATE services SET price_cents=9900 WHERE id=1')
    saved = client.get('/api/jobs', headers=manager).json()[0]
    assert saved['status'] == 'finished'
    assert saved['started_at'] and saved['finished_at']
    assert saved['price_cents'] == 8500


def test_role_boundaries_and_internal_notes(client):
    manager, owner, other, plumber, unassigned = [auth(client, i) for i in [1, 2, 3, 4, 5]]
    jid = job(client, manager)
    url = f'/api/jobs/{jid}'
    client.put(url + '/assignments', headers=manager, json={'plumber_ids': [4]})
    assert client.get('/api/jobs', headers=other).json() == []
    assert client.get('/api/jobs', headers=unassigned).json() == []
    assert client.post(url + '/notes', headers=unassigned, json={'body': 'Hidden'}).status_code == 404
    assert client.post(url + '/notes', headers=plumber, json={'body': 'Pipe inspected'}).status_code == 201
    assert client.post(url + '/notes', headers=owner, json={'body': 'Not internal'}).status_code == 403
    assert client.get('/api/jobs', headers=owner).json()[0]['notes'] == []
    assert client.get('/api/jobs', headers=manager).json()[0]['notes'][0]['body'] == 'Pipe inspected'
    member = client.get('/api/jobs', headers=plumber).json()[0]['plumbers'][0]
    assert 'address' not in member and 'password_hash' not in member
    for role in [owner, other, plumber, unassigned]:
        assert client.get('/api/users', headers=role).status_code == 403
        assert client.put(url + '/assignments', headers=role, json={'plumber_ids': [4]}).status_code == 403
        assert client.patch(url + '/status', headers=role, json={'status': 'in_progress'}).status_code == 403
    assert client.post('/api/jobs', headers=owner, json={
        'customer_id': 3, 'service_id': 1, 'description': 'Forged', 'address': 'X',
    }).status_code == 403


def test_skill_capacity_duplicate_validation_and_atomic_replacement(client):
    manager = auth(client, 1)
    jid = job(client, manager)
    url = f'/api/jobs/{jid}/assignments'
    assert client.put(url, headers=manager, json={'plumber_ids': [4]}).status_code == 200
    for ids in [[5], [6], [4, 4], [4, 5], [2], [999]]:
        assert client.put(url, headers=manager, json={'plumber_ids': ids}).status_code == 422
        assert [p['id'] for p in client.get('/api/jobs', headers=manager).json()[0]['plumbers']] == [4]
    second = job(client, manager, service_id=2)
    assert client.put(f'/api/jobs/{second}/assignments', headers=manager, json={'plumber_ids': [4, 5]}).status_code == 200
    assert client.patch(f'/api/jobs/{second}/status', headers=manager, json={'status': 'in_progress'}).status_code == 200


def test_auth_expiry_logout_and_user_validation(client):
    assert client.get('/api/jobs').status_code == 401
    assert client.get('/api/jobs', headers={'Authorization': 'Bearer forged'}).status_code == 401
    assert client.post('/api/auth/login', json={'email': 'missing@example.com', 'password': PASSWORD}).status_code == 401
    manager = auth(client, 1)
    assert 'password_hash' not in client.get('/api/me', headers=manager).json()
    payload = {'name': 'New plumber', 'email': 'new@example.com', 'password': PASSWORD, 'role': 'plumber', 'service_ids': [1]}
    created = client.post('/api/users', headers=manager, json=payload)
    assert created.status_code == 201
    assert client.post('/api/users', headers=manager, json=payload).status_code == 409
    assert client.post('/api/users', headers=manager, json={**payload, 'email': 'second@example.com', 'service_ids': [999]}).status_code == 422
    assert client.post('/api/users', headers=manager, json={**payload, 'email': 'third@example.com', 'role': 'manager'}).status_code == 422
    assert client.post('/api/auth/logout', headers=manager).status_code == 204
    assert client.get('/api/me', headers=manager).status_code == 401
    manager = auth(client, 1)
    with connect() as db:
        db.execute('UPDATE sessions SET expires_at=?', (int(time.time()) - 1,))
    assert client.get('/api/me', headers=manager).status_code == 401
