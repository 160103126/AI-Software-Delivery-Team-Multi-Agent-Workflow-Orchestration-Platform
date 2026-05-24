"""Context window management for agent prompts.

Each agent needs only a subset of the workflow state.  This module provides
utilities to extract, truncate, and format the relevant context so that
prompts stay within safe token limits regardless of how large the state
grows across iterations.

Design principles:
- Each agent declares which state fields it needs.
- Large text fields (generated_code, test_cases) are truncated to a
  configurable character limit with a clear "[TRUNCATED]" marker so the
  LLM knows content was cut.
- Structured fields (requirements, architecture, tasks) are serialised to
  compact JSON for smaller prompt footprint.
- The module is purely functional — no side effects, easy to test.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from .state import WorkflowState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Truncation helpers
# ---------------------------------------------------------------------------

# Default per-field character limits.  These are conservative estimates
# assuming ~4 chars per token;  8 000 chars ≈ 2 000 tokens.
DEFAULT_CHAR_LIMITS: Dict[str, int] = {
    "user_request": 2_000,
    "requirements": 4_000,
    "architecture": 4_000,
    "tasks": 4_000,
    "generated_code": 12_000,
    "test_cases": 6_000,
    "security_findings": 3_000,
    "review_comments": 3_000,
    "human_feedback": 2_000,
    "agent_feedback": 6_000,
}


def truncate(text: str, max_chars: int, label: str = "content") -> str:
    """Truncate text to *max_chars*, appending a marker if cut."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    marker = f"\n\n[TRUNCATED — {label} exceeded {max_chars:,} chars, {len(text) - max_chars:,} chars omitted]"
    logger.debug("Truncated %s from %d to %d chars", label, len(text), max_chars)
    return truncated + marker


def compact_json(obj: Any, max_chars: int, label: str = "json") -> str:
    """Serialise *obj* to compact JSON and truncate if needed."""
    text = json.dumps(obj, separators=(",", ":"), default=str)
    return truncate(text, max_chars, label)


def format_list(items: List[str], max_chars: int, label: str = "list") -> str:
    """Format a list of strings as bullet points, truncating if needed."""
    if not items:
        return "None"
    text = "\n".join(f"- {item}" for item in items)
    return truncate(text, max_chars, label)


def _read_workspace_files(workspace_dir: str, extension: str = ".py") -> str:
    """Helper to read all source files from the workspace into a single string."""
    if not workspace_dir or not os.path.exists(workspace_dir):
        return "No workspace files available."
    
    workspace = Path(workspace_dir)
    contents = []
    for file_path in workspace.rglob(f"*{extension}"):
        try:
            text = file_path.read_text(encoding="utf-8")
            contents.append(f"--- {file_path.name} ---\n{text}")
        except Exception:
            pass
            
    if not contents:
        return "No files found in workspace."
    return "\n\n".join(contents)


# ---------------------------------------------------------------------------
# Per-agent context builders
# ---------------------------------------------------------------------------

def product_owner_context(state: WorkflowState) -> str:
    """Product Owner only needs the raw user request."""
    request = state.get("user_request", "").strip()
    return truncate(request, DEFAULT_CHAR_LIMITS["user_request"], "user_request")


def architect_context(state: WorkflowState) -> str:
    """Architect needs the request and requirements."""
    limits = DEFAULT_CHAR_LIMITS
    sections = [
        f"Feature request:\n{truncate(state.get('user_request', ''), limits['user_request'], 'user_request')}",
        f"Requirements:\n{compact_json(state.get('requirements', {}), limits['requirements'], 'requirements')}",
    ]
    return "\n\n".join(sections)


def scrum_master_context(state: WorkflowState) -> str:
    """Scrum Master needs request, requirements, and architecture."""
    limits = DEFAULT_CHAR_LIMITS
    sections = [
        f"Request:\n{truncate(state.get('user_request', ''), limits['user_request'], 'user_request')}",
        f"Requirements:\n{compact_json(state.get('requirements', {}), limits['requirements'], 'requirements')}",
        f"Architecture:\n{compact_json(state.get('architecture', {}), limits['architecture'], 'architecture')}",
    ]
    return "\n\n".join(sections)


