from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_documents_requires_login():
    response = client.get("/api/documents")
    assert response.status_code == 401


def test_demo_users_can_login():
    admin_response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    user_response = client.post("/api/auth/login", json={"username": "user", "password": "user123"})

    assert admin_response.status_code == 200
    assert admin_response.json()["user"]["role"] == "admin"
    assert user_response.status_code == 200
    assert user_response.json()["user"]["role"] == "user"


def test_user_cannot_rebuild_index():
    login_response = client.post("/api/auth/login", json={"username": "user", "password": "user123"})
    token = login_response.json()["access_token"]

    response = client.post("/api/rebuild", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
