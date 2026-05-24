from __future__ import annotations

from datetime import datetime, timezone
from textwrap import dedent
from typing import Any, Dict, List

from .llm import invoke_json_model
from .schemas import ArchitectureOutput, RequirementsOutput
from .state import WorkflowState


def _log(agent_name: str) -> List[str]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return [f"{timestamp} | {agent_name} completed"]


def product_owner_agent(state: WorkflowState) -> Dict[str, Any]:
    request = state["user_request"].strip()
    fallback_requirements = {
        "summary": request,
        "functional": [
            "Expose a clear API contract for the requested feature.",
            "Validate all incoming payloads with typed schemas.",
            "Return predictable success and error responses.",
        ],
        "non_functional": [
            "Keep the implementation testable and modular.",
            "Add observable workflow logs for each major step.",
            "Prefer secure defaults for authentication and secrets.",
        ],
        "acceptance_criteria": [
            f"The system implements: {request}",
            "Automated tests cover success and failure paths.",
            "Security review has no unresolved high-risk findings.",
            "A human reviewer can approve or reject the workflow output.",
        ],
        "priority": "HIGH",
    }
    try:
        requirements = invoke_json_model(
            system_prompt=(
                "You are a senior product owner for an AI software delivery team. "
                "Return only valid JSON matching this schema: "
                "{summary: string, functional: string[], non_functional: string[], "
                "acceptance_criteria: string[], priority: LOW|MEDIUM|HIGH|CRITICAL}."
            ),
            user_prompt=(
                f"Analyze this feature request and produce concise implementation-ready requirements:\n\n{request}"
            ),
            schema=RequirementsOutput,
        )
    except Exception as exc:
        requirements = fallback_requirements
        requirements["llm_fallback_reason"] = str(exc)
    return {"requirements": requirements, "status": "requirements_defined", "execution_log": _log("Product Owner")}


def architect_agent(state: WorkflowState) -> Dict[str, Any]:
    fallback_architecture = {
        "style": "FastAPI service orchestrated by LangGraph",
        "apis": [
            "POST /workflows",
            "GET /workflows/{workflow_id}",
            "POST /workflows/{workflow_id}/approval",
        ],
        "services": ["orchestrator", "agent_nodes", "workflow_store", "approval_gateway"],
        "data": {
            "workflow_state": "LangGraph state object",
            "persistence_next": "PostgreSQL checkpoints plus Redis short-term memory",
        },
        "security": [
            "Use Secret Manager or environment variables for provider keys.",
            "Validate tool file paths before writes.",
            "Require human approval before deployment.",
        ],
    }
    try:
        architecture = invoke_json_model(
            system_prompt=(
                "You are a pragmatic software architect. Return only valid JSON matching this schema: "
                "{style: string, apis: string[], services: string[], "
                "data: {workflow_state: string, persistence_next: string}, security: string[]}."
            ),
            user_prompt=(
                "Design a concise architecture for this feature request and requirements.\n\n"
                f"Feature request: {state['user_request']}\n\n"
                f"Requirements: {state.get('requirements', {})}"
            ),
            schema=ArchitectureOutput,
        )
    except Exception as exc:
        architecture = fallback_architecture
        architecture["llm_fallback_reason"] = str(exc)
    return {"architecture": architecture, "status": "architecture_defined", "execution_log": _log("Architect")}


def scrum_master_agent(state: WorkflowState) -> Dict[str, Any]:
    tasks = [
        {"id": "T1", "title": "Define API schemas", "priority": "HIGH", "depends_on": []},
        {"id": "T2", "title": "Implement orchestration graph", "priority": "HIGH", "depends_on": ["T1"]},
        {"id": "T3", "title": "Generate feature implementation", "priority": "HIGH", "depends_on": ["T2"]},
        {"id": "T4", "title": "Add tests and quality checks", "priority": "MEDIUM", "depends_on": ["T3"]},
        {"id": "T5", "title": "Prepare deployment plan", "priority": "MEDIUM", "depends_on": ["T4"]},
    ]
    return {"tasks": tasks, "status": "tasks_planned", "execution_log": _log("Scrum Master")}


def developer_agent(state: WorkflowState) -> Dict[str, Any]:
    iteration = state.get("iteration_count", 0) + 1
    feedback = state.get("human_feedback", "").strip()
    feedback_note = f"\n# Rework note: {feedback}" if feedback else ""
    generated_code = dedent(
        f"""
        # Generated implementation sketch, iteration {iteration}
        from fastapi import APIRouter

        router = APIRouter(prefix="/feature", tags=["feature"])

        @router.post("/execute")
        async def execute_feature(payload: dict) -> dict:
            \"\"\"Implements: {state['user_request']}\"\"\"
            return {{"status": "accepted", "payload": payload}}
        {feedback_note}
        """
    ).strip()
    return {
        "generated_code": generated_code,
        "iteration_count": iteration,
        "approved": None,
        "status": "implementation_ready",
        "execution_log": _log("Developer"),
    }


def qa_agent(state: WorkflowState) -> Dict[str, Any]:
    test_cases = dedent(
        """
        def test_execute_feature_success(client):
            response = client.post("/feature/execute", json={"sample": "value"})
            assert response.status_code == 200
            assert response.json()["status"] == "accepted"

        def test_execute_feature_rejects_invalid_payload(client):
            response = client.post("/feature/execute", json=None)
            assert response.status_code in {400, 422}
        """
    ).strip()
    return {"test_cases": test_cases, "execution_log": _log("QA Engineer")}


def security_agent(state: WorkflowState) -> Dict[str, Any]:
    findings = [
        "No hardcoded secrets in generated implementation sketch.",
        "Human approval gate exists before deployment.",
        "Next step: run Bandit/Semgrep on materialized source files.",
    ]
    return {"security_findings": findings, "execution_log": _log("Security Agent")}


def reviewer_agent(state: WorkflowState) -> Dict[str, Any]:
    comments = [
        "Implementation is intentionally minimal and should be expanded with typed request/response models.",
        "Add integration tests once generated code is written to a concrete project path.",
        "Keep provider-specific LLM code behind the agent boundary.",
    ]
    return {"review_comments": comments, "execution_log": _log("Reviewer")}


def aggregate_agent(state: WorkflowState) -> Dict[str, Any]:
    return {"status": "awaiting_approval", "execution_log": _log("Aggregation")}


def human_review_node(state: WorkflowState) -> Dict[str, Any]:
    if state.get("approved") is True:
        return {"status": "approved", "execution_log": _log("Human Approval")}
    if state.get("approved") is False:
        return {"status": "rework_requested", "execution_log": _log("Human Approval")}
    return {"status": "awaiting_approval", "execution_log": _log("Human Approval")}


def devops_agent(state: WorkflowState) -> Dict[str, Any]:
    deployment_plan = {
        "container": "Build a Docker image and push it to Artifact Registry.",
        "runtime": "Deploy FastAPI on Cloud Run.",
        "managed_services": ["Cloud SQL PostgreSQL", "Memorystore Redis", "Secret Manager", "Cloud Logging"],
        "release_gate": "Deploy only after approved == true.",
    }
    return {"deployment_plan": deployment_plan, "status": "ready_for_deployment", "execution_log": _log("DevOps Agent")}
