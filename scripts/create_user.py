#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hash_password(password: str) -> str:
    # Keep hashing consistent with backend/aistaff_api/services/auth_service.py (pbkdf2_sha256).
    from passlib.context import CryptContext

    ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    return ctx.hash(password)


def upsert_sqlite(*, db_path: Path, email: str, name: str, password_hash: str, now: str) -> None:
    if not db_path.exists():
        raise SystemExit(f"sqlite db not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users(email, name, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
              name = excluded.name,
              password_hash = excluded.password_hash
            """.strip(),
            (email, name, password_hash, now),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_postgres(*, db_url: str, email: str, name: str, password_hash: str, now: str) -> None:
    # Prefer psycopg3 if available; fallback to asyncpg.
    try:
        import psycopg  # type: ignore

        conn = psycopg.connect(db_url)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO users(email, name, password_hash, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(email) DO UPDATE SET
                  name = EXCLUDED.name,
                  password_hash = EXCLUDED.password_hash
                """.strip(),
                (email, name, password_hash, now),
            )
            conn.commit()
        finally:
            conn.close()
        return
    except Exception:
        pass

    import asyncio

    import asyncpg  # type: ignore

    async def run() -> None:
        conn = await asyncpg.connect(db_url)
        try:
            await conn.execute(
                """
                INSERT INTO users(email, name, password_hash, created_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT(email) DO UPDATE SET
                  name = EXCLUDED.name,
                  password_hash = EXCLUDED.password_hash
                """.strip(),
                email,
                name,
                password_hash,
                now,
            )
        finally:
            await conn.close()

    asyncio.run(run())


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update aistaff user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    email = str(args.email).strip().lower()
    name = str(args.name).strip()
    password = str(args.password)
    if not email:
        raise SystemExit("empty --email")
    if "@" not in email:
        raise SystemExit("--email must be a valid email (login is email-based)")
    if not name:
        raise SystemExit("empty --name")
    if not password:
        raise SystemExit("empty --password")

    now = utc_now_iso()
    pwd_hash = hash_password(password)

    db_url = (os.getenv("AISTAFF_DB_URL") or "").strip()
    if db_url.lower().startswith("postgres"):
        upsert_postgres(db_url=db_url, email=email, name=name, password_hash=pwd_hash, now=now)
        print(f"ok (postgres): {email}")
        return

    repo_root = Path(__file__).resolve().parents[1]
    db_path = Path(os.getenv("AISTAFF_DB_PATH") or (repo_root / ".aistaff" / "aistaff.db"))
    upsert_sqlite(db_path=db_path.expanduser().resolve(), email=email, name=name, password_hash=pwd_hash, now=now)
    print(f"ok (sqlite): {email}")


if __name__ == "__main__":
    main()

