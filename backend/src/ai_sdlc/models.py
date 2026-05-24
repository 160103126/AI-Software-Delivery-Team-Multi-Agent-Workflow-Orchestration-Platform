from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class WorkflowCreate(BaseModel):
    user_request: str = Field(..., min_length=3)
    user_id: str = "local-user"
    session_id: str = "local-session"
    max_iterations: int = Field(default=3, ge=1, le=10)


class ApprovalRequest(BaseModel):
    approved: bool
    comment: str = ""


class WorkflowResponse(BaseModel):
    workflow_id: str
    status: str
    state: Dict[str, Any]


class ErrorResponse(BaseModel):
    detail: str
    workflow_id: Optional[str] = None
