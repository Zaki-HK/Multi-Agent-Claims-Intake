"""Versioned local ICD-10-CM/CPT reference lookup; no invented fallback codes."""

import asyncio
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import Settings, settings


class MedicalCode(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    system: Literal["ICD-10-CM", "CPT"]
    code: str = Field(min_length=1, max_length=16)
    description: str = Field(min_length=1, max_length=1000)
    keywords: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_code(self) -> "MedicalCode":
        pattern = r"[A-Z][0-9][A-Z0-9](?:\.[A-Z0-9]{1,4})?" if self.system == "ICD-10-CM" else r"(?:[0-9]{5}|[0-9]{4}[FTU])"
        if not re.fullmatch(pattern, self.code):
            raise ValueError("Reference code does not match its system format")
        return self


class MedicalCodeCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: str = Field(min_length=1)
    source: str = Field(min_length=1)
    valid_from: date
    valid_to: date
    codes: list[MedicalCode]

    @model_validator(mode="after")
    def validate_catalog(self) -> "MedicalCodeCatalog":
        if self.valid_to < self.valid_from:
            raise ValueError("Reference validity dates are reversed")
        identities = [(item.system, item.code) for item in self.codes]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate reference codes")
        return self


@lru_cache(maxsize=4)
def load_catalog(path: str, mtime_ns: int, size: int) -> MedicalCodeCatalog:
    # File metadata invalidates the process cache when a new catalog is mounted.
    return MedicalCodeCatalog.model_validate_json(Path(path).read_text(encoding="utf-8"))


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - {
        "a", "an", "and", "the", "of", "to", "with", "for", "in", "on", "was", "is",
        "unspecified", "other", "initial", "encounter",
    }


class MedicalCodeLookup:
    def __init__(self, config: Settings = settings) -> None:
        self.config = config

    def lookup(self, narrative: str, incident_date: str | None) -> dict:
        if not self.config.medical_code_reference_path:
            return {"status": "reference_unavailable", "candidates": [], "reference": None}
        try:
            path = Path(self.config.medical_code_reference_path).expanduser().resolve(strict=True)
            stat = path.stat()
        except FileNotFoundError:
            return {"status": "reference_unavailable", "candidates": [], "reference": None}
        catalog = load_catalog(str(path), stat.st_mtime_ns, stat.st_size)
        reference = catalog.model_dump(mode="json", exclude={"codes"})
        if not incident_date or not catalog.valid_from <= date.fromisoformat(incident_date) <= catalog.valid_to:
            return {"status": "reference_date_mismatch", "candidates": [], "reference": reference}
        tokens = words(narrative)
        normalized = " ".join(re.findall(r"[a-z0-9]+", narrative.lower()))
        ranked = []
        for item in catalog.codes:
            vocabulary = words(" ".join([item.description, *item.keywords]))
            overlap = len(tokens & vocabulary)
            explicit = bool(re.search(r"(?<![\w.])" + re.escape(item.code) + r"(?![\w.])", narrative, re.IGNORECASE))
            phrase = any(
                " " + " ".join(re.findall(r"[a-z0-9]+", keyword.lower())) + " " in " " + normalized + " "
                for keyword in item.keywords if words(keyword)
            )
            if overlap or explicit or phrase:
                score = overlap / max(len(vocabulary), 1) + 2 * explicit + int(phrase)
                ranked.append((score, item))
        ranked.sort(key=lambda pair: (-pair[0], pair[1].system, pair[1].code))
        # Retain candidates from each system so diagnoses cannot crowd out procedures.
        candidates = []
        for system in ("ICD-10-CM", "CPT"):
            candidates.extend(item.model_dump(mode="json") for _, item in
                              [pair for pair in ranked if pair[1].system == system][:self.config.medical_code_candidate_count])
        return {"status": "matched" if candidates else "no_reference_match",
                "candidates": candidates, "reference": reference}

    async def alookup(self, narrative: str, incident_date: str | None) -> dict:
        return await asyncio.to_thread(self.lookup, narrative, incident_date)
