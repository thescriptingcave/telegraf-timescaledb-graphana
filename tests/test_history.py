from itertools import islice

from scripts.generate_history import simulate_admission
from scripts.ward_registry import admission_for

MARCUS = admission_for("W10004")


def _collect(admission, ticks: int):
    rows = []
    for vitals_row, truth, reads in islice(simulate_admission(admission), ticks):
        rows.append((vitals_row[0] if vitals_row else None, truth[0], len(reads)))
    return rows


def test_backfill_is_deterministic_for_a_slice():
    a = _collect(MARCUS, 4_000)
    b = _collect(MARCUS, 4_000)
    assert a == b


def test_backfill_row_shapes():
    for vitals_row, truth, reads in islice(simulate_admission(MARCUS), 50):
        assert len(truth) == 12
        assert truth[1].tzinfo is not None
        if vitals_row is not None:
            assert len(vitals_row) == 15
            assert vitals_row[1].tzinfo is not None
        assert len(reads) in (6, 12)
        for reading in reads:
            assert reading[5] in ("bpm", "%", "°C", "mmHg")


def test_full_short_stay_counts_are_consistent():
    ticks = 0
    vitals = 0
    readings = 0
    for vitals_row, _truth, reads in simulate_admission(MARCUS):
        ticks += 1
        readings += len(reads)
        if vitals_row is not None:
            vitals += 1

    assert ticks == MARCUS.backfill_ticks()
    assert readings == 6 * ticks + 6 * vitals
    assert 0.70 * ticks <= vitals <= 0.95 * ticks


def test_off_monitor_windows_are_gaps():
    from scripts.ward_registry import in_off_monitor_window

    checked = 0
    for i, (vitals_row, _truth, _reads) in enumerate(simulate_admission(MARCUS)):
        if i > 30_000:
            break
        if vitals_row is not None:
            assert not in_off_monitor_window(vitals_row[1]), (
                f"emitted during an off-monitor window at {vitals_row[1]}"
            )
            checked += 1
    assert checked > 0