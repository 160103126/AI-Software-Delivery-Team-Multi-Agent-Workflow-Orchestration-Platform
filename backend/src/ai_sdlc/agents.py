from __future__ import annotations

import logging
from datetime import datetime, timezone
from textwrap import dedent
from typing import Any, Dict, List

from .llm import invoke_json_model
from .schemas import (
    ArchitectureOutput,
    DeploymentPlanOutput,
    DeveloperOutput,
    QaOutput,
    RequirementsOutput,
    ReviewerOutput,
    ScrumOutput,
    SecurityOutput,
)
from .state import WorkflowState

logger = logging.getLogger(__name__)


def _log(agent_name: str) -> List[str]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return [f"{timestamp} | {agent_name} completed"]


def product_owner_agent(state: WorkflowState) -> Dict[str, Any]:
    logger.info("Product Owner started: workflow_id=%s", state.get("workflow_id"))
    request = state["user_request"].strip()
    fallback_requirements = {
        "summary": request,
        "functional": [],
        "non_functional": [],
        "acceptance_criteria": [
            "LLM-backed requirement analysis did not complete; retry after resolving the fallback reason.",
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
        logger.info("Product Owner used Gemini successfully: workflow_id=%s", state.get("workflow_id"))
    except Exception as exc:
        logger.warning(
            "Product Owner falling back to deterministic output: workflow_id=%s reason=%s",
            state.get("workflow_id"),
            exc,
        )
        requirements = fallback_requirements
        requirements["llm_fallback_reason"] = str(exc)
    return {"requirements": requirements, "status": "requirements_defined", "execution_log": _log("Product Owner")}


def architect_agent(state: WorkflowState) -> Dict[str, Any]:
    logger.info("Architect started: workflow_id=%s", state.get("workflow_id"))
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
        logger.info("Architect used Gemini successfully: workflow_id=%s", state.get("workflow_id"))
    except Exception as exc:
        logger.warning(
            "Architect falling back to deterministic output: workflow_id=%s reason=%s",
            state.get("workflow_id"),
            exc,
        )
        architecture = fallback_architecture
        architecture["llm_fallback_reason"] = str(exc)
    return {"architecture": architecture, "status": "architecture_defined", "execution_log": _log("Architect")}


def scrum_master_agent(state: WorkflowState) -> Dict[str, Any]:
    logger.info("Scrum Master started: workflow_id=%s", state.get("workflow_id"))
    try:
        output = invoke_json_model(
            system_prompt=(
                "You are a scrum master. Return only valid JSON matching this schema: "
                "{tasks: [{id: string, title: string, priority: LOW|MEDIUM|HIGH|CRITICAL, depends_on: string[]}]}."
            ),
            user_prompt=(
                "Break this feature plan into implementation tasks with dependencies.\n\n"
                f"Request: {state['user_request']}\n\n"
                f"Requirements: {state.get('requirements', {})}\n\n"
                f"Architecture: {state.get('architecture', {})}"
            ),
            schema=ScrumOutput,
        )
        tasks = output["tasks"]
        logger.info("Scrum Master used Gemini successfully: workflow_id=%s", state.get("workflow_id"))
    except Exception as exc:
        logger.warning(
            "Scrum Master falling back to minimal output: workflow_id=%s reason=%s",
            state.get("workflow_id"),
            exc,
        )
        tasks = [
            {
                "id": "T1",
                "title": "Retry LLM task planning after resolving fallback reason.",
                "priority": "HIGH",
                "depends_on": [],
                "llm_fallback_reason": str(exc),
            }
        ]
    return {"tasks": tasks, "status": "tasks_planned", "execution_log": _log("Scrum Master")}


def developer_agent(state: WorkflowState) -> Dict[str, Any]:
    logger.info(
        "Developer started: workflow_id=%s next_iteration=%s",
        state.get("workflow_id"),
        state.get("iteration_count", 0) + 1,
    )
    iteration = state.get("iteration_count", 0) + 1
    feedback = state.get("human_feedback", "").strip()
    try:
        output = invoke_json_model(
            system_prompt=(
                "You are a senior Python/FastAPI developer. Return only valid JSON matching this schema: "
                "{generated_code: string}. Include concise, runnable FastAPI-oriented code only."
            ),
            user_prompt=(
                "Generate an implementation sketch for this feature.\n\n"
                f"Request: {state['user_request']}\n\n"
                f"Requirements: {state.get('requirements', {})}\n\n"
                f"Architecture: {state.get('architecture', {})}\n\n"
                f"Tasks: {state.get('tasks', [])}\n\n"
                f"Human feedback for this iteration: {feedback or 'None'}"
            ),
            schema=DeveloperOutput,
        )
        generated_code = output["generated_code"]
        logger.info("Developer used Gemini successfully: workflow_id=%s", state.get("workflow_id"))
    except Exception as exc:
        logger.warning(
            "Developer falling back to minimal output: workflow_id=%s reason=%s",
            state.get("workflow_id"),
            exc,
        )
        generated_code = dedent(
            f"""
            # LLM code generation failed for iteration {iteration}.
            # Fallback reason: {exc}
            # Requested feature: {state['user_request']}
            # Human feedback: {feedback or 'None'}
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
    logger.info("QA Engineer started: workflow_id=%s", state.get("workflow_id"))
    try:
        output = invoke_json_model(
            system_prompt="You are a QA engineer. Return only valid JSON matching this schema: {test_cases: string}.",
            user_prompt=(
                "Create pytest test cases for this implementation.\n\n"
                f"Request: {state['user_request']}\n\n"
                f"Generated code: {state.get('generated_code', '')}"
            ),
            schema=QaOutput,
        )
        test_cases = output["test_cases"]
        logger.info("QA Engineer used Gemini successfully: workflow_id=%s", state.get("workflow_id"))
    except Exception as exc:
        logger.warning(
            "QA Engineer falling back to minimal output: workflow_id=%s reason=%s",
            state.get("workflow_id"),
            exc,
        )
        test_cases = f"# LLM test generation failed. Fallback reason: {exc}"
    return {"test_cases": test_cases, "execution_log": _log("QA Engineer")}


def security_agent(state: WorkflowState) -> Dict[str, Any]:
    logger.info("Security Agent started: workflow_id=%s", state.get("workflow_id"))
    try:
        output = invoke_json_model(
            system_prompt=(
                "You are an application security reviewer. Return only valid JSON matching this schema: "
                "{security_findings: string[]}."
            ),
            user_prompt=(
                "Review this generated implementation for security risks.\n\n"
                f"Request: {state['user_request']}\n\n"
                f"Architecture: {state.get('architecture', {})}\n\n"
                f"Generated code: {state.get('generated_code', '')}"
            ),
            schema=SecurityOutput,
        )
        findings = output["security_findings"]
        logger.info("Security Agent used Gemini successfully: workflow_id=%s", state.get("workflow_id"))
    except Exception as exc:
        logger.warning(
            "Security Agent falling back to minimal output: workflow_id=%s reason=%s",
            state.get("workflow_id"),
            exc,
        )
        findings = [f"LLM security review failed. Fallback reason: {exc}"]
    return {"security_findings": findings, "execution_log": _log("Security Agent")}


def reviewer_agent(state: WorkflowState) -> Dict[str, Any]:
    logger.info("Reviewer started: workflow_id=%s", state.get("workflow_id"))
    try:
        output = invoke_json_model(
            system_prompt=(
                "You are a senior code reviewer. Return only valid JSON matching this schema: "
                "{review_comments: string[]}."
            ),
            user_prompt=(
                "Review this implementation for maintainability, correctness, and missing tests.\n\n"
                f"Request: {state['user_request']}\n\n"
                f"Requirements: {state.get('requirements', {})}\n\n"
                f"Generated code: {state.get('generated_code', '')}\n\n"
                f"Test cases: {state.get('test_cases', '')}"
            ),
            schema=ReviewerOutput,
        )
        comments = output["review_comments"]
        logger.info("Reviewer used Gemini successfully: workflow_id=%s", state.get("workflow_id"))
    except Exception as exc:
        logger.warning(
            "Reviewer falling back to minimal output: workflow_id=%s reason=%s",
            state.get("workflow_id"),
            exc,
        )
        comments = [f"LLM code review failed. Fallback reason: {exc}"]
    return {"review_comments": comments, "execution_log": _log("Reviewer")}


def aggregate_agent(state: WorkflowState) -> Dict[str, Any]:
    logger.info("Aggregation completed: workflow_id=%s", state.get("workflow_id"))
    return {"status": "awaiting_approval", "execution_log": _log("Aggregation")}


def human_review_node(state: WorkflowState) -> Dict[str, Any]:
    logger.info(
        "Human review gate: workflow_id=%s approved=%s iteration=%s",
        state.get("workflow_id"),
        state.get("approved"),
        state.get("iteration_count"),
    )
    if state.get("approved") is True:
        return {"status": "approved", "execution_log": _log("Human Approval")}
    if state.get("approved") is False:
        return {"status": "rework_requested", "execution_log": _log("Human Approval")}
    return {"status": "awaiting_approval", "execution_log": _log("Human Approval")}


def devops_agent(state: WorkflowState) -> Dict[str, Any]:
    logger.info("DevOps Agent started: workflow_id=%s", state.get("workflow_id"))
    try:
        deployment_plan = invoke_json_model(
            system_prompt=(
                "You are a GCP DevOps engineer. Return only valid JSON matching this schema: "
                "{container: string, runtime: string, managed_services: string[], release_gate: string}."
            ),
            user_prompt=(
                "Create a concise GCP deployment plan for this approved workflow.\n\n"
                f"Request: {state['user_request']}\n\n"
                f"Architecture: {state.get('architecture', {})}\n\n"
                f"Security findings: {state.get('security_findings', [])}"
            ),
            schema=DeploymentPlanOutput,
        )
        logger.info("DevOps Agent used Gemini successfully: workflow_id=%s", state.get("workflow_id"))
    except Exception as exc:
        logger.warning(
            "DevOps Agent falling back to minimal output: workflow_id=%s reason=%s",
            state.get("workflow_id"),
            exc,
        )
        deployment_plan = {
            "container": f"LLM deployment planning failed. Fallback reason: {exc}",
            "runtime": "Manual deployment review required.",
            "managed_services": [],
            "release_gate": "Do not deploy until LLM fallback reason is resolved or a human approves a manual plan.",
        }
    return {"deployment_plan": deployment_plan, "status": "ready_for_deployment", "execution_log": _log("DevOps Agent")}
