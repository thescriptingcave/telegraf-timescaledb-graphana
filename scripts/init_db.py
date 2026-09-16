"""Apply the TimescaleDB DDL (sql/ddl/00_init.sql) idempotently.

Usage: uv run python scripts/init_db.py
Connectivity comes from DATABASE_URL in .env (defaults to the local compose
instance). The SQL file is safe to re-apply: every statement is guarded with
IF NOT EXISTS / DO blocks, and CREATE OR REPLACE is used for views and the
continuous aggregate.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DDL_PATH = ROOT / "sql" / "ddl" / "00_init.sql"


def main() -> int:
    load_dotenv(ROOT / ".env")
    url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres@localhost:5432/telemetry",
    )

    if not DDL_PATH.exists():
        print(f"DDL file not found: {DDL_PATH}", file=sys.stderr)
        return 1

    with psycopg.connect(url, autocommit=True) as conn:
        print(f"Connected; applying {DDL_PATH.name} ...")
        started = time.perf_counter()

        with conn.cursor() as cur:
            cur.execute(DDL_PATH.read_text(encoding="utf-8"))

        elapsed = time.perf_counter() - started
        print(f"Schema ready in {elapsed:.2f}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())