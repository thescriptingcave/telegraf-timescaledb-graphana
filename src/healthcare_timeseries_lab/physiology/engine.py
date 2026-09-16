from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from random import Random

from healthcare_timeseries_lab.patients.models import PatientProfile
from healthcare_timeseries_lab.physiology.models import PhysiologicalState
from healthcare_timeseries_lab.scenarios.models import ActiveCondition


@dataclass(frozen=True)
class SignalParameters:
    mean_reversion_strength: float
    noise_stddev: float


@dataclass(frozen=True)
class OxygenCouplingParameters:
    heart_rate_per_spo2_deficit: float
    respiration_per_spo2_deficit: float

    heart_rate_lag: timedelta
    respiration_lag: timedelta


@dataclass(frozen=True)
class CombinedPhysiologicalEffects:
    heart_rate_delta_bpm: float = 0.0
    spo2_delta_pct: float = 0.0
    respiration_rate_delta_bpm: float = 0.0
    temperature_delta_c: float = 0.0
    systolic_bp_delta_mmhg: float = 0.0
    diastolic_bp_delta_mmhg: float = 0.0


@dataclass(frozen=True)
class OxygenDeficitObservation:
    timestamp: datetime
    deficit: float


class PhysiologyEngine:
    def __init__(self, rng: Random) -> None:
        self._rng = rng

        self._heart_rate = SignalParameters(
            mean_reversion_strength=0.05,
            noise_stddev=0.35,
        )

        self._spo2 = SignalParameters(
            mean_reversion_strength=0.08,
            noise_stddev=0.05,
        )

        self._respiration = SignalParameters(
            mean_reversion_strength=0.06,
            noise_stddev=0.12,
        )

        self._temperature = SignalParameters(
            mean_reversion_strength=0.03,
            noise_stddev=0.01,
        )

        self._systolic_bp = SignalParameters(
            mean_reversion_strength=0.05,
            noise_stddev=0.45,
        )

        self._diastolic_bp = SignalParameters(
            mean_reversion_strength=0.05,
            noise_stddev=0.30,
        )

        self._oxygen_coupling = OxygenCouplingParameters(
            heart_rate_per_spo2_deficit=1.2,
            respiration_per_spo2_deficit=0.6,
            heart_rate_lag=timedelta(seconds=60),
            respiration_lag=timedelta(seconds=30),
        )

        self._oxygen_deficit_history: deque[
            OxygenDeficitObservation
        ] = deque()

    def next_state(
        self,
        *,
        patient: PatientProfile,
        previous_state: PhysiologicalState,
        timestamp: datetime,
        active_conditions: Iterable[ActiveCondition] = (),
    ) -> PhysiologicalState:
        variability = patient.variability_factor

        effects = self._combine_condition_effects(
            active_conditions,
        )

        current_oxygen_deficit = max(
            0.0,
            patient.baseline_spo2_pct
            - previous_state.spo2_pct,
        )

        self._record_oxygen_deficit(
            timestamp=previous_state.timestamp,
            deficit=current_oxygen_deficit,
        )

        respiration_oxygen_deficit = (
            self._delayed_oxygen_deficit(
                timestamp=timestamp,
                lag=self._oxygen_coupling.respiration_lag,
            )
        )

        heart_rate_oxygen_deficit = (
            self._delayed_oxygen_deficit(
                timestamp=timestamp,
                lag=self._oxygen_coupling.heart_rate_lag,
            )
        )

        coupled_heart_rate_effect = (
            heart_rate_oxygen_deficit
            * self._oxygen_coupling.heart_rate_per_spo2_deficit
        )

        coupled_respiration_effect = (
            respiration_oxygen_deficit
            * self._oxygen_coupling.respiration_per_spo2_deficit
        )

        heart_rate_target = (
            patient.baseline_heart_rate_bpm
            + effects.heart_rate_delta_bpm
            + coupled_heart_rate_effect
        )

        spo2_target = (
            patient.baseline_spo2_pct
            + effects.spo2_delta_pct
        )

        respiration_target = (
            patient.baseline_respiration_rate_bpm
            + effects.respiration_rate_delta_bpm
            + coupled_respiration_effect
        )

        temperature_target = (
            patient.baseline_temperature_c
            + effects.temperature_delta_c
        )

        systolic_target = (
            patient.baseline_systolic_bp_mmhg
            + effects.systolic_bp_delta_mmhg
        )

        diastolic_target = (
            patient.baseline_diastolic_bp_mmhg
            + effects.diastolic_bp_delta_mmhg
        )

        heart_rate = self._next_value(
            current=previous_state.heart_rate_bpm,
            target=heart_rate_target,
            parameters=self._heart_rate,
            variability=variability,
        )

        spo2 = self._next_value(
            current=previous_state.spo2_pct,
            target=spo2_target,
            parameters=self._spo2,
            variability=variability,
        )

        respiration = self._next_value(
            current=previous_state.respiration_rate_bpm,
            target=respiration_target,
            parameters=self._respiration,
            variability=variability,
        )

        temperature = self._next_value(
            current=previous_state.temperature_c,
            target=temperature_target,
            parameters=self._temperature,
            variability=variability,
        )

        systolic = self._next_value(
            current=previous_state.systolic_bp_mmhg,
            target=systolic_target,
            parameters=self._systolic_bp,
            variability=variability,
        )

        diastolic = self._next_value(
            current=previous_state.diastolic_bp_mmhg,
            target=diastolic_target,
            parameters=self._diastolic_bp,
            variability=variability,
        )

        if systolic <= diastolic:
            systolic = diastolic + 1.0

        return PhysiologicalState(
            timestamp=timestamp,
            heart_rate_bpm=heart_rate,
            spo2_pct=spo2,
            respiration_rate_bpm=respiration,
            temperature_c=temperature,
            systolic_bp_mmhg=systolic,
            diastolic_bp_mmhg=diastolic,
        )

    def _record_oxygen_deficit(
        self,
        *,
        timestamp: datetime,
        deficit: float,
    ) -> None:
        self._oxygen_deficit_history.append(
            OxygenDeficitObservation(
                timestamp=timestamp,
                deficit=deficit,
            )
        )

        longest_lag = max(
            self._oxygen_coupling.heart_rate_lag,
            self._oxygen_coupling.respiration_lag,
        )

        oldest_needed = timestamp - longest_lag - timedelta(minutes=1)

        while (
            self._oxygen_deficit_history
            and self._oxygen_deficit_history[0].timestamp
            < oldest_needed
        ):
            self._oxygen_deficit_history.popleft()

    def _delayed_oxygen_deficit(
        self,
        *,
        timestamp: datetime,
        lag: timedelta,
    ) -> float:
        target_time = timestamp - lag

        selected_deficit = 0.0

        for observation in self._oxygen_deficit_history:
            if observation.timestamp > target_time:
                break

            selected_deficit = observation.deficit

        return selected_deficit

    def _next_value(
        self,
        *,
        current: float,
        target: float,
        parameters: SignalParameters,
        variability: float,
    ) -> float:
        mean_reversion = (
            target - current
        ) * parameters.mean_reversion_strength

        noise = self._rng.gauss(
            mu=0.0,
            sigma=parameters.noise_stddev * variability,
        )

        return current + mean_reversion + noise

    @staticmethod
    def _combine_condition_effects(
        active_conditions: Iterable[ActiveCondition],
    ) -> CombinedPhysiologicalEffects:
        total = CombinedPhysiologicalEffects()

        for condition in active_conditions:
            severity = condition.severity
            effect = condition.effect

            total = CombinedPhysiologicalEffects(
                heart_rate_delta_bpm=(
                    total.heart_rate_delta_bpm
                    + effect.heart_rate_delta_bpm * severity
                ),
                spo2_delta_pct=(
                    total.spo2_delta_pct
                    + effect.spo2_delta_pct * severity
                ),
                respiration_rate_delta_bpm=(
                    total.respiration_rate_delta_bpm
                    + effect.respiration_rate_delta_bpm * severity
                ),
                temperature_delta_c=(
                    total.temperature_delta_c
                    + effect.temperature_delta_c * severity
                ),
                systolic_bp_delta_mmhg=(
                    total.systolic_bp_delta_mmhg
                    + effect.systolic_bp_delta_mmhg * severity
                ),
                diastolic_bp_delta_mmhg=(
                    total.diastolic_bp_delta_mmhg
                    + effect.diastolic_bp_delta_mmhg * severity
                ),
            )

        return total