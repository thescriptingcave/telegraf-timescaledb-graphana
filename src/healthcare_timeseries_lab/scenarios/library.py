from datetime import timedelta

from healthcare_timeseries_lab.scenarios.engine import (
    ConditionDefinition,
    ScenarioPhaseDefinition,
)
from healthcare_timeseries_lab.scenarios.models import (
    ConditionPhase,
    PhysiologicalEffect,
)


def progressive_hypoxemia() -> tuple[ConditionDefinition, ...]:
    return (
        ConditionDefinition(
            name="hypoxemia",
            effect=PhysiologicalEffect(
                spo2_delta_pct=-10.0,
            ),
            phases=(
                ScenarioPhaseDefinition(
                    phase=ConditionPhase.ONSET,
                    start_offset=timedelta(hours=2),
                    end_offset=timedelta(hours=2, minutes=15),
                    start_severity=0.0,
                    end_severity=0.2,
                ),
                ScenarioPhaseDefinition(
                    phase=ConditionPhase.PROGRESSION,
                    start_offset=timedelta(hours=2, minutes=15),
                    end_offset=timedelta(hours=3),
                    start_severity=0.2,
                    end_severity=1.0,
                ),
                ScenarioPhaseDefinition(
                    phase=ConditionPhase.PLATEAU,
                    start_offset=timedelta(hours=3),
                    end_offset=timedelta(hours=4),
                    start_severity=1.0,
                    end_severity=1.0,
                ),
                ScenarioPhaseDefinition(
                    phase=ConditionPhase.RECOVERY,
                    start_offset=timedelta(hours=4),
                    end_offset=timedelta(hours=5),
                    start_severity=1.0,
                    end_severity=0.0,
                ),
            ),
        ),
    )


def tachycardia() -> tuple[ConditionDefinition, ...]:
    return (
        ConditionDefinition(
            name="tachycardia",
            effect=PhysiologicalEffect(
                heart_rate_delta_bpm=40.0,
            ),
            phases=(
                ScenarioPhaseDefinition(
                    phase=ConditionPhase.ONSET,
                    start_offset=timedelta(hours=1),
                    end_offset=timedelta(hours=1, minutes=30),
                    start_severity=0.0,
                    end_severity=0.3,
                ),
                ScenarioPhaseDefinition(
                    phase=ConditionPhase.PROGRESSION,
                    start_offset=timedelta(hours=1, minutes=30),
                    end_offset=timedelta(hours=2),
                    start_severity=0.3,
                    end_severity=1.0,
                ),
                ScenarioPhaseDefinition(
                    phase=ConditionPhase.PLATEAU,
                    start_offset=timedelta(hours=2),
                    end_offset=timedelta(hours=3),
                    start_severity=1.0,
                    end_severity=1.0,
                ),
                ScenarioPhaseDefinition(
                    phase=ConditionPhase.RECOVERY,
                    start_offset=timedelta(hours=3),
                    end_offset=timedelta(hours=4),
                    start_severity=1.0,
                    end_severity=0.0,
                ),
            ),
        ),
    )