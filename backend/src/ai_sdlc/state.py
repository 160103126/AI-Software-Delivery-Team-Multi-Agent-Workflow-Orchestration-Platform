from __future__ import annotations

from operator import add
from typing import Annotated, Any, Dict, List, Optional

from typing_extensions import TypedDict


class WorkflowState(TypedDict, total=False):
    workflow_id: str
    user_id: str
    session_id: str
    user_request: str
    requirements: Dict[str, Any]
    architecture: Dict[str, Any]
    tasks: List[Dict[str, Any]]
    generated_code: str
    test_cases: str
    security_findings: List[str]
    review_comments: List[str]
    deployment_plan: Dict[str, Any]
    approved: Optional[bool]
    human_feedback: str
    iteration_count: int
    max_iterations: int
    auto_rework_count: int
    max_auto_reworks: int
    status: str
    workspace_dir: str
    project_archive_base64: Optional[str]
    execution_log: Annotated[List[str], add]

