import json
from datetime import timedelta

from scripts.stream_vitals import (
    advance,
    initial_checkpoint,
)
from scripts.ward_registry import admission_for

TICK = timedelta(seconds=60)
ADMISSION = admission_for("W10001")


def test_initial_checkpoint_is_a_clean_continuation():
    cp = initial_checkpoint(ADMISSION)
    assert cp["sequence_number"] == ADMISSION.backfill_ticks()
    assert cp["mrn"] == "W10001"
    assert cp["oxygen_deficit"] == []


def test_advance_is_pure_and_deterministic():
    cp = initial_checkpoint(ADMISSION)
    event_a, new_a = advance(ADMISSION, cp, scenario_tick=TICK, skip_probability=0.0)
    event_b, new_b = advance(ADMISSION, cp, scenario_tick=TICK, skip_probability=0.0)
    assert event_a is not None
    assert event_a.event_id == event_b.event_id
    assert new_a == new_b  # identical next checkpoint -> identical on-disk state


def test_advance_survives_json_round_trip():
    cp = initial_checkpoint(ADMISSION)
    _, new_cp = advance(ADMISSION, cp, scenario_tick=TICK, skip_probability=0.0)

    reloaded = json.loads(json.dumps(new_cp))
    event_a, next_a = advance(ADMISSION, reloaded, scenario_tick=TICK, skip_probability=0.0)
    event_b, next_b = advance(ADMISSION, new_cp, scenario_tick=TICK, skip_probability=0.0)

    assert event_a.event_id == event_b.event_id
    assert next_a == next_b


def test_checkpoint_advances_time_and_sequence():
    cp = initial_checkpoint(ADMISSION)
    _, first = advance(ADMISSION, cp, scenario_tick=TICK, skip_probability=0.0)
    _, second = advance(ADMISSION, first, scenario_tick=TICK, skip_probability=0.0)
    assert second["sequence_number"] == first["sequence_number"] + 1
    assert second["scenario_time"] > first["scenario_time"]


def test_advance_and_emit_prints_influx_line(tmp_path, monkeypatch):
    import scripts.stream_vitals as sv

    monkeypatch.setattr(sv, "STATE_DIR", tmp_path)

    line = sv.advance_and_emit(ADMISSION, TICK)
    assert line is not None
    measurement, rest = line.split(" ", 1)
    assert measurement.startswith("vitals,event_id=")
    assert ",sequence_number=" in measurement
    timestamp_ns = int(rest.rsplit(" ", 1)[1])
    assert timestamp_ns > 0

    checkpoint = tmp_path / "W10001.json"
    assert checkpoint.exists()
    assert json.loads(checkpoint.read_text())["sequence_number"] == ADMISSION.backfill_ticks() + 1