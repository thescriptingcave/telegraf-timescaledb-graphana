"""Device / fault layer between true physiology and observed telemetry (M8).

A ``DeviceSimulator`` sits between ``PhysiologicalState`` (true physiology)
and ``VitalsTelemetryEvent`` (observed telemetry), applying measurement noise,
precision/rounding, sensor latency, clock skew, dropout, drift, spikes,
flatlines, and disconnects.
"""

from __future__ import annotations

from healthcare_timeseries_lab.device.models import (
    VITAL_CHANNELS,
    DeviceChannelConfig,
    DeviceFaultWindow,
    DeviceSimulationConfig,
    DeviceStatus,
    DisconnectWindow,
    FlatlineWindow,
    QualityCode,
)
from healthcare_timeseries_lab.device.simulator import DeviceSimulator


def default_bedside_monitor_config() -> DeviceSimulationConfig:
    """A realistic default bedside-monitor fault profile.

    Applies per-channel noise and standard monitor precision/rounding, a
    small sensor latency, light random dropout, and occasional spikes on the
    most artifact-prone channels (SpO2, heart rate). Fault windows and drift
    are deliberately left off by default so demos stay readable; they are
    fully configurable.
    """
    return DeviceSimulationConfig(
        seed=42,
        latency_seconds=0.5,
        dropout_probability=0.005,
        channels={
            "heart_rate_bpm": DeviceChannelConfig(
                noise_stddev=0.4,
                precision=0,
                spike_probability=0.003,
                spike_amplitude=4.0,
            ),
            "spo2_pct": DeviceChannelConfig(
                noise_stddev=0.25,
                precision=0,
                spike_probability=0.003,
                spike_amplitude=2.0,
            ),
            "respiration_rate_bpm": DeviceChannelConfig(
                noise_stddev=0.2,
                precision=0,
            ),
            "temperature_c": DeviceChannelConfig(
                noise_stddev=0.02,
                precision=1,
            ),
            "systolic_bp_mmhg": DeviceChannelConfig(
                noise_stddev=0.5,
                precision=0,
            ),
            "diastolic_bp_mmhg": DeviceChannelConfig(
                noise_stddev=0.4,
                precision=0,
            ),
        },
    )


__all__ = [
    "VITAL_CHANNELS",
    "DeviceChannelConfig",
    "DeviceFaultWindow",
    "DeviceSimulationConfig",
    "DeviceSimulator",
    "DeviceStatus",
    "DisconnectWindow",
    "FlatlineWindow",
    "QualityCode",
    "default_bedside_monitor_config",
]