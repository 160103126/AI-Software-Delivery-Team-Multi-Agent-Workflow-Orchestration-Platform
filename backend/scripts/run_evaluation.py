"""LangSmith Evaluation Script for AI Software Delivery Team.

Runs a golden dataset of prompts through the workflow API, scores each
output with deterministic evaluators, and uploads results to LangSmith
for regression tracking.

Usage:
    # Against local server (default)
    python backend/scripts/run_evaluation.py

    # Against deployed Cloud Run
    python backend/scripts/run_evaluation.py --api-url https://ai-sdlc-backend-xxx.run.app

    # Custom experiment name
    python backend/scripts/run_evaluation.py --experiment "v2.0-flash-lite"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from typing import Any

import requests
from langsmith import Client
from langsmith.evaluation import evaluate, EvaluationResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Golden Dataset — prompts with known expected properties
# ---------------------------------------------------------------------------

GOLDEN_DATASET_NAME = "ai-sdlc-golden-tests"

GOLDEN_EXAMPLES = [
    {
        "input": (
            "Build a user authentication API with JWT tokens. "
            "It should have register, login, and a protected /me endpoint. "
            "Passwords must be hashed with bcrypt. Tokens expire after 30 minutes. "
            "Return proper 401/403 errors for invalid or expired tokens."
        ),
        "expected": {
            "description": "Auth API with password hashing, JWT signing/verification, and protected routes",
            "security_sensitive": True,
            "must_handle": ["expired token", "invalid token", "duplicate email", "weak password"],
        },
    },
    {
        "input": (
            "Create an API rate limiter middleware using a sliding window algorithm. "
            "It should support per-IP and per-API-key limits, configurable window size "
            "and max requests. Return 429 Too Many Requests with a Retry-After header "
            "when the limit is exceeded. Store counters in memory with automatic expiry."
        ),
        "expected": {
            "description": "Sliding window rate limiter with per-client tracking and proper HTTP 429 responses",
            "security_sensitive": False,
            "must_handle": ["concurrent requests", "window expiry", "multiple clients"],
        },
    },
    {
        "input": (
            "Build a file upload service that accepts CSV files up to 10MB, "
            "validates the CSV structure (must have headers: name, email, age), "
            "rejects rows with invalid emails or negative ages, "
            "and returns a JSON summary with total rows, valid rows, and a list of errors with line numbers."
        ),
        "expected": {
            "description": "CSV upload with structural validation, row-level error reporting, and size limits",
            "security_sensitive": False,
            "must_handle": ["oversized file", "malformed CSV", "invalid email format", "negative age"],
        },
    },
    {
        "input": (
            "Create a webhook delivery system with retry logic. "
            "It should accept a target URL and payload, attempt delivery with POST, "
            "retry up to 3 times with exponential backoff (1s, 2s, 4s) on failure, "
            "log each attempt with status code and timestamp, "
            "and return a delivery report with all attempts."
        ),
        "expected": {
            "description": "Webhook dispatcher with exponential backoff retry, attempt logging, and delivery reports",
            "security_sensitive": False,
            "must_handle": ["timeout", "connection error", "non-2xx response", "max retries exhausted"],
        },
    },
    {
        "input": (
            "Build a multi-tenant task management API with role-based access control. "
            "Each tenant has users with roles: admin, member, viewer. "
            "Admins can create/delete tasks and manage users. "
            "Members can create tasks and update their own. "
            "Viewers can only read. "
            "Tasks must be isolated between tenants — a user in tenant A must never see tenant B's tasks."
        ),
        "expected": {
            "description": "Multi-tenant RBAC API with tenant isolation and 3-tier permission model",
            "security_sensitive": True,
            "must_handle": ["cross-tenant access", "insufficient permissions", "role escalation"],
        },
    },
    {
        "input": (
            "Build a blog API with SQLite persistence. "
            "Posts have a title, body, author, tags (many-to-many), and timestamps. "
            "Support filtering by tag, full-text search on title and body, "
            "pagination with cursor-based navigation, "
            "and a GET /stats endpoint that returns total posts, top 5 tags by usage count, "
            "and average posts per day."
        ),
        "expected": {
            "description": "Blog API with relational data, many-to-many tags, search, pagination, and analytics",
            "security_sensitive": False,
            "must_handle": ["empty database", "invalid cursor", "tag not found", "SQL injection prevention"],
        },
    },
    {
        "input": (
            "Create a CLI tool that watches a directory for new JSON files, "
            "validates each file against a schema (must have fields: id, timestamp, value), "
            "transforms valid files by adding a computed 'status' field based on value thresholds "
            "(low < 10, medium 10-90, high > 90), "
            "moves processed files to an 'output' folder, and logs errors for invalid files."
        ),
        "expected": {
            "description": "File watcher CLI with schema validation, transformation rules, and error logging",
            "security_sensitive": False,
            "must_handle": ["malformed JSON", "missing fields", "permission error", "empty directory"],
        },
    },
    {
        "input": (
            "Build an async job queue with a REST API. "
            "POST /jobs accepts a task type and payload, returns a job ID immediately. "
            "Jobs run in background worker threads with a configurable pool size. "
            "GET /jobs/{id} returns the job status (queued, running, completed, failed), "
            "result if completed, error message if failed, and timing (queued_at, started_at, finished_at). "
            "Support job cancellation via DELETE /jobs/{id} and a GET /jobs endpoint with status filtering."
        ),
        "expected": {
            "description": "Async job queue with background workers, status tracking, cancellation, and timing",
            "security_sensitive": False,
            "must_handle": ["worker pool exhaustion", "job cancellation mid-execution", "invalid job ID", "concurrent access"],
        },
    },
]


# ---------------------------------------------------------------------------
# Evaluators — all deterministic, no LLM judge
# ---------------------------------------------------------------------------


def workflow_completed(run, example) -> EvaluationResult:
    """Did the workflow reach awaiting_approval without crashing?"""
    outputs = run.outputs or {}
    status = outputs.get("status", "")
    success = status in ("awaiting_approval", "ready_for_deployment")
    return EvaluationResult(
        key="workflow_completed",
        score=1.0 if success else 0.0,
        comment=f"Final status: {status}",
    )


def code_generated(run, example) -> EvaluationResult:
    """Did the Developer agent produce non-empty code?"""
    outputs = run.outputs or {}
    code = outputs.get("generated_code", "")
    has_code = bool(code.strip()) and "fallback" not in code.lower()[:100]
    return EvaluationResult(
        key="code_generated",
        score=1.0 if has_code else 0.0,
        comment=f"Code length: {len(code)} chars" if has_code else "No real code generated (fallback or empty)",
    )


def tests_generated(run, example) -> EvaluationResult:
    """Did the QA agent produce test functions?"""
    outputs = run.outputs or {}
    tests = outputs.get("test_cases", "")
    has_tests = "def test_" in tests or "class Test" in tests
    return EvaluationResult(
        key="tests_generated",
        score=1.0 if has_tests else 0.0,
        comment="Test functions found" if has_tests else "No test functions detected",
    )


def security_clean(run, example) -> EvaluationResult:
    """Did the Security agent report zero actionable findings?"""
    outputs = run.outputs or {}
    findings = outputs.get("security_findings", [])
    clean_markers = ["no security issues found", "no issues", "no vulnerabilities"]
    fallback_marker = "llm"

    actionable = []
    for finding in findings:
        text = finding.lower()
        if fallback_marker in text:
            continue
        if any(m in text for m in clean_markers):
            continue
        actionable.append(finding)

    return EvaluationResult(
        key="security_clean",
        score=1.0 if len(actionable) == 0 else 0.0,
        comment=f"{len(actionable)} actionable finding(s)" if actionable else "Clean",
    )


def no_llm_fallback(run, example) -> EvaluationResult:
    """Did ALL agents use the LLM successfully (no deterministic fallbacks)?"""
    outputs = run.outputs or {}
    fallback_fields = ["requirements", "architecture", "generated_code"]
    fallbacks = []

    for field in fallback_fields:
        value = outputs.get(field, "")
        text = json.dumps(value) if isinstance(value, dict) else str(value)
        if "llm_fallback_reason" in text or "LLM code generation failed" in text:
            fallbacks.append(field)

    return EvaluationResult(
        key="no_llm_fallback",
        score=1.0 if len(fallbacks) == 0 else 0.0,
        comment=f"Fallbacks in: {', '.join(fallbacks)}" if fallbacks else "All agents used LLM",
    )


# ---------------------------------------------------------------------------
# Workflow runner — calls the actual API
# ---------------------------------------------------------------------------


def create_workflow_runner(api_url: str, timeout: int = 300):
    """Create a function that runs a prompt through the workflow API."""

    def run_workflow(inputs: dict) -> dict:
        """Run a single workflow and return the final state."""
        user_request = inputs["input"]
        logger.info("Running workflow for: %s", user_request[:60])

        try:
            # Use the synchronous (non-streaming) endpoint for evaluation
            response = requests.post(
                f"{api_url}/workflows",
                json={"user_request": user_request, "max_iterations": 3},
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            state = data.get("state", {})
            workflow_id = data.get("workflow_id", "unknown")

            logger.info(
                "Workflow %s completed: status=%s",
                workflow_id,
                state.get("status"),
            )

            # Return the fields we want to evaluate
            return {
                "status": state.get("status", ""),
                "generated_code": state.get("generated_code", ""),
                "test_cases": state.get("test_cases", ""),
                "security_findings": state.get("security_findings", []),
                "review_comments": state.get("review_comments", []),
                "requirements": state.get("requirements", {}),
                "architecture": state.get("architecture", {}),
                "iteration_count": state.get("iteration_count", 0),
                "workflow_id": workflow_id,
            }
        except requests.RequestException as exc:
            logger.error("Workflow request failed: %s", exc)
            return {"status": "error", "error": str(exc)}

    return run_workflow


# ---------------------------------------------------------------------------
# Dataset management
# ---------------------------------------------------------------------------


def ensure_dataset(client: Client) -> str:
    """Create the golden dataset in LangSmith if it doesn't exist."""
    # Check if dataset already exists
    try:
        datasets = list(client.list_datasets(dataset_name=GOLDEN_DATASET_NAME))
        if datasets:
            dataset = datasets[0]
            logger.info("Found existing dataset: %s (id=%s)", dataset.name, dataset.id)
            return dataset.name
    except Exception:
        pass

    # Create new dataset
    logger.info("Creating golden dataset: %s", GOLDEN_DATASET_NAME)
    dataset = client.create_dataset(
        dataset_name=GOLDEN_DATASET_NAME,
        description="Golden test prompts for AI SDLC workflow evaluation",
    )

    for example in GOLDEN_EXAMPLES:
        client.create_example(
            dataset_id=dataset.id,
            inputs={"input": example["input"]},
            outputs={"expected": example["expected"]},
        )
        logger.info("  Added: %s", example["input"][:50])

    logger.info("Created dataset with %d examples", len(GOLDEN_EXAMPLES))
    return dataset.name


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Run LangSmith evaluation for AI SDLC")
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the AI SDLC backend API (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--experiment",
        default=None,
        help="Experiment name prefix (default: auto-generated with timestamp)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds per workflow (default: 300)",
    )
    args = parser.parse_args()

    experiment_prefix = args.experiment or f"ai-sdlc-eval-{int(time.time())}"

    # Verify API is reachable
    logger.info("Checking API at %s ...", args.api_url)
    try:
        health = requests.get(f"{args.api_url}/health", timeout=10)
        health.raise_for_status()
        logger.info("API is healthy: %s", health.json())
    except requests.RequestException as exc:
        logger.error("Cannot reach API at %s: %s", args.api_url, exc)
        logger.error("Start the backend first: uvicorn ai_sdlc.api:app --app-dir backend/src")
        sys.exit(1)

    # Initialize LangSmith client
    client = Client()
    logger.info("Connected to LangSmith: %s", client.api_url)

    # Ensure the golden dataset exists
    dataset_name = ensure_dataset(client)

    # Create the workflow runner
    runner = create_workflow_runner(args.api_url, timeout=args.timeout)

    # Run evaluation
    logger.info("=" * 60)
    logger.info("Starting evaluation: %s", experiment_prefix)
    logger.info("Dataset: %s (%d examples)", dataset_name, len(GOLDEN_EXAMPLES))
    logger.info("API: %s", args.api_url)
    logger.info("=" * 60)

    results = evaluate(
        runner,
        data=dataset_name,
        evaluators=[
            workflow_completed,
            code_generated,
            tests_generated,
            security_clean,
            no_llm_fallback,
        ],
        experiment_prefix=experiment_prefix,
    )

    # Print summary
    logger.info("=" * 60)
    logger.info("Evaluation complete!")
    logger.info("View results at: https://smith.langchain.com")
    logger.info("Project: %s", experiment_prefix)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
