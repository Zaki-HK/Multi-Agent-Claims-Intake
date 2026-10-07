"""Policy metadata and ingestion responses for the repository UI."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PolicyCoverageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    coverage_type: str = Field(min_length=1, max_length=128)
    covered_services: dict = Field(default_factory=dict)
    exclusions: dict = Field(default_factory=dict)
    deductible: float = Field(default=0, ge=0)
    copay: float = Field(default=0, ge=0)
    coinsurance_percent: float = Field(default=0, ge=0, le=100)
    out_of_pocket_max: float = Field(default=0, ge=0)
    annual_limit: float | None = Field(default=None, ge=0)


class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    policy_number: str = Field(min_length=1, max_length=64)
    holder_name: str = Field(min_length=1, max_length=255)
    plan_type: str = Field(min_length=1, max_length=64)
    effective_date: date
    expiration_date: date
    status: Literal["active", "inactive", "expired"] = "active"
    coverages: list[PolicyCoverageInput] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_dates(self) -> "PolicyCreate":
        if self.expiration_date < self.effective_date:
            raise ValueError("Expiration date cannot precede the effective date")
        return self


class PolicyResponse(BaseModel):
    id: UUID
    policy_number: str
    holder_name: str
    plan_type: str
    effective_date: date
    expiration_date: date
    status: str
    indexing_status: Literal["indexed", "not_indexed"]


class PolicyListResponse(BaseModel):
    items: list[PolicyResponse]
    total: int
    limit: int
    offset: int


class PolicyUploadResponse(BaseModel):
    policy_id: UUID
    indexing_status: Literal["indexed"] = "indexed"
    page_count: int
    chunk_count: int
    message: str = "Policy parsed and indexed successfully"
