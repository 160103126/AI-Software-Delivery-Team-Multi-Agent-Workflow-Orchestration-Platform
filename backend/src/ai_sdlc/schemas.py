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


class TaskOutput(BaseModel):
    id: str
    title: str
    priority: str = Field(pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    depends_on: List[str] = []


class ScrumOutput(BaseModel):
    tasks: List[TaskOutput] = Field(min_length=1)


class DeveloperOutput(BaseModel):
    generated_code: str = Field(min_length=1)


class QaOutput(BaseModel):
    test_cases: str = Field(min_length=1)


class SecurityOutput(BaseModel):
    security_findings: List[str] = Field(min_length=1)


class ReviewerOutput(BaseModel):
    review_comments: List[str] = Field(min_length=1)


class DeploymentPlanOutput(BaseModel):
    container: str
    runtime: str
    managed_services: List[str] = Field(min_length=1)
    release_gate: str
