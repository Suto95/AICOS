import os
import sqlite3
import warnings
from contextlib import contextmanager
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "cosai_app.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def _has_psycopg2():
    try:
        import psycopg2  # noqa: F401
        return True
    except ImportError:
        return False


class PostgresConnection:
    def __init__(self, dsn):
        import psycopg2
        import psycopg2.extras

        self._conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
        self.is_postgres = True

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def execute(self, sql, params=None):
        cur = self.cursor()
        if params is None:
            cur.execute(self._translate_sql(sql))
        else:
            cur.execute(self._translate_sql(sql), self._normalize_params(params))
        return cur

    def executescript(self, script):
        statements = [stmt.strip() for stmt in script.split(";") if stmt.strip()]
        cur = self.cursor()
        for stmt in statements:
            cur.execute(stmt)
        self.commit()
        return cur

    def _translate_sql(self, sql):
        return sql.replace("?", "%s")

    def _normalize_params(self, params):
        if params is None:
            return None
        if isinstance(params, dict):
            return params
        if isinstance(params, (list, tuple)):
            return tuple(params)
        return params

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        self.close()


def _use_postgres():
    if not DATABASE_URL:
        return False
    if not _has_psycopg2():
        warnings.warn(
            "DATABASE_URL is set but psycopg2 is not installed; falling back to SQLite. "
            "Restore psycopg2-binary for Supabase/Postgres support.")
        return False
    return True


def get_sqlite_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_postgres_conn():
    return PostgresConnection(DATABASE_URL)


def init_db():
    if _use_postgres():
        init_postgres_db()
        return

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
            """)
        _ensure_connected_accounts_columns(conn)
        conn.commit()


def init_postgres_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS connected_accounts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                provider TEXT NOT NULL,
                account_email TEXT,
                scopes TEXT,
                access_token TEXT,
                refresh_token TEXT,
                token_expiry TIMESTAMP,
                query_filter TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                health_status TEXT NOT NULL DEFAULT 'unknown',
                health_error TEXT DEFAULT '',
                last_health_check_at TIMESTAMP,
                last_fetched_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_prefs (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                prefs_json JSONB NOT NULL,
                updated_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_memory (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                entry_json JSONB NOT NULL,
                created_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_events (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                event_json JSONB NOT NULL,
                created_at TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS oauth_state_cache (
                state TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                code_verifier TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL
            );
            """)
        conn.commit()


@contextmanager
def get_conn():
    if _use_postgres():
        yield get_postgres_conn()
        return

    conn = get_sqlite_conn()
    try:
        yield conn
    finally:
        conn.close()


def _ensure_connected_accounts_columns(conn):
    if getattr(conn, "is_postgres", False):
        return

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
