import os

os.environ["AI_SDLC_USE_LLM"] = "false"

from fastapi.testclient import TestClient

from ai_sdlc.api import app


def test_workflow_stream_returns_agent_events():
    client = TestClient(app)

    with client.stream(
        "POST",
        "/workflows/stream",
        json={"user_request": "Build login API with JWT authentication"},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "event: workflow_started" in body
    assert "event: agent_update" in body
    assert "event: workflow_completed" in body
    assert '"node": "product_owner"' in body
    assert '"status": "awaiting_approval"' in body
