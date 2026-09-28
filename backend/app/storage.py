import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def database_path() -> Path:
    return Path(os.environ.get("INTRAC_DB_PATH", Path(__file__).resolve().parents[1] / "data" / "intrac.db"))


@contextmanager
def connect(path: Path):
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('ADMINISTRATOR', 'VERIFIER'))
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                operation_name TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                operator_name TEXT NOT NULL,
                location_name TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                location_accuracy REAL,
                status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'REVIEWED')),
                reviewed_at TEXT,
                reviewed_by_name TEXT
            );
            CREATE TABLE IF NOT EXISTS weapons (
                id INTEGER PRIMARY KEY,
                log_id INTEGER NOT NULL REFERENCES operation_logs(id),
                item_type TEXT NOT NULL,
                name_model TEXT NOT NULL DEFAULT '',
                serial_number TEXT NOT NULL DEFAULT '',
                serial_numbers TEXT,
                quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 100000),
                condition TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                photo BLOB,
                photo_content_type TEXT
            );
        """)
        connection.execute("BEGIN IMMEDIATE")
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(operation_logs)")}
        for column, definition in (
            ("status", "TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'REVIEWED'))"),
            ("reviewed_at", "TEXT"),
            ("reviewed_by_name", "TEXT"),
        ):
            if column not in columns:
                connection.execute(f"ALTER TABLE operation_logs ADD COLUMN {column} {definition}")
        weapon_columns = {row["name"] for row in connection.execute("PRAGMA table_info(weapons)")}
        if "serial_numbers" not in weapon_columns:
            connection.execute("ALTER TABLE weapons ADD COLUMN serial_numbers TEXT")
            connection.executemany(
                "UPDATE weapons SET serial_numbers = ? WHERE id = ?",
                [(json.dumps([row["serial_number"].strip()] if row["serial_number"].strip() else []), row["id"])
                 for row in connection.execute("SELECT id, serial_number FROM weapons")],
            )


def weapon_serial_numbers(row) -> list[str]:
    # NULL supports records written before the serial-number list was introduced.
    if row["serial_numbers"] is not None:
        return json.loads(row["serial_numbers"])
    serial_number = row["serial_number"].strip()
    return [serial_number] if serial_number else []


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3, maxmem=64 * 1024 * 1024)
    return f"scrypt$32768$8$3${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    algorithm, n, r, p, salt, expected = encoded.split("$")
    if algorithm != "scrypt":
        return False
    derived = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), maxmem=64 * 1024 * 1024
    )
    return hmac.compare_digest(derived, bytes.fromhex(expected))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def insert_user(path: Path, *, first_name: str, last_name: str, username: str, password: str, role: str):
    password_hash = hash_password(password)
    with connect(path) as connection:
        cursor = connection.execute(
            "INSERT INTO users (first_name, last_name, username, password_hash, role) VALUES (?, ?, ?, ?, ?)",
            (first_name, last_name, username, password_hash, role),
        )
        return dict(connection.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone())
