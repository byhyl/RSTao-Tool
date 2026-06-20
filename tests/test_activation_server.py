import sqlite3

from server import activation_server


def test_admin_token_migrates_to_hash(tmp_path, monkeypatch):
    db_path = tmp_path / "activation.db"
    monkeypatch.setattr(activation_server, "DB_PATH", db_path)

    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE admin_tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT UNIQUE NOT NULL, description TEXT DEFAULT '', created_at TEXT DEFAULT '')"
    )
    conn.execute("INSERT INTO admin_tokens (token, description) VALUES (?, ?)", ("plain-token", "old"))
    conn.commit()
    conn.close()

    activation_server.init_db()

    conn = activation_server.get_db()
    row = conn.execute("SELECT token FROM admin_tokens").fetchone()
    conn.close()

    assert row["token"] == activation_server._hash_admin_token("plain-token")
    assert row["token"] != "plain-token"


def test_admin_token_hash_has_prefix():
    token_hash = activation_server._hash_admin_token("secret")

    assert activation_server._is_hashed_token(token_hash)
    assert token_hash.startswith(activation_server.TOKEN_HASH_PREFIX)
