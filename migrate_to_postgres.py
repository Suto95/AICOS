#!/usr/bin/env python3
"""
Migration script: SQLite → PostgreSQL for AICOS production deployment.

Usage:
1. Set environment variables:
   - SQLITE_DB_PATH: path to your local SQLite database
   - DATABASE_URL: PostgreSQL connection string

2. Run: python migrate_to_postgres.py

This script:
- Creates PostgreSQL tables with proper types
- Migrates all data from SQLite
- Handles type conversions (e.g., INTEGER → SERIAL, TEXT → VARCHAR/TEXT)
"""

import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

def get_sqlite_conn():
    sqlite_path = os.getenv("SQLITE_DB_PATH", "cosai_app.db")
    return sqlite3.connect(sqlite_path)


def get_postgres_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def create_postgres_tables(conn):
    """Create PostgreSQL tables with proper constraints and indexes."""
    with conn.cursor() as cur:
        # Drop existing tables if they exist (for re-running migrations)
        cur.execute("DROP TABLE IF EXISTS oauth_state_cache CASCADE;")
        cur.execute("DROP TABLE IF EXISTS task_events CASCADE;")
        cur.execute("DROP TABLE IF EXISTS task_memory CASCADE;")
        cur.execute("DROP TABLE IF EXISTS user_prefs CASCADE;")
        cur.execute("DROP TABLE IF EXISTS connected_accounts CASCADE;")
        cur.execute("DROP TABLE IF EXISTS users CASCADE;")
        
        # Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL
            );
        """)

        # Connected accounts table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS connected_accounts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                provider VARCHAR(50) NOT NULL,
                account_email VARCHAR(255),
                scopes TEXT,
                access_token TEXT,
                refresh_token TEXT,
                token_expiry TIMESTAMP,
                query_filter TEXT DEFAULT '',
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                health_status VARCHAR(20) NOT NULL DEFAULT 'unknown',
                health_error TEXT DEFAULT '',
                last_health_check_at TIMESTAMP,
                last_fetched_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            );
        """)

        # User preferences
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_prefs (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                prefs_json JSONB NOT NULL,
                updated_at TIMESTAMP NOT NULL
            );
        """)

        # Task memory
        cur.execute("""
            CREATE TABLE IF NOT EXISTS task_memory (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                entry_json JSONB NOT NULL,
                created_at TIMESTAMP NOT NULL
            );
        """)

        # Task events
        cur.execute("""
            CREATE TABLE IF NOT EXISTS task_events (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                event_json JSONB NOT NULL,
                created_at TIMESTAMP NOT NULL
            );
        """)

        # OAuth state cache
        cur.execute("""
            CREATE TABLE IF NOT EXISTS oauth_state_cache (
                state VARCHAR(255) PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                code_verifier TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL
            );
        """)

        # Indexes for performance
        cur.execute("CREATE INDEX IF NOT EXISTS idx_connected_accounts_user_id ON connected_accounts(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_task_memory_user_id ON task_memory(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_task_events_user_id ON task_events(user_id);")

    conn.commit()


def migrate_table(table_name, sqlite_conn, postgres_conn, transform_row=None):
    """Generic table migration with optional row transformation."""
    print(f"Migrating {table_name}...")

    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cur.fetchall()

    if not rows:
        print(f"No data in {table_name}")
        return

    # Get column names
    sqlite_cur.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in sqlite_cur.fetchall()]

    postgres_cur = postgres_conn.cursor()
    
    # JSONB columns that need special handling
    jsonb_columns = ['prefs_json', 'entry_json', 'event_json']

    for row in rows:
        row_dict = dict(zip(columns, row))

        # Apply transformation if provided
        if transform_row:
            row_dict = transform_row(row_dict)

        # Wrap JSONB columns with Json() for psycopg2
        for col in jsonb_columns:
            if col in row_dict and isinstance(row_dict[col], dict):
                row_dict[col] = Json(row_dict[col])

        # Insert into PostgreSQL
        cols = ', '.join(row_dict.keys())
        placeholders = ', '.join(['%s'] * len(row_dict))
        values = list(row_dict.values())

        query = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"
        postgres_cur.execute(query, values)

    postgres_conn.commit()
    print(f"Migrated {len(rows)} rows from {table_name}")


def transform_timestamp_fields(row):
    """Convert ISO string timestamps to proper TIMESTAMP format."""
    timestamp_fields = ['created_at', 'updated_at', 'token_expiry', 'last_health_check_at', 'last_fetched_at']

    for field in timestamp_fields:
        if field in row and row[field] and isinstance(row[field], str):
            try:
                # Parse ISO string and ensure it's in UTC
                dt = datetime.fromisoformat(row[field].replace('Z', '+00:00'))
                row[field] = dt
            except ValueError:
                # If parsing fails, set to NULL
                row[field] = None

    return row


def transform_json_fields(row):
    """Convert JSON strings to proper JSON objects."""
    json_fields = ['prefs_json', 'entry_json', 'event_json']

    for field in json_fields:
        if field in row and row[field] and isinstance(row[field], str):
            try:
                row[field] = json.loads(row[field])
            except json.JSONDecodeError:
                row[field] = {}

    return row


def main():
    print("Starting SQLite → PostgreSQL migration...")

    # Connect to databases
    sqlite_conn = get_sqlite_conn()
    postgres_conn = get_postgres_conn()

    try:
        # Create tables
        create_postgres_tables(postgres_conn)

        # Migrate data with transformations
        migrate_table('users', sqlite_conn, postgres_conn, transform_timestamp_fields)

        migrate_table('connected_accounts', sqlite_conn, postgres_conn,
                     lambda row: transform_json_fields(transform_timestamp_fields(row)))

        migrate_table('user_prefs', sqlite_conn, postgres_conn,
                     lambda row: transform_json_fields(transform_timestamp_fields(row)))

        migrate_table('task_memory', sqlite_conn, postgres_conn,
                     lambda row: transform_json_fields(transform_timestamp_fields(row)))

        migrate_table('task_events', sqlite_conn, postgres_conn,
                     lambda row: transform_json_fields(transform_timestamp_fields(row)))

        # Skip oauth_state_cache - it's a temporary cache that doesn't need migration
        print("Skipping oauth_state_cache (temporary cache, not needed for production)")

        print("Migration completed successfully!")

    except Exception as e:
        print(f"Migration failed: {e}")
        postgres_conn.rollback()
        raise

    finally:
        sqlite_conn.close()
        postgres_conn.close()


if __name__ == "__main__":
    main()