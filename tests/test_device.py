from datetime import timedelta

from healthcare_timeseries_lab.device import default_bedside_monitor_config
from healthcare_timeseries_lab.device.simulator import DeviceSimulator
from healthcare_timeseries_lab.physiology.models import PhysiologicalState
from scripts.ward_registry import WARD_ADMISSIONS


def test_dropout_never_fabricates_values():
    from healthcare_timeseries_lab.device.models import DeviceSimulationConfig

    admission = WARD_ADMISSIONS[2]  # Ivy W10003, stable
    device = DeviceSimulator(
        config=DeviceSimulationConfig(seed=21, dropout_probability=0.15),
        rng=None,
    )
    state = PhysiologicalState(
        timestamp=admission.admitted_at,
        heart_rate_bpm=69.0,
        spo2_pct=98.0,
        respiration_rate_bpm=13.0,
        temperature_c=36.6,
        systolic_bp_mmhg=110.0,
        diastolic_bp_mmhg=70.0,
    )
    seen = 0
    drops = 0
    for seq in range(1, 200):
        event = device.observe(
            state=state,
            simulation_id=admission.simulation_id,
            patient_id=admission.patient_id,
            device_id=admission.device_id,
            sequence_number=seq,
            event_id=admission.simulation_id,
        )
        if event is None:
            drops += 1
            continue
        seen += 1
        assert abs(event.heart_rate_bpm - 69.0) < 2.0
        assert abs(event.spo2_pct - 98.0) <= 1.0
    assert 0 < drops < seen
    assert seen > 100


def test_precision_rounding_and_quality_good():
    admission = WARD_ADMISSIONS[2]
    device = DeviceSimulator(
        config=default_bedside_monitor_config(),
        rng=None,
    )
    state = PhysiologicalState(
        timestamp=admission.admitted_at,
        heart_rate_bpm=72.37,
        spo2_pct=97.6,
        respiration_rate_bpm=14.2,
        temperature_c=36.81,
        systolic_bp_mmhg=118.6,
        diastolic_bp_mmhg=74.1,
    )
    event = device.observe(
        state=state,
        simulation_id=admission.simulation_id,
        patient_id=admission.patient_id,
        device_id=admission.device_id,
        sequence_number=1,
        event_id=admission.simulation_id,
    )
    assert event is not None
    assert event.heart_rate_bpm == round(72.37, 0)
    assert event.temperature_c == round(36.81, 1)
    assert event.quality_code == "GOOD"
    assert event.device_status == "CONNECTED"


def test_flatline_freezes_channel_and_flags_poor():

    from healthcare_timeseries_lab.device.models import (
        DeviceChannelConfig,
        DeviceSimulationConfig,
        FlatlineWindow,
    )

    admission = WARD_ADMISSIONS[2]
    config = DeviceSimulationConfig(
        seed=3,
        channels={"spo2_pct": DeviceChannelConfig(noise_stddev=0.1)},
        flatline_windows=(FlatlineWindow(
            channel="spo2_pct",
            start_offset=timedelta(seconds=5),
            end_offset=timedelta(seconds=11),
        ),),
    )
    device = DeviceSimulator(
        config=config,
        rng=None,
    )
    values = []
    qualities = []
    for seq in range(1, 4):
        state = PhysiologicalState(
            timestamp=admission.admitted_at + timedelta(seconds=5 * seq),
            heart_rate_bpm=72.0,
            spo2_pct=97.0,
            respiration_rate_bpm=14.0,
            temperature_c=36.6,
            systolic_bp_mmhg=110.0,
            diastolic_bp_mmhg=70.0,
        )
        event = device.observe(
            state=state,
            simulation_id=admission.simulation_id,
            patient_id=admission.patient_id,
            device_id=admission.device_id,
            sequence_number=seq,
            event_id=admission.simulation_id,
        )
        values.append(event.spo2_pct)
        qualities.append(event.quality_code)
    assert values[1] == values[2]
    assert qualities[2] == "POOR"


def test_disconnect_freezes_and_marks_lost():

    from healthcare_timeseries_lab.device.models import (
        DeviceSimulationConfig,
        DisconnectWindow,
    )

    admission = WARD_ADMISSIONS[2]
    config = DeviceSimulationConfig(
        seed=1,
        disconnect_windows=(DisconnectWindow(
            start_offset=timedelta(seconds=8),
            end_offset=timedelta(seconds=30),
        ),),
    )
    device = DeviceSimulator(config=config, rng=None)
    states = []
    statuses = []
    for seq in range(1, 4):
        state = PhysiologicalState(
            timestamp=admission.admitted_at + timedelta(seconds=5 * seq),
            heart_rate_bpm=72.0,
            spo2_pct=97.0,
            respiration_rate_bpm=14.0,
            temperature_c=36.6,
            systolic_bp_mmhg=110.0,
            diastolic_bp_mmhg=70.0,
        )
        event = device.observe(
            state=state,
            simulation_id=admission.simulation_id,
            patient_id=admission.patient_id,
            device_id=admission.device_id,
            sequence_number=seq,
            event_id=admission.simulation_id,
        )
        states.append(event)
        statuses.append(event.device_status)
    assert statuses[0] == "CONNECTED"
    assert statuses[1] == "CONNECTED"
    assert statuses[2] == "DISCONNECTED"
    assert states[2].quality_code == "LOST"
    assert states[2].heart_rate_bpm == states[1].heart_rate_bpm