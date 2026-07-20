from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import rag
from app.main import app
from app.rag import _can_access_document, _decode_document, _decode_json_value, filter_cited_sources
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


def test_append_history_writes_refused_as_boolean(monkeypatch):
    calls = []

    class FakeConnection:
        def execute(self, query, params=()):
            calls.append((query, params))
            return SimpleNamespace(lastrowid=len(calls))

    @contextmanager
    def fake_get_db():
        yield FakeConnection()

    monkeypatch.setattr(rag, "get_db", fake_get_db)

    rag.append_history(1, "question", "answer", [], refused=True)

    chat_params = next(params for query, params in calls if "INSERT INTO chat_messages" in query)
    assert chat_params[-1] is True
    assert isinstance(chat_params[-1], bool)


def test_document_access_requires_clearance_role_department_and_user_scope():
    document = {
        "security_level": 2,
        "department_scope": [1],
        "visible_roles": ["reader"],
        "visible_users": [],
    }
    low_clearance = {"id": 7, "role": "reader", "department_id": 1, "clearance_level": 1, "status": "active"}
    allowed = {**low_clearance, "clearance_level": 2}

    assert not _can_access_document(document, low_clearance)
    assert _can_access_document(document, allowed)
    assert not _can_access_document(document, {**allowed, "department_id": 2})
    assert not _can_access_document({**document, "visible_roles": ["kb_admin"]}, allowed)
    assert not _can_access_document({**document, "visible_users": [8]}, allowed)
    assert _can_access_document({**document, "visible_users": [7]}, allowed)


def test_only_active_system_admin_bypasses_document_policy():
    restricted = {
        "security_level": 3,
        "department_scope": [99],
        "visible_roles": ["reader"],
        "visible_users": [99],
    }
    admin = {"id": 1, "role": "system_admin", "clearance_level": 0, "status": "active"}

    assert _can_access_document(restricted, admin)
    assert not _can_access_document(restricted, {**admin, "status": "disabled"})


def test_public_document_is_visible_to_every_active_authenticated_user():
    public_document = {
        "security_level": 0,
        "department_scope": [99],
        "visible_roles": ["reader"],
        "visible_users": [99],
    }
    kb_admin = {"id": 2, "role": "kb_admin", "department_id": 2, "clearance_level": 2, "status": "active"}

    assert _can_access_document(public_document, kb_admin)
    assert not _can_access_document(public_document, {**kb_admin, "status": "disabled"})
