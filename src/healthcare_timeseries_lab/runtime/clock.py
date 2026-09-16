from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class SimulationClock:
    start_time: datetime
    step: timedelta

    def __post_init__(self) -> None:
        if self.start_time.tzinfo is None:
            raise ValueError("start_time must be timezone-aware")

        if self.step <= timedelta(0):
            raise ValueError("step must be greater than zero")

        self._current_time = self.start_time

    @property
    def now(self) -> datetime:
        return self._current_time

    def advance(self) -> datetime:
        self._current_time += self.step
        return self._current_time