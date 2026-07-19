from fastapi.testclient import TestClient

from app.main import app
from app.rag import _decode_document, _decode_json_value, filter_cited_sources
from app.schemas import Source


client = TestClient(app)


def _login(username: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_knowledge_bases_are_available_to_authenticated_users():
    token = _login("user", "user123")

    response = client.get("/api/knowledge-bases", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()[0]["name"] == "默认知识库"


def test_reader_cannot_access_audit_logs():
    token = _login("user", "user123")

    response = client.get("/api/audit-logs", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_system_admin_can_manage_users_but_reader_cannot():
    admin_token = _login("admin", "admin123")
    reader_token = _login("user", "user123")

    admin_response = client.get("/api/users", headers={"Authorization": f"Bearer {admin_token}"})
    reader_response = client.get("/api/users", headers={"Authorization": f"Bearer {reader_token}"})

    assert admin_response.status_code == 200
    roles = {row["username"]: row["role"] for row in admin_response.json()}
    assert roles["kbadmin"] == "kb_admin"
    assert roles["editor"] == "editor"
    assert roles["user"] == "reader"
    assert reader_response.status_code == 403


def test_filter_cited_sources_only_returns_used_references():
    sources = [
        Source(id=1, file_name="a.md", chunk_id=1, content="a"),
        Source(id=2, file_name="b.md", chunk_id=1, content="b"),
    ]

    filtered = filter_cited_sources("结论来自这里。[来源2]", sources)

    assert [source.id for source in filtered] == [2]


def test_json_fields_support_sqlite_text_and_postgres_decoded_values():
    assert _decode_json_value('[{"id": 1}]', []) == [{"id": 1}]
    assert _decode_json_value([{"id": 1}], []) == [{"id": 1}]
    assert _decode_json_value({"action": "upload"}, {}) == {"action": "upload"}
    assert _decode_document({"visible_roles": ["reader"]})["visible_roles"] == ["reader"]