def developer_context(state: WorkflowState) -> str:
    """Developer needs everything relevant — but each piece truncated."""
    limits = DEFAULT_CHAR_LIMITS
    human_fb = state.get("human_feedback", "").strip() or "None"
    sections = [
        f"Request:\n{truncate(state.get('user_request', ''), limits['user_request'], 'user_request')}",
        f"Requirements:\n{compact_json(state.get('requirements', {}), limits['requirements'], 'requirements')}",
        f"Architecture:\n{compact_json(state.get('architecture', {}), limits['architecture'], 'architecture')}",
        f"Tasks:\n{compact_json(state.get('tasks', []), limits['tasks'], 'tasks')}",
        f"Human feedback:\n{truncate(human_fb, limits['human_feedback'], 'human_feedback')}",
    ]
    return "\n\n".join(sections)


def qa_context(state: WorkflowState) -> str:
    """QA only needs the request and generated code."""
    limits = DEFAULT_CHAR_LIMITS
    workspace_code = _read_workspace_files(state.get("workspace_dir", ""))
    sections = [
        f"Request:\n{truncate(state.get('user_request', ''), limits['user_request'], 'user_request')}",
        f"Generated code:\n{truncate(workspace_code, limits['generated_code'], 'generated_code')}",
    ]
    return "\n\n".join(sections)


def security_context(state: WorkflowState) -> str:
    """Security needs request, architecture summary, and generated code."""
    limits = DEFAULT_CHAR_LIMITS
    workspace_code = _read_workspace_files(state.get("workspace_dir", ""))
    sections = [
        f"Request:\n{truncate(state.get('user_request', ''), limits['user_request'], 'user_request')}",
        f"Architecture:\n{compact_json(state.get('architecture', {}), limits['architecture'], 'architecture')}",
        f"Generated code:\n{truncate(workspace_code, limits['generated_code'], 'generated_code')}",
    ]
    return "\n\n".join(sections)


def reviewer_context(state: WorkflowState) -> str:
    """Reviewer needs request, requirements, code, and tests."""
    limits = DEFAULT_CHAR_LIMITS
    workspace_code = _read_workspace_files(state.get("workspace_dir", ""))
    sections = [
        f"Request:\n{truncate(state.get('user_request', ''), limits['user_request'], 'user_request')}",
        f"Requirements:\n{compact_json(state.get('requirements', {}), limits['requirements'], 'requirements')}",
        f"Generated code and tests:\n{truncate(workspace_code, limits['generated_code'], 'generated_code')}",
    ]
    return "\n\n".join(sections)


def devops_context(state: WorkflowState) -> str:
    """DevOps needs request, architecture, and security findings."""
    limits = DEFAULT_CHAR_LIMITS
    sections = [
        f"Request:\n{truncate(state.get('user_request', ''), limits['user_request'], 'user_request')}",
        f"Architecture:\n{compact_json(state.get('architecture', {}), limits['architecture'], 'architecture')}",
        f"Security findings:\n{format_list(state.get('security_findings', []), limits['security_findings'], 'security_findings')}",
    ]
    return "\n\n".join(sections)


def agent_feedback_context(state: WorkflowState) -> str:
    """Build the inter-agent feedback block for the Developer, truncated."""
    limits = DEFAULT_CHAR_LIMITS
    sections = []
    test_cases = state.get("test_cases", "").strip()
    if test_cases:
        sections.append(f"QA test cases:\n{truncate(test_cases, limits['test_cases'], 'test_cases')}")
    security_findings = state.get("security_findings", [])
    if security_findings:
        sections.append(f"Security findings:\n{format_list(security_findings, limits['security_findings'], 'security_findings')}")
    review_comments = state.get("review_comments", [])
    if review_comments:
        sections.append(f"Code review comments:\n{format_list(review_comments, limits['review_comments'], 'review_comments')}")
    full = "\n\n".join(sections) if sections else "None"
    return truncate(full, limits["agent_feedback"], "agent_feedback")
