import sqlite3
from contextlib import contextmanager
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "cosai_app.db"


def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS connected_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                account_email TEXT,
                scopes TEXT,
                access_token TEXT,
                refresh_token TEXT,
                token_expiry TEXT,
                query_filter TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                health_status TEXT NOT NULL DEFAULT 'unknown',
                health_error TEXT DEFAULT '',
                last_health_check_at TEXT DEFAULT '',
                last_fetched_at TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS user_prefs (
                user_id INTEGER PRIMARY KEY,
                prefs_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS task_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                entry_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS oauth_state_cache (
                state TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                code_verifier TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )
        # Lightweight schema migration for existing DB files.
        _ensure_connected_accounts_columns(conn)
        conn.commit()


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _ensure_connected_accounts_columns(conn):
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(connected_accounts)").fetchall()}
    needed = {
        "health_status": "TEXT NOT NULL DEFAULT 'unknown'",
        "health_error": "TEXT DEFAULT ''",
        "last_health_check_at": "TEXT DEFAULT ''",
        "last_fetched_at": "TEXT DEFAULT ''",
    }
    for col, ddl in needed.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE connected_accounts ADD COLUMN {col} {ddl}")
