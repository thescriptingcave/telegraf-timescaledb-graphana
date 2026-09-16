import math
from datetime import UTC, datetime, timedelta

import pytest

from healthcare_timeseries_lab.scenarios.engine import ScenarioEngine
from scripts.ward_registry import (
    EVENT_NS,
    TRUTH_NS,
    WARD_ADMISSIONS,
    admission_for,
    event_id_for,
    truth_id_for,
)


def test_admissions_are_unique_and_ordered():
    mrns = [a.mrn for a in WARD_ADMISSIONS]
    assert len(mrns) == len(set(mrns))
    assert len(WARD_ADMISSIONS) == 6


def test_patient_id_is_consistent_between_profile_and_admission():
    for admission in WARD_ADMISSIONS:
        assert admission.patient_id == admission.baseline.patient_id


def test_scenario_windows_are_in_order():
    for admission in WARD_ADMISSIONS:
        assert admission.admitted_at < admission.discharged_at
        assert admission.backfill_ticks() > 0


def test_event_id_namespaces_are_distinct():
    sim = admission_for("W10001").simulation_id
    assert event_id_for(sim, 1) != truth_id_for(sim, 1)
    assert EVENT_NS != TRUTH_NS
    assert event_id_for(sim, 1) != event_id_for(sim, 2)


def test_seeds_are_deterministic_and_distinct():
    seeds = [a.seed for a in WARD_ADMISSIONS]
    assert len(set(seeds)) == len(seeds)
    assert any(seeds)


@pytest.mark.parametrize(
    ("hour", "expected_ratio"),
    [(3, 0.15), (20, 0.53), (480, 1.0)],
)
def test_hypoxemia_severity_tracks_timeline(hour, expected_ratio):
    admission = admission_for("W10001")
    scenario = ScenarioEngine(
        simulation_start_time=admission.admitted_at,
        conditions=admission.conditions,
    )
    at = admission.admitted_at + timedelta(hours=hour)
    active = scenario.active_conditions(at)
    assert len(active) == 1
    assert active[0].name == "hypoxemia"
    assert active[0].severity == pytest.approx(expected_ratio, abs=0.06)


def test_conditions_resolved_after_recovery_window():
    admission = admission_for("W10001")
    scenario = ScenarioEngine(
        simulation_start_time=admission.admitted_at,
        conditions=admission.conditions,
    )
    at = admission.admitted_at + timedelta(days=23)  # recovery ended day 22
    assert scenario.active_conditions(at) == []


def test_live_scenario_start_equals_backfill_end():
    from scripts.ward_registry import BACKFILL_END, LIVE_SCENARIO_START

    assert LIVE_SCENARIO_START == BACKFILL_END
    assert LIVE_SCENARIO_START.tzinfo is UTC
    assert math.isfinite(LIVE_SCENARIO_START.timestamp())
    assert datetime(2026, 1, 31, tzinfo=UTC) == LIVE_SCENARIO_START