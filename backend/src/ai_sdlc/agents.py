from __future__ import annotations

import base64
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from textwrap import dedent
from typing import Any, Dict, List

from .context import (
    agent_feedback_context,
    architect_context,
    developer_context,
    devops_context,
    product_owner_context,
    qa_context,
    reviewer_context,
    scrum_master_context,
    security_context,
)
from .llm import invoke_json_model, invoke_agent_with_tools
from .tools import get_workspace_tools
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
    request = product_owner_context(state)
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
                f"Design a concise architecture for this feature request and requirements.\n\n"
                f"{architect_context(state)}"
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
                f"Break this feature plan into implementation tasks with dependencies.\n\n"
                f"{scrum_master_context(state)}"
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
        "Developer started: workflow_id=%s next_iteration=%s auto_rework=%s",
        state.get("workflow_id"),
        state.get("iteration_count", 0) + 1,
        state.get("auto_rework_count", 0),
    )
    iteration = state.get("iteration_count", 0) + 1
    ctx = developer_context(state)
    agent_fb = agent_feedback_context(state)
    workspace_dir = state.get("workspace_dir", "")
    
    try:
        tools = get_workspace_tools(workspace_dir)
        system_prompt = (
            "You are a senior Python/FastAPI developer. "
            "You have access to tools to write files and list directories. "
            f"Your workspace is at {workspace_dir}. "
            "Write the actual FastAPI implementation files to the workspace. "
            "If agent feedback (QA tests, security findings, review comments) is provided, "
            "you MUST address every finding in your revised implementation. "
            "When you are done writing the files, return a brief summary of what you implemented as your final answer."
        )
        user_prompt = (
            "Implement this feature.\n\n"
            f"{ctx}\n\n"
            f"Agent feedback from QA/Security/Reviewer:\n{agent_fb}"
        )
        
        generated_code_summary = invoke_agent_with_tools(system_prompt, user_prompt, tools)
        logger.info("Developer used ReAct loop successfully: workflow_id=%s", state.get("workflow_id"))
    except Exception as exc:
        logger.warning(
            "Developer falling back to minimal output: workflow_id=%s reason=%s",
            state.get("workflow_id"),
            exc,
        )
        human_feedback = state.get("human_feedback", "").strip()
        generated_code_summary = dedent(
            f"""
            # LLM code generation failed for iteration {iteration}.
            # Fallback reason: {exc}
            # Requested feature: {state['user_request']}
            # Human feedback: {human_feedback or 'None'}
            # Agent feedback: {agent_fb}
            """
        ).strip()
    return {
        "generated_code": generated_code_summary,
        "iteration_count": iteration,
        "approved": None,
        "status": "implementation_ready",
        "execution_log": _log("Developer"),
    }


def qa_agent(state: WorkflowState) -> Dict[str, Any]:
    logger.info("QA Engineer started: workflow_id=%s", state.get("workflow_id"))
    workspace_dir = state.get("workspace_dir", "")
    try:
        tools = get_workspace_tools(workspace_dir)
        system_prompt = (
            "You are a QA engineer. "
            "You have access to tools to write files, read files, and run commands. "
            f"Your workspace is at {workspace_dir}. "
            "1. Read the code files in the workspace. "
            "2. Write pytest tests for the implementation. "
            "3. Run the tests using the `run_command` tool (e.g., `pytest`). "
            "4. Iterate if tests fail due to syntax errors in your tests. "
            "When you are done, return a summary of the test results and any issues found in the implementation as your final answer."
        )
        user_prompt = (
            f"Create and run tests for this implementation.\n\n"
            f"{qa_context(state)}"
        )
        
        test_cases_summary = invoke_agent_with_tools(system_prompt, user_prompt, tools)
        logger.info("QA Engineer used ReAct loop successfully: workflow_id=%s", state.get("workflow_id"))
    except Exception as exc:
        logger.warning(
            "QA Engineer falling back to minimal output: workflow_id=%s reason=%s",
            state.get("workflow_id"),
            exc,
        )
        test_cases_summary = f"# LLM test generation failed. Fallback reason: {exc}"
    return {"test_cases": test_cases_summary, "execution_log": _log("QA Engineer")}


def security_agent(state: WorkflowState) -> Dict[str, Any]:
    logger.info("Security Agent started: workflow_id=%s", state.get("workflow_id"))
    workspace_dir = state.get("workspace_dir", "")
    try:
        tools = get_workspace_tools(workspace_dir)
        system_prompt = (
            "You are an application security reviewer. "
            "You have access to tools to read files, write files, and run commands. "
            f"Your workspace is at {workspace_dir}. "
            "Use your tools to read the workspace codebase, and run any security testing tools you deem necessary (like bandit for SAST, and pip-audit for SCA). "
            "When you are done, return a detailed summary of the security risks found as your final answer. "
            "If no issues are found, state 'No security issues found.' clearly."
        )
        user_prompt = (
            f"Review this generated implementation for security risks.\n\n"
            f"{security_context(state)}"
        )
        
        output = invoke_agent_with_tools(system_prompt, user_prompt, tools)
        findings = [output]
        logger.info("Security Agent used ReAct loop successfully: workflow_id=%s", state.get("workflow_id"))
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
    workspace_dir = state.get("workspace_dir", "")
    try:
        tools = get_workspace_tools(workspace_dir)
        system_prompt = (
            "You are a senior code reviewer. "
            "You have access to tools to read files, write files, and run commands. "
            f"Your workspace is at {workspace_dir}. "
            "Use your tools to read the actual workspace files to evaluate maintainability, correctness, and missing tests. "
            "You can even run tests or linting tools to verify your assertions if you wish. "
            "When you are done, return a detailed summary of your review comments as your final answer. "
            "If the code is perfect, state 'Code looks great, no actionable feedback' clearly."
        )
        user_prompt = (
            f"Review this implementation for maintainability, correctness, and missing tests.\n\n"
            f"{reviewer_context(state)}"
        )
        
        output = invoke_agent_with_tools(system_prompt, user_prompt, tools)
        comments = [output]
        logger.info("Reviewer used ReAct loop successfully: workflow_id=%s", state.get("workflow_id"))
    except Exception as exc:
        logger.warning(
            "Reviewer falling back to minimal output: workflow_id=%s reason=%s",
            state.get("workflow_id"),
            exc,
        )
        comments = [f"LLM code review failed. Fallback reason: {exc}"]
    return {"review_comments": comments, "execution_log": _log("Reviewer")}


def _has_actionable_findings(state: WorkflowState) -> bool:
    """Check if QA/Security/Reviewer found issues worth auto-reworking."""
    fallback_marker = "LLM"
    
    for finding in state.get("security_findings", []):
        text = finding.lower()
        if fallback_marker.lower() in text:
            continue
        if "no security issues found" not in text:
            logger.info("Security issue found: %s", finding)
            return True
            
    for comment in state.get("review_comments", []):
        text = comment.lower()
        if fallback_marker.lower() in text:
            continue
        if "no actionable feedback" not in text:
            logger.info("Review issue found: %s", comment)
            return True
            
    return False


def aggregate_agent(state: WorkflowState) -> Dict[str, Any]:
    auto_rework_count = state.get("auto_rework_count", 0)
    max_auto_reworks = state.get("max_auto_reworks", 1)
    has_issues = _has_actionable_findings(state)

    if has_issues and auto_rework_count < max_auto_reworks:
        logger.info(
            "Aggregate: auto-rework triggered (round %s/%s): workflow_id=%s",
            auto_rework_count + 1,
            max_auto_reworks,
            state.get("workflow_id"),
        )
        return {
            "auto_rework_count": auto_rework_count + 1,
            "status": "auto_rework",
            "execution_log": _log("Aggregation (auto-rework)"),
        }

    logger.info(
        "Aggregate: forwarding to human review: workflow_id=%s issues_found=%s auto_rework_count=%s",
        state.get("workflow_id"),
        has_issues,
        auto_rework_count,
    )
    # CRITICAL: We must reset 'approved' to None so the graph pauses and waits for the user again
    return {"status": "awaiting_approval", "approved": None, "execution_log": _log("Aggregation")}


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
                f"Create a concise GCP deployment plan for this approved workflow.\n\n"
                f"{devops_context(state)}"
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


def archiver_node(state: WorkflowState) -> Dict[str, Any]:
    """Zip the workspace and base64 encode it for state storage."""
    logger.info("Archiver started: workflow_id=%s", state.get("workflow_id"))
    workspace_dir = state.get("workspace_dir", "")
    
    if not workspace_dir or not os.path.exists(workspace_dir):
        return {"project_archive_base64": None, "execution_log": _log("Archiver (skipped - no workspace)")}
        
    try:
        # Create a temp file for the zip
        temp_zip = tempfile.mktemp(suffix=".zip")
        shutil.make_archive(temp_zip.replace('.zip', ''), 'zip', workspace_dir)
        
        with open(temp_zip, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
            
        # Clean up temp zip and the entire workspace directory to free up memory
        os.remove(temp_zip)
        shutil.rmtree(workspace_dir, ignore_errors=True)
        
        logger.info("Archiver completed successfully. Workspace cleaned up.")
        return {"project_archive_base64": b64_data, "execution_log": _log("Archiver")}
    except Exception as exc:
        logger.warning(f"Archiver failed: {exc}")
        return {"project_archive_base64": None, "execution_log": _log("Archiver (failed)")}
