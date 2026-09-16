"""Device-layer configuration: how a monitor turns true physiology into
observed telemetry (Milestone 8).

The device layer lives between ``PhysiologicalState`` (true physiology) and
``VitalsTelemetryEvent`` (observed telemetry). It models measurement noise,
precision/rounding, sensor latency, clock skew, dropout, drift, spikes,
flatlines, and disconnects while keeping true physiology untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum

VITAL_CHANNELS: tuple[str, ...] = (
    "heart_rate_bpm",
    "spo2_pct",
    "respiration_rate_bpm",
    "temperature_c",
    "systolic_bp_mmhg",
    "diastolic_bp_mmhg",
)


class DeviceStatus(StrEnum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"


class QualityCode(StrEnum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    POOR = "POOR"
    LOST = "LOST"


@dataclass(frozen=True)
class DeviceChannelConfig:
    """Per-channel sensor behaviour.

    Channels without an explicit config are passed through unchanged; the
    config below only applies to the channels it names.
    """

    noise_stddev: float = 0.0
    precision: int = 0
    drift_per_hour: float = 0.0
    spike_probability: float = 0.0
    spike_amplitude: float = 0.0

    def __post_init__(self) -> None:
        if self.noise_stddev < 0:
            raise ValueError("noise_stddev must be non-negative")

        if self.precision < 0:
            raise ValueError("precision must be non-negative")

        if not 0.0 <= self.spike_probability <= 1.0:
            raise ValueError("spike_probability must be between 0.0 and 1.0")

        if self.spike_amplitude < 0:
            raise ValueError("spike_amplitude must be non-negative")


@dataclass(frozen=True)
class DeviceFaultWindow:
    start_offset: timedelta
    end_offset: timedelta

    def __post_init__(self) -> None:
        if self.start_offset < timedelta(0):
            raise ValueError("start_offset must be non-negative")

        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")


@dataclass(frozen=True)
class DisconnectWindow(DeviceFaultWindow):
    """Whole-device offline window; events are flagged, values frozen."""


@dataclass(frozen=True)
class FlatlineWindow(DeviceFaultWindow):
    """A single channel freezes to its pre-window value for the window."""

    channel: str
    value: float | None = None

    def __post_init__(self) -> None:
        if self.channel not in VITAL_CHANNELS:
            raise ValueError(
                f"unknown channel: {self.channel!r} "
                f"(expected one of {VITAL_CHANNELS})"
            )

        if self.start_offset < timedelta(0):
            raise ValueError("start_offset must be non-negative")

        if not self.start_offset < self.end_offset:
            raise ValueError("end_offset must be greater than start_offset")


@dataclass(frozen=True)
class DeviceSimulationConfig:
    seed: int = 0

    clock_skew: timedelta = timedelta(0)
    latency_seconds: float = 0.0
    dropout_probability: float = 0.0

    channels: dict[str, DeviceChannelConfig] = field(default_factory=dict)
    disconnect_windows: tuple[DisconnectWindow, ...] = ()
    flatline_windows: tuple[FlatlineWindow, ...] = ()

    def __post_init__(self) -> None:
        if self.latency_seconds < 0:
            raise ValueError("latency_seconds must be non-negative")

        if not 0.0 <= self.dropout_probability <= 1.0:
            raise ValueError("dropout_probability must be between 0.0 and 1.0")

        unknown = set(self.channels) - set(VITAL_CHANNELS)
        if unknown:
            raise ValueError(
                f"unknown channels: {sorted(unknown)} "
                f"(expected one of {VITAL_CHANNELS})"
            )


__all__ = [
    "VITAL_CHANNELS",
    "DeviceChannelConfig",
    "DeviceFaultWindow",
    "DeviceSimulationConfig",
    "DeviceStatus",
    "DisconnectWindow",
    "FlatlineWindow",
    "QualityCode",
]