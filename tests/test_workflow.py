import os

os.environ["AI_SDLC_USE_LLM"] = "false"

from ai_sdlc.graph import workflow_graph


def _initial_state():
    return {
        "workflow_id": "test-workflow",
        "user_id": "test-user",
        "session_id": "test-session",
        "user_request": "Build login API with JWT authentication",
        "approved": None,
        "human_feedback": "",
        "iteration_count": 0,
        "max_iterations": 3,
        "status": "created",
        "execution_log": [],
    }


def test_workflow_waits_for_human_approval():
    state = workflow_graph.invoke(_initial_state())

    assert state["status"] == "awaiting_approval"
    assert state["requirements"]["priority"] == "HIGH"
    assert state["test_cases"]
    assert state["security_findings"]
    assert state["review_comments"]


def test_approved_workflow_reaches_deployment_plan():
    state = workflow_graph.invoke(_initial_state())
    state["approved"] = True
    approved_state = workflow_graph.invoke(state)

    assert approved_state["status"] == "ready_for_deployment"
    assert approved_state["deployment_plan"]["runtime"] == "Deploy FastAPI on Cloud Run."


def test_rejected_workflow_loops_to_developer():
    state = workflow_graph.invoke(_initial_state())
    state["approved"] = False
    state["human_feedback"] = "Use typed schemas."
    reworked_state = workflow_graph.invoke(state)

    assert reworked_state["status"] == "awaiting_approval"
    assert reworked_state["iteration_count"] == 2
    assert "Use typed schemas." in reworked_state["generated_code"]
