import sqlite3

from app.database import Connection


def test_sqlite_cursor_preserves_lastrowid_and_iteration():
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    connection = Connection(raw, postgres=False)
    connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    inserted = connection.execute("INSERT INTO items (name) VALUES (?)", ("one",))

    assert inserted.lastrowid == 1
    assert [row["name"] for row in connection.execute("SELECT name FROM items")] == ["one"]
