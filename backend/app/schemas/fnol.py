"""Validated input and structured multimodal extraction contracts."""

from datetime import date
from typing_extensions import TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FNOLData(TypedDict):
    claimant_name: str | None
    policy_number: str | None
    incident_date: str | None
    incident_description: str
    injury_type: str | None
    body_part_affected: str | None
    treatment_received: str | None
    provider_name: str | None
    estimated_amount: float | None
    extraction_confidence: float
    raw_text: str
    missing_fields: list[str]


class FNOLExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    claimant_name: str | None = Field(default=None, max_length=255)
    policy_number: str | None = Field(default=None, max_length=64)
    incident_date: date | None = None
    incident_description: str = Field(default="", max_length=20_000)
    injury_type: str | None = Field(default=None, max_length=128)
    body_part_affected: str | None = Field(default=None, max_length=128)
    treatment_received: str | None = Field(default=None, max_length=20_000)
    provider_name: str | None = Field(default=None, max_length=255)
    estimated_amount: float | None = Field(default=None, ge=0)
    extraction_confidence: float = Field(ge=0, le=1)

    @field_validator(
        "claimant_name", "policy_number", "incident_date", "injury_type",
        "body_part_affected", "treatment_received", "provider_name", mode="before",
    )
    @classmethod
    def empty_to_none(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    def to_fnol_data(self, raw_text: str) -> FNOLData:
        data = self.model_dump(mode="json")
        data["raw_text"] = raw_text
        data["missing_fields"] = [
            name for name in ("claimant_name", "policy_number", "incident_date", "incident_description")
            if not data[name]
        ]
        return data


class FNOLSubmission(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    description: str = Field(min_length=1, description="Incident narrative or attached image context")


class FNOLResponse(BaseModel):
    claim_id: str
    claim_number: str
    status: str
    extracted_data: dict
    missing_fields: list[str]
    message: str
