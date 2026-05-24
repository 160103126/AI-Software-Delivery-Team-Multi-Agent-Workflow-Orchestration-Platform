from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class RequirementsOutput(BaseModel):
    summary: str
    functional: List[str] = Field(min_length=1)
    non_functional: List[str] = Field(min_length=1)
    acceptance_criteria: List[str] = Field(min_length=1)
    priority: str = Field(pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")


class ArchitectureDataOutput(BaseModel):
    workflow_state: str
    persistence_next: str


class ArchitectureOutput(BaseModel):
    style: str
    apis: List[str] = Field(min_length=1)
    services: List[str] = Field(min_length=1)
    data: ArchitectureDataOutput
    security: List[str] = Field(min_length=1)
