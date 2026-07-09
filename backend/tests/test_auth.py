from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_documents_requires_login():
    response = client.get("/api/documents")
    assert response.status_code == 401


def test_demo_users_can_login():
    admin_response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    kbadmin_response = client.post("/api/auth/login", json={"username": "kbadmin", "password": "kbadmin123"})
    editor_response = client.post("/api/auth/login", json={"username": "editor", "password": "editor123"})
    user_response = client.post("/api/auth/login", json={"username": "user", "password": "user123"})

    assert admin_response.status_code == 200
    assert admin_response.json()["user"]["role"] == "system_admin"
    assert admin_response.json()["user"]["status"] == "active"
    assert kbadmin_response.status_code == 200
    assert kbadmin_response.json()["user"]["role"] == "kb_admin"
    assert editor_response.status_code == 200
    assert editor_response.json()["user"]["role"] == "editor"
    assert user_response.status_code == 200
    assert user_response.json()["user"]["role"] == "reader"


def test_user_cannot_rebuild_index():
    login_response = client.post("/api/auth/login", json={"username": "user", "password": "user123"})
    token = login_response.json()["access_token"]

    response = client.post("/api/rebuild", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
