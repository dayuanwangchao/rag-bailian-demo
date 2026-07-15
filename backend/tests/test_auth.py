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


def test_system_admin_cannot_disable_self():
    login_response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_response.json()["access_token"]
    user_id = login_response.json()["user"]["id"]

    response = client.patch(
        f"/api/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "disabled"},
    )

    assert response.status_code == 400
    assert "不能修改当前登录账号状态" in response.json()["detail"]


def test_last_system_admin_cannot_be_disabled_by_another_admin():
    login_response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    token = login_response.json()["access_token"]
    users_response = client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    admin_user = next(user for user in users_response.json() if user["username"] == "admin")

    response = client.patch(
        f"/api/users/{admin_user['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "kb_admin"},
    )

    assert response.status_code == 400
