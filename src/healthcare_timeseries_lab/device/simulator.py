"""DeviceSimulator: turn true physiology into observed telemetry (M8).

One ``DeviceSimulator`` instance is stateful — it tracks the first observed
timestamp (for drift/window math), the last observed values per channel
(for disconnect/flatline freezing), and a seeded RNG for stochastic faults.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from random import Random
from uuid import UUID

from healthcare_timeseries_lab.device.models import (
    VITAL_CHANNELS,
    DeviceChannelConfig,
    DeviceFaultWindow,
    DeviceSimulationConfig,
    DeviceStatus,
    FlatlineWindow,
    QualityCode,
)
from healthcare_timeseries_lab.physiology.models import PhysiologicalState
from healthcare_timeseries_lab.telemetry.events import VitalsTelemetryEvent


class DeviceSimulator:
    def __init__(
        self,
        *,
        config: DeviceSimulationConfig,
        rng: Random | None = None,
    ) -> None:
        self._config = config
        self._rng = rng or Random(config.seed)
        self._start_time: datetime | None = None
        self._last_observed: dict[str, float] = {}
        self._flatline_anchor: dict[str, float] = {}

    def observe(
        self,
        *,
        state: PhysiologicalState,
        simulation_id: UUID,
        patient_id: UUID,
        device_id: UUID,
        sequence_number: int,
        event_id: UUID,
    ) -> VitalsTelemetryEvent | None:
        """Transform one true state into one observed event (or skip it)."""
        if self._start_time is None:
            self._start_time = state.timestamp
        elapsed = state.timestamp - self._start_time

        if self._rng.random() < self._config.dropout_probability:
            return None

        disconnected = self._in_window(
            elapsed,
            self._config.disconnect_windows,
        )

        if disconnected:
            device_status = DeviceStatus.DISCONNECTED
        else:
            device_status = DeviceStatus.CONNECTED

        event_time = (
            state.timestamp
            + self._config.clock_skew
            + timedelta(seconds=self._next_latency())
        )

        values: dict[str, float] = {}
        degraded = False
        flatlined = False

        for channel in VITAL_CHANNELS:
            true_value = getattr(state, channel)

            if disconnected:
                values[channel] = self._last_observed.get(channel, true_value)
                continue

            if self._active_flatline(channel, elapsed) is not None:
                if channel not in self._flatline_anchor:
                    self._flatline_anchor[channel] = self._last_observed.get(
                        channel,
                        true_value,
                    )
                values[channel] = self._flatline_anchor[channel]
                self._last_observed[channel] = values[channel]
                flatlined = True
                continue

            self._flatline_anchor.pop(channel, None)

            sensor = self._config.channels.get(channel)
            value = true_value

            if sensor is not None:
                value, channel_degraded = self._apply_sensor(
                    value,
                    sensor,
                    elapsed,
                )
                degraded = degraded or channel_degraded

            values[channel] = value
            self._last_observed[channel] = value

        if disconnected:
            quality = QualityCode.LOST
        elif flatlined:
            quality = QualityCode.POOR
        elif degraded:
            quality = QualityCode.DEGRADED
        else:
            quality = QualityCode.GOOD

        return VitalsTelemetryEvent(
            event_id=event_id,
            simulation_id=simulation_id,
            patient_id=patient_id,
            device_id=device_id,
            event_time=event_time,
            sequence_number=sequence_number,
            heart_rate_bpm=values["heart_rate_bpm"],
            spo2_pct=values["spo2_pct"],
            respiration_rate_bpm=values["respiration_rate_bpm"],
            temperature_c=values["temperature_c"],
            systolic_bp_mmhg=values["systolic_bp_mmhg"],
            diastolic_bp_mmhg=values["diastolic_bp_mmhg"],
            device_status=device_status.value,
            quality_code=quality.value,
        )

    def _apply_sensor(
        self,
        value: float,
        sensor: DeviceChannelConfig,
        elapsed: timedelta,
    ) -> tuple[float, bool]:
        degraded = False

        if sensor.noise_stddev:
            value = value + self._rng.gauss(0.0, sensor.noise_stddev)

        if sensor.drift_per_hour and elapsed > timedelta(0):
            value = value + sensor.drift_per_hour * (
                elapsed.total_seconds() / 3600.0
            )
            degraded = True

        if sensor.spike_probability and (
            self._rng.random() < sensor.spike_probability
        ):
            direction = self._rng.choice([-1.0, 1.0])
            value = value + direction * sensor.spike_amplitude
            degraded = True

        return round(value, sensor.precision), degraded

    def _in_window(
        self,
        elapsed: timedelta,
        windows: tuple[DeviceFaultWindow, ...],
    ) -> bool:
        return any(
            window.start_offset <= elapsed < window.end_offset
            for window in windows
        )

    def _active_flatline(
        self,
        channel: str,
        elapsed: timedelta,
    ) -> FlatlineWindow | None:
        for window in self._config.flatline_windows:
            if (
                window.channel == channel
                and window.start_offset <= elapsed < window.end_offset
            ):
                return window
        return None

    def _next_latency(self) -> float:
        latency = self._config.latency_seconds
        if latency <= 0:
            return 0.0
        return max(0.0, self._rng.gauss(latency, latency / 3.0))


__all__ = ["DeviceSimulator"]