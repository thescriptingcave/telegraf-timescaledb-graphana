import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DQL = ROOT / "sql" / "dql"

LESSONS = {
    "beginner": [
        "b1_ward_census.sql",
        "b2_hourly_handoff.sql",
        "b3_flag_attention.sql",
    ],
    "intermediate": [
        "i1_first_drop.sql",
        "i2_moving_average.sql",
        "i3_worst_ranked.sql",
        "i4_window_frames.sql",
        "i5_lead_first_last.sql",
        "i6_dense_rank.sql",
        "d1_dimension_modeling.sql",
    ],
    "advanced": [
        "a1_desaturation_episodes.sql",
        "a2_alarm_sessions.sql",
        "a3_observed_vs_truth.sql",
        "a4_lateral_latest.sql",
        "a5_delta_alerts.sql",
        "a6_percentile_outliers.sql",
        "a7_distinct_on_latest.sql",
        "a8_local_extrema.sql",
        "a9_episode_reframe.sql",
        "a10_explain_selectivity.sql",
        "r1_recursive_cte.sql",
        "g1_gap_fill.sql",
        "c1_continuous_aggregates.sql",
    ],
}

SCHEMA_TABLES = (
    "patients",
    "encounters",
    "vitals_truth",
    "vitals_hourly",
    "vitals_derived",
    "readings",
    "vitals",
)

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|create|drop|alter|truncate|grant|revoke|merge|copy|vacuum)\b",
    re.IGNORECASE,
)


def _lesson_paths():
    for tier, files in LESSONS.items():
        for name in files:
            yield tier, DQL / tier / name


@pytest.mark.parametrize(("tier", "path"), list(_lesson_paths()))
def test_lesson_file_exists_with_headers(tier, path):
    assert path.exists(), f"missing lesson {path}"
    text = path.read_text(encoding="utf-8")
    assert "-- lesson:" in text
    assert f"-- tier: {tier}" in text


@pytest.mark.parametrize(("tier", "path"), list(_lesson_paths()))
def test_lessons_are_read_only(tier, path):
    text = path.read_text(encoding="utf-8")
    code = "\n".join(re.sub(r"--.*$", "", line) for line in text.splitlines())
    assert "SELECT" in code.upper()
    match = FORBIDDEN.search(code)
    assert match is None, f"non-read-only keyword {match.group(0)!r} in {path.name}"


@pytest.mark.parametrize(("tier", "path"), list(_lesson_paths()))
def test_lessons_reference_the_lab_schema(tier, path):
    text = path.read_text(encoding="utf-8").lower()
    assert any(table in text for table in SCHEMA_TABLES), (
        f"{path.name} does not reference any lab table"
    )