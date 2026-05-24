import os

os.environ["AI_SDLC_USE_LLM"] = "false"

from ai_sdlc.graph import workflow_graph


def _config(thread_id="test-thread"):
    """Build LangGraph config with a unique thread_id for checkpointing."""
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}


def _initial_state():
    import tempfile
    from pathlib import Path
    workspace_dir = str(Path(tempfile.gettempdir()) / "ai_sdlc" / "test-workflow")
    os.makedirs(workspace_dir, exist_ok=True)
    return {
        "workflow_id": "test-workflow",
        "user_id": "test-user",
        "session_id": "test-session",
        "user_request": "Build login API with JWT authentication",
        "approved": None,
        "human_feedback": "",
        "iteration_count": 0,
        "max_iterations": 3,
        "auto_rework_count": 0,
        "max_auto_reworks": 1,
        "status": "created",
        "workspace_dir": workspace_dir,
        "project_archive_base64": None,
        "execution_log": [],
    }


def test_workflow_waits_for_human_approval():
    state = workflow_graph.invoke(_initial_state(), _config("test-approval-wait"))

    assert state["status"] == "awaiting_approval"
    assert state["requirements"]["priority"] == "HIGH"
    assert state["test_cases"]
    assert state["security_findings"]
    assert state["review_comments"]


def test_approved_workflow_reaches_deployment_plan():
    state = workflow_graph.invoke(_initial_state(), _config("test-approved"))
    workflow_graph.update_state(_config("test-approved"), {
        "approved": True,
        "status": "awaiting_approval",
    })
    approved_state = workflow_graph.invoke(None, _config("test-approved"))

    assert approved_state["status"] == "ready_for_deployment"
    assert approved_state["deployment_plan"]["runtime"] == "Manual deployment review required."


def test_repeated_approval_stays_deployment_ready():
    state = workflow_graph.invoke(_initial_state(), _config("test-repeated"))
    workflow_graph.update_state(_config("test-repeated"), {
        "approved": True,
        "status": "awaiting_approval",
    })
    approved_state = workflow_graph.invoke(None, _config("test-repeated"))

    assert approved_state["status"] == "ready_for_deployment"
    assert approved_state["iteration_count"] == 1

    # With checkpointing, the graph has reached END — verify the checkpoint
    # still holds the final state.
    snapshot = workflow_graph.get_state(_config("test-repeated"))
    assert snapshot.values["status"] == "ready_for_deployment"


def test_rejected_workflow_loops_to_developer():
    state = workflow_graph.invoke(_initial_state(), _config("test-rejected"))
    workflow_graph.update_state(_config("test-rejected"), {
        "approved": False,
        "human_feedback": "Use typed schemas.",
        "status": "awaiting_approval",
    })
    reworked_state = workflow_graph.invoke(None, _config("test-rejected"))

    assert reworked_state["status"] == "awaiting_approval"
    assert reworked_state["iteration_count"] == 2
    assert "Use typed schemas." in reworked_state["generated_code"]


def test_auto_rework_skipped_when_no_actionable_findings():
    """With LLM disabled, fallback outputs contain 'LLM' marker and are NOT
    treated as actionable findings — so no auto-rework should trigger."""
    state = workflow_graph.invoke(_initial_state(), _config("test-no-autorework"))
    # Should go straight to awaiting_approval without auto-rework
    assert state["status"] == "awaiting_approval"
    assert state.get("auto_rework_count", 0) == 0
