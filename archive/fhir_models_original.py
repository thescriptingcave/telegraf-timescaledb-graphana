"""LOINC mapping and FHIR resource builders for simulated vitals.

Each simulated vitals sample maps onto a *vital-signs panel* observation per
FHIR R5 convention: parent ``Observation`` carries the ``85353-1`` Vital
Signs panel code, and each of the six telemetry channels becomes a structured
``component`` with its own LOINC code and UCUM unit.

Panels (LOINC / unit system):
* 84257-7 Vital signs - heart rate (8867-4, beats/minute)
* 84868-6 Vital signs - oxygen saturation (2708-6, %)
* 84258-5 Vital signs - respiratory rate (9279-1, breaths/minute)
* 8310-5 Body temperature (Cel)
* 8462-4 Diastolic blood pressure (mm[Hg])
* 8480-6 Systolic blood pressure (mm[Hg])
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fhir.resources.codeableconcept import CodeableConcept, Coding
from fhir.resources.encounter import Encounter, EncounterStatus
from fhir.resources.fhirtypes import (
    DateTime,
)
from fhir.resources.humanname import HumanName
from fhir.resources.meta import Meta
from fhir.resources.observation import (
    Observation,
    ObservationComponent,
    ObservationStatus,
)
from fhir.resources.patient import Patient
from fhir.resources.period import Period
from fhir.resources.quantity import Quantity
from fhir.resources.reference import Reference

from healthcare_timeseries_lab.patients.models import PatientProfile

LOINC_SYSTEM = "http://loinc.org"
VITAL_SIGNS_PANEL_LOINC = "85353-1"
VITAL_SIGNS_PANEL_DISPLAY = "Vital signs"


VITAL_LOINC_CODES: dict[str, str] = {
    "heart_rate": "8867-4",
    "spo2": "2708-6",
    "respiration": "9279-1",
    "temperature": "8310-5",
    "systolic_bp": "8480-6",
    "diastolic_bp": "8462-4",
}


class VitalsObservationBuilder:
    """Build FHIR `Observation` resources from a patient profile.

    Each vital channel maps to a LOINC panel; the six channels collapse into
    ``Observation.component`` entries so a single ``Observation`` per sample
    keeps the bundle compact for FHIR transaction POSTs.
    """

    def __init__(self, profile: PatientProfile, *, server_base: str) -> None:
        self.profile = profile
        self._server_base = server_base.rstrip("/")

    def _loinc_coding(self, loinc_code: str, *, display: str | None = None) -> Coding:
        return Coding(system=LOINC_SYSTEM, code=loinc_code, display=display)

    def _quantity(
        self,
        *,
        value: float,
        unit: str,
        system: str = "http://unitsofmeasure.org",
        code: str | None = None,
    ) -> Quantity:
        return Quantity(value=value, unit=unit, system=system, code=code)

    def patient(self) -> Patient:
        p = self.profile
        return Patient(
            id=str(p.patient_id),
            name=[HumanName(family=p.last_name, given=[p.first_name])],
            gender=p.sex,
            birthDate=str(p.date_of_birth) if p.date_of_birth else None,
            meta=Meta(profile=["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"]),
        )

    def encounter(self) -> Encounter:
        p = self.profile
        return Encounter(
            id=f"enc-{uuid.uuid5(p.patient_id, 'encounter').hex[:24]}",
            status=EncounterStatus.FINISHED,
            class_=Coding(
                system="http://terminology.hl7.org/CodeSystem/v3-ActCode",
                code="IMP",
                display="inpatient encounter",
            ),
            subject=Reference(reference=f"Patient/{p.patient_id}"),
            period=Period(start=DateTime.now(), end=DateTime.now().replace(day=1)),
        )

    def observation(self, *, event_time: datetime, vitals: dict[str, float]) -> Observation:
        """Build a single vital-signs panel Observation at ``event_time``."""
        p = self.profile
        components = []
        for name, loinc_code in VITAL_LOINC_CODES.items():
            unit = self._unit_for(name)
            components.append(
                ObservationComponent(
                    code=self._component_code(name, loinc_code),
                    valueQuantity=self._quantity(
                        value=vitals[name],
                        unit=unit["unit"],
                        system=unit["system"],
                        code=unit["code"],
                    ),
                )
            )

        return Observation(
            id=f"obs-{uuid.uuid5(p.patient_id, 'observation').hex[:24]}",
            status=ObservationStatus.FINAL,
            code=CodeableConcept(
                coding=[self._loinc_coding(VITAL_SIGNS_PANEL_LOINC, VITAL_SIGNS_PANEL_DISPLAY)]
            ),
            subject=Reference(reference=f"Patient/{p.patient_id}"),
            effectiveDateTime=event_time.astimezone(UTC),
            component=components,
        )

    def _component_code(self, name: str, loinc_code: str) -> CodeableConcept:
        display = {
            "heart_rate": "Heart rate",
            "spo2": "Oxygen saturation",
            "respiration": "Respiratory rate",
            "temperature": "Body temperature",
            "systolic_bp": "Systolic blood pressure",
            "diastolic_bp": "Diastolic blood pressure",
        }[name]
        return CodeableConcept(
            coding=[
                self._loinc_coding(loinc_code, display),
            ]
        )

    def _unit_for(self, name: str) -> dict[str, str]:
        return {
            "heart_rate": {"unit": "beats/minute", "system": "http://unitsofmeasure.org", "code": "/min"},
            "spo2": {"unit": "%", "system": "http://unitsofmeasure.org", "code": "%"},
            "respiration": {"unit": "breaths/minute", "system": "http://unitsofmeasure.org", "code": "/min"},
            "temperature": {"unit": "Cel", "system": "http://unitsofmeasure.org", "code": "Cel"},
            "systolic_bp": {"unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
            "diastolic_bp": {"unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
        }[name]


__all__ = [
    "LOINC_SYSTEM",
    "VITAL_LOINC_CODES",
    "VITAL_SIGNS_PANEL_DISPLAY",
    "VITAL_SIGNS_PANEL_LOINC",
    "VitalsObservationBuilder",
]
