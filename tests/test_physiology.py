import random
from datetime import timedelta

from healthcare_timeseries_lab.physiology.engine import PhysiologyEngine
from healthcare_timeseries_lab.physiology.models import PhysiologicalState
from healthcare_timeseries_lab.scenarios.engine import ScenarioEngine
from scripts.generate_history import initial_state
from scripts.ward_registry import WARD_ADMISSIONS


def _advance(admission, ticks: int, seed: int) -> list[PhysiologicalState]:
    engine = PhysiologyEngine(random.Random(seed))
    scenario = ScenarioEngine(
        simulation_start_time=admission.admitted_at,
        conditions=admission.conditions,
    )
    previous = initial_state(admission)
    states = []
    for seq in range(1, ticks + 1):
        current = admission.admitted_at + seq * timedelta(seconds=10)
        previous = engine.next_state(
            patient=admission.profile_at(current),
            previous_state=previous,
            timestamp=current,
            active_conditions=scenario.active_conditions(current),
        )
        states.append(previous)
    return states


def test_engine_is_deterministic_per_seed():
    admission = WARD_ADMISSIONS[1]  # Cole W10002
    a = _advance(admission, 600, seed=7)
    b = _advance(admission, 600, seed=7)
    assert a == b


def test_engine_differs_with_different_seed():
    admission = WARD_ADMISSIONS[1]
    a = _advance(admission, 600, seed=7)
    b = _advance(admission, 600, seed=8)
    assert a != b


def test_states_stay_in_physiological_bounds():
    for admission in (WARD_ADMISSIONS[0], WARD_ADMISSIONS[4]):
        degree = 2_400  # ~6.7 hours -> deep into progression episodes
        states = _advance(admission, degree, seed=5)
        assert len(states) == degree
        assert all(s.spo2_pct >= 50 for s in states)  # bounds enforced by model


def test_hypoxemia_progression_drops_spo2_and_raises_heart_rate():
    admission = WARD_ADMISSIONS[0]  # Naomi W10001, hypoxemia from ~2h
    states = _advance(admission, 2_400, seed=3)  # 2h00m -> 6h40m
    first, last = states[0], states[-1]
    assert last.spo2_pct < first.spo2_pct
    assert last.spo2_pct < 98.0
    assert last.heart_rate_bpm > first.heart_rate_bpm + 3.0


def test_baselines_stay_quiet_for_stable_patient():
    admission = WARD_ADMISSIONS[2]  # Ivy W10003, no conditions
    states = _advance(admission, 1_000, seed=11)
    assert all(96.0 < s.spo2_pct <= 100.0 for s in states)