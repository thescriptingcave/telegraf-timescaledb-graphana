"""Post-load sanity checks against the live TimescaleDB instance.

Checks table counts, timeline coverage, referential integrity, the derived
view, and the continuous aggregate. Exits non-zero on any problem.

Usage: uv run python -m scripts.verify
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

CHECKS = {
    "patients": "SELECT count(*) FROM patients",
    "encounters": "SELECT count(*) FROM encounters",
    "vitals_truth": "SELECT count(*) FROM vitals_truth",
    "vitals": "SELECT count(*) FROM vitals",
    "readings": "SELECT count(*) FROM readings",
    "vitals_hourly": "SELECT count(*) FROM vitals_hourly",
}


def main() -> int:
    load_dotenv(ROOT / ".env")
    url = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/telemetry")

    problems = 0

    with psycopg.connect(url) as conn, conn.cursor() as cur:
            print("== Table counts ==")
            for name, query in CHECKS.items():
                cur.execute(query)
                count = int(cur.fetchone()[0])
                print(f"  {name:<14} {count:>10,}")
                if count == 0:
                    print(f"    !! empty table: {name}")
                    problems += 1

            print("\n== Invariants (from the deterministic registry) ==")
            from scripts.ward_registry import WARD_ADMISSIONS

            expected_truth = sum(a.backfill_ticks() for a in WARD_ADMISSIONS)

            cur.execute("SELECT count(*) FROM vitals_truth")
            truth = int(cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM vitals")
            vit = int(cur.fetchone()[0])
            cur.execute("SELECT count(*) FROM readings")
            readings = int(cur.fetchone()[0])

            if truth != expected_truth:
                print(f"  !! vitals_truth {truth:,} != expected {expected_truth:,}")
                problems += 1
            if readings != 6 * truth + 6 * vit:
                print(f"  !! readings {readings:,} != 6*truth + 6*vitals = {6*truth + 6*vit:,}")
                problems += 1
            if not (0.70 * expected_truth <= vit <= 0.95 * expected_truth):
                print(f"  !! vitals {vit:,} outside expected 70-95% of ticks ({expected_truth:,})")
                problems += 1
            print(
                f"  vitals/ticks = {vit / expected_truth:.1%} "
                f"(design target ~85%; loss = loop skips + off-monitor + device dropout)"
            )

            print("\n== Timeline coverage (vitals) ==")
            cur.execute(
                "SELECT min(time), max(time), "
                "(max(time) - min(time)) AS span FROM vitals"
            )
            lo, hi, span = cur.fetchone()
            print(f"  {lo} -> {hi} ({span})")

            print("\n== Referential integrity ==")
            for label, query in (
                (
                    "vitals orphans",
                    ("SELECT count(*) FROM vitals v "
                     "LEFT JOIN patients p USING (patient_id) "
                     "WHERE p.patient_id IS NULL"),
                ),
                (
                    "readings orphans",
                    ("SELECT count(*) FROM readings r "
                     "LEFT JOIN patients p USING (patient_id) "
                     "WHERE p.patient_id IS NULL"),
                ),
                (
                    "vitals duplicate event_id",
                    "SELECT count(*) - count(DISTINCT event_id) FROM vitals",
                ),
            ):
                cur.execute(query)
                value = int(cur.fetchone()[0])
                print(f"  {label:<26} {value:>10,}")
                if value:
                    problems += 1

            print("\n== Derived view (vitals_derived) ==")
            cur.execute(
                "SELECT count(*), round(avg(map_mmhg), 1), "
                "round(avg(pulse_pressure_mmhg), 1), round(avg(shock_index), 3) "
                "FROM vitals_derived WHERE quality_code <> 'LOST'"
            )
            n, map_, pulse, si = cur.fetchone()
            print(f"  rows={n:,} MAP~{map_} mmHg PP~{pulse} mmHg SI~{si}")

            print("\n== Hourly aggregate (sample) ==")
            cur.execute(
                "SELECT bucket, mrn, n FROM vitals_hourly "
                "ORDER BY bucket LIMIT 3"
            )
            for bucket, mrn, n in cur.fetchall():
                print(f"  {bucket:%Y-%m-%d %H:%M}Z {mrn} n={n}")

    if problems:
        print(f"\n{problems} problem(s) found.", file=sys.stderr)
        return 1

    print("\nAll good.")
    return 0


if __name__ == "__main__":
    sys.exit(main())