from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from copy import deepcopy
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .graph import workflow_graph
from .logging_config import configure_logging
from .models import ApprovalRequest, WorkflowCreate, WorkflowResponse
from .state import WorkflowState
from .store import workflow_store

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Software Delivery Team",
    version="0.1.0",
    description="LangGraph-orchestrated multi-agent SDLC workflow with human approval.",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (can be restricted to frontend URL in production)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _merge_delta(state: WorkflowState, delta: dict | None) -> None:
    if not delta:
        return
    for key, value in delta.items():
        if key == "execution_log":
            state.setdefault("execution_log", [])
            state["execution_log"].extend(value)
        else:
            state[key] = value


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _stream_workflow(initial_state: WorkflowState) -> Iterator[str]:
    workflow_id = initial_state["workflow_id"]
    state: WorkflowState = deepcopy(initial_state)
    yield _sse("workflow_started", {"workflow_id": workflow_id, "status": state.get("status")})

    try:
        for chunk in workflow_graph.stream(initial_state):
            for node_name, delta in chunk.items():
                _merge_delta(state, delta)
                if node_name == "entry":
                    continue
                yield _sse(
                    "agent_update",
                    {
                        "workflow_id": workflow_id,
                        "node": node_name,
                        "status": state.get("status"),
                        "delta": delta or {},
                    },
                )
        workflow_store.save(workflow_id, state)
        logger.info("Streaming workflow completed: workflow_id=%s status=%s", workflow_id, state.get("status"))
        yield _sse("workflow_completed", {"workflow_id": workflow_id, "status": state.get("status"), "state": state})
    except Exception as exc:
        logger.exception("Streaming workflow failed: workflow_id=%s", workflow_id)
        yield _sse("workflow_error", {"workflow_id": workflow_id, "error": str(exc)})


@app.get("/health")
async def health() -> dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "ok"}


@app.post("/workflows", response_model=WorkflowResponse)
async def create_workflow(payload: WorkflowCreate) -> WorkflowResponse:
    workflow_id = str(uuid4())
    logger.info(
        "Create workflow requested: workflow_id=%s user_id=%s session_id=%s max_iterations=%s",
        workflow_id,
        payload.user_id,
        payload.session_id,
        payload.max_iterations,
    )
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
    logger.info("Workflow created: workflow_id=%s status=%s", workflow_id, state["status"])
    return WorkflowResponse(workflow_id=workflow_id, status=state["status"], state=state)


@app.post("/workflows/stream")
async def create_workflow_stream(payload: WorkflowCreate) -> StreamingResponse:
    workflow_id = str(uuid4())
    logger.info(
        "Streaming workflow requested: workflow_id=%s user_id=%s session_id=%s",
        workflow_id,
        payload.user_id,
        payload.session_id,
    )
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
    return StreamingResponse(_stream_workflow(initial_state), media_type="text/event-stream")


@app.get("/workflows", response_model=dict[str, WorkflowState])
async def list_workflows() -> dict[str, WorkflowState]:
    workflows = workflow_store.list()
    logger.info("List workflows requested: count=%s", len(workflows))
    return workflows


@app.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str) -> WorkflowResponse:
    state = workflow_store.get(workflow_id)
    if state is None:
        logger.warning("Workflow not found: workflow_id=%s", workflow_id)
        raise HTTPException(status_code=404, detail="Workflow not found")
    logger.info("Workflow fetched: workflow_id=%s status=%s", workflow_id, state["status"])
    return WorkflowResponse(workflow_id=workflow_id, status=state["status"], state=state)


@app.post("/workflows/{workflow_id}/approval", response_model=WorkflowResponse)
async def approve_workflow(workflow_id: str, payload: ApprovalRequest) -> WorkflowResponse:
    state = workflow_store.get(workflow_id)
    if state is None:
        logger.warning("Approval submitted for missing workflow: workflow_id=%s", workflow_id)
        raise HTTPException(status_code=404, detail="Workflow not found")

    logger.info(
        "Approval submitted: workflow_id=%s approved=%s comment_length=%s",
        workflow_id,
        payload.approved,
        len(payload.comment),
    )
    state["approved"] = payload.approved
    state["human_feedback"] = payload.comment
    state["status"] = "awaiting_approval"
    resumed_state = workflow_graph.invoke(state)
    workflow_store.save(workflow_id, resumed_state)
    logger.info("Workflow resumed after approval: workflow_id=%s status=%s", workflow_id, resumed_state["status"])
    return WorkflowResponse(workflow_id=workflow_id, status=resumed_state["status"], state=resumed_state)


@app.post("/workflows/{workflow_id}/approval/stream")
async def approve_workflow_stream(workflow_id: str, payload: ApprovalRequest) -> StreamingResponse:
    state = workflow_store.get(workflow_id)
    if state is None:
        logger.warning("Streaming approval submitted for missing workflow: workflow_id=%s", workflow_id)
        raise HTTPException(status_code=404, detail="Workflow not found")

    logger.info(
        "Streaming approval submitted: workflow_id=%s approved=%s comment_length=%s",
        workflow_id,
        payload.approved,
        len(payload.comment),
    )
    state["approved"] = payload.approved
    state["human_feedback"] = payload.comment
    state["status"] = "awaiting_approval"
    return StreamingResponse(_stream_workflow(state), media_type="text/event-stream")
