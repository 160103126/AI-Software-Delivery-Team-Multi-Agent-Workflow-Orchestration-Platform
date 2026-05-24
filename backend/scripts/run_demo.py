from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_sdlc.graph import workflow_graph  # noqa: E402
from ai_sdlc.logging_config import configure_logging  # noqa: E402


def main() -> None:
    configure_logging()
    workflow_id = str(uuid4())
    state = workflow_graph.invoke(
        {
            "workflow_id": workflow_id,
            "user_id": "demo-user",
            "session_id": "demo-session",
            "user_request": "Build login API with JWT authentication",
            "approved": None,
            "human_feedback": "",
            "iteration_count": 0,
            "max_iterations": 3,
            "status": "created",
            "execution_log": [],
        }
    )
    print(f"Workflow: {workflow_id}")
    print(f"Status after first pass: {state['status']}")
    print(f"Agents completed: {len(state['execution_log'])}")

    state["approved"] = True
    state["human_feedback"] = "Approved for demo deployment plan."
    approved_state = workflow_graph.invoke(state)
    print(f"Status after approval: {approved_state['status']}")
    print(f"Deployment runtime: {approved_state['deployment_plan']['runtime']}")


if __name__ == "__main__":
    main()
