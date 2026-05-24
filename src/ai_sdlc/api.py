from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, HTTPException

from .graph import workflow_graph
from .models import ApprovalRequest, WorkflowCreate, WorkflowResponse
from .state import WorkflowState
from .store import workflow_store

app = FastAPI(
    title="AI Software Delivery Team",
    version="0.1.0",
    description="LangGraph-orchestrated multi-agent SDLC workflow with human approval.",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/workflows", response_model=WorkflowResponse)
async def create_workflow(payload: WorkflowCreate) -> WorkflowResponse:
    workflow_id = str(uuid4())
    initial_state: WorkflowState = {
        "workflow_id": workflow_id,
        "user_id": payload.user_id,
        "session_id": payload.session_id,
        "user_request": payload.user_request,
        "approved": None,
        "human_feedback": "",
        "iteration_count": 0,
        "max_iterations": payload.max_iterations,
        "status": "created",
        "execution_log": [],
    }
    state = workflow_graph.invoke(initial_state)
    workflow_store.save(workflow_id, state)
    return WorkflowResponse(workflow_id=workflow_id, status=state["status"], state=state)


@app.get("/workflows", response_model=dict[str, WorkflowState])
async def list_workflows() -> dict[str, WorkflowState]:
    return workflow_store.list()


@app.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str) -> WorkflowResponse:
    state = workflow_store.get(workflow_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowResponse(workflow_id=workflow_id, status=state["status"], state=state)


@app.post("/workflows/{workflow_id}/approval", response_model=WorkflowResponse)
async def approve_workflow(workflow_id: str, payload: ApprovalRequest) -> WorkflowResponse:
    state = workflow_store.get(workflow_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    state["approved"] = payload.approved
    state["human_feedback"] = payload.comment
    resumed_state = workflow_graph.invoke(state)
    workflow_store.save(workflow_id, resumed_state)
    return WorkflowResponse(workflow_id=workflow_id, status=resumed_state["status"], state=resumed_state)
