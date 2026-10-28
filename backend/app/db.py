import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect():
    path = Path(os.getenv("DATABASE_PATH", "plumb.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('manager','plumber','customer')),
            phone TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id), expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
            workers INTEGER NOT NULL CHECK(workers BETWEEN 1 AND 10)
        );
        CREATE TABLE IF NOT EXISTS skills (
            plumber_id INTEGER NOT NULL REFERENCES users(id),
            service_id INTEGER NOT NULL REFERENCES services(id),
            PRIMARY KEY(plumber_id, service_id)
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES users(id),
            service_id INTEGER NOT NULL REFERENCES services(id),
            description TEXT NOT NULL, address TEXT NOT NULL,
            priority TEXT NOT NULL CHECK(priority IN ('low','normal','high','emergency')),
            status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','in_progress','finished')),
            price_cents INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            started_at TEXT, finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS assignments (
            job_id INTEGER NOT NULL REFERENCES jobs(id),
            plumber_id INTEGER NOT NULL REFERENCES users(id),
            PRIMARY KEY(job_id, plumber_id)
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id),
            author_id INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
        """)
