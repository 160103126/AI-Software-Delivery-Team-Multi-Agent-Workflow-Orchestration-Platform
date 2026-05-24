from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

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


# Hard cap on total node steps per invoke/stream call.
# With the inner feedback loop the worst case per invocation is roughly:
#   entry(1) + PO(1) + Arch(1) + SM(1) + [Dev(1) + QA/Sec/Rev(3) + Agg(1)] × (1 + max_auto_reworks)
#   + HumanReview(1) + DevOps(1) ≈ 20 for max_auto_reworks=1.
# 50 leaves generous headroom while preventing runaway loops.
DEFAULT_RECURSION_LIMIT = 50


def _thread_config(workflow_id: str) -> dict:
    """Build the LangGraph config dict for a given workflow (thread)."""
    return {
        "configurable": {"thread_id": workflow_id},
        "recursion_limit": DEFAULT_RECURSION_LIMIT,
    }


def _get_checkpoint_state(workflow_id: str) -> dict | None:
    """Retrieve the latest state from the LangGraph checkpointer."""
    snapshot = workflow_graph.get_state(_thread_config(workflow_id))
    if snapshot and snapshot.values:
        return dict(snapshot.values)
    return None


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


def _stream_workflow(initial_state: WorkflowState | None, config: dict) -> Iterator[str]:
    """Stream graph execution via SSE.

    If initial_state is None, the graph resumes from its last checkpoint
    (used after approval/rejection).  Otherwise it starts a fresh run.
    """
    workflow_id = config["configurable"]["thread_id"]
    # For tracking SSE deltas locally
    import queue
    import threading
    
    state: WorkflowState = deepcopy(initial_state) if initial_state else {}
    yield _sse("workflow_started", {"workflow_id": workflow_id, "status": state.get("status", "resuming")})

    q = queue.Queue()

    def _run_graph():
        try:
            for chunk in workflow_graph.stream(initial_state, config):
                q.put(("chunk", chunk))
            q.put(("done", None))
        except Exception as e:
            logger.exception("Graph execution error")
            q.put(("error", str(e)))

    t = threading.Thread(target=_run_graph)
    t.start()

    try:
        while True:
            try:
                # Wait for 15 seconds. If nothing, send a keep-alive.
                msg_type, data = q.get(timeout=15.0)
                
                if msg_type == "done":
                    # Save final state to the workflow store (query layer)
                    final_state = _get_checkpoint_state(workflow_id) or state
                    workflow_store.save(workflow_id, final_state)
                    logger.info("Streaming workflow completed: workflow_id=%s status=%s", workflow_id, final_state.get("status"))
                    yield _sse("workflow_completed", {"workflow_id": workflow_id, "status": final_state.get("status"), "state": final_state})
                    break
                    
                elif msg_type == "error":
                    yield _sse("workflow_error", {"workflow_id": workflow_id, "error": data})
                    break
                    
                elif msg_type == "chunk":
                    for node_name, delta in data.items():
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
            except queue.Empty:
                # Send a keep-alive ping to prevent browser timeout and update UI
                yield _sse("ping", {"message": "Agent is thinking..."})
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
    
    workspace_dir = str(Path(tempfile.gettempdir()) / "ai_sdlc" / workflow_id)
    os.makedirs(workspace_dir, exist_ok=True)

    initial_state: WorkflowState = {
        "workflow_id": workflow_id,
        "user_id": payload.user_id,
        "session_id": payload.session_id,
        "user_request": payload.user_request,
        "approved": None,
        "human_feedback": "",
        "iteration_count": 0,
        "max_iterations": payload.max_iterations,
        "auto_rework_count": 0,
        "max_auto_reworks": 1,
        "status": "created",
        "workspace_dir": workspace_dir,
        "project_archive_base64": None,
        "execution_log": [],
    }
    config = _thread_config(workflow_id)
    state = workflow_graph.invoke(initial_state, config)
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
    
    workspace_dir = str(Path(tempfile.gettempdir()) / "ai_sdlc" / workflow_id)
    os.makedirs(workspace_dir, exist_ok=True)

    initial_state: WorkflowState = {
        "workflow_id": workflow_id,
        "user_id": payload.user_id,
        "session_id": payload.session_id,
        "user_request": payload.user_request,
        "approved": None,
        "human_feedback": "",
        "iteration_count": 0,
        "max_iterations": payload.max_iterations,
        "auto_rework_count": 0,
        "max_auto_reworks": 1,
        "status": "created",
        "workspace_dir": workspace_dir,
        "execution_log": [],
    }
    config = _thread_config(workflow_id)
    return StreamingResponse(_stream_workflow(initial_state, config), media_type="text/event-stream")


@app.get("/workflows", response_model=dict[str, WorkflowState])
async def list_workflows() -> dict[str, WorkflowState]:
    workflows = workflow_store.list()
    logger.info("List workflows requested: count=%s", len(workflows))
    return workflows


@app.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str) -> WorkflowResponse:
    # Try checkpoint first, then fall back to store
    state = _get_checkpoint_state(workflow_id) or workflow_store.get(workflow_id)
    if state is None:
        logger.warning("Workflow not found: workflow_id=%s", workflow_id)
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Remove the large base64 string from the standard status response
    state_copy = deepcopy(state)
    state_copy.pop("project_archive_base64", None)
    
    logger.info("Workflow fetched: workflow_id=%s status=%s", workflow_id, state.get("status"))
    return WorkflowResponse(workflow_id=workflow_id, status=state.get("status", "unknown"), state=state_copy)


@app.get("/workflows/{workflow_id}/download")
async def download_workflow_archive(workflow_id: str):
    """Download the final zipped codebase."""
    state = _get_checkpoint_state(workflow_id) or workflow_store.get(workflow_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
        
    b64_data = state.get("project_archive_base64")
    if not b64_data:
        raise HTTPException(status_code=404, detail="Archive not found. Workflow may not be completed.")
        
    zip_bytes = base64.b64decode(b64_data)
    
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{workflow_id}.zip"'
        }
    )


@app.post("/workflows/{workflow_id}/approval", response_model=WorkflowResponse)
async def approve_workflow(workflow_id: str, payload: ApprovalRequest) -> WorkflowResponse:
    config = _thread_config(workflow_id)

    # Verify workflow exists in checkpoint or store
    existing = _get_checkpoint_state(workflow_id) or workflow_store.get(workflow_id)
    if existing is None:
        logger.warning("Approval submitted for missing workflow: workflow_id=%s", workflow_id)
        raise HTTPException(status_code=404, detail="Workflow not found")

    logger.info(
        "Approval submitted: workflow_id=%s approved=%s comment_length=%s",
        workflow_id,
        payload.approved,
        len(payload.comment),
    )
    # Update the checkpoint state and resume from where the graph paused
    workflow_graph.update_state(config, {
        "approved": payload.approved,
        "human_feedback": payload.comment,
        "status": "awaiting_approval",
    })
    resumed_state = workflow_graph.invoke(None, config)
    workflow_store.save(workflow_id, resumed_state)
    logger.info("Workflow resumed after approval: workflow_id=%s status=%s", workflow_id, resumed_state["status"])
    return WorkflowResponse(workflow_id=workflow_id, status=resumed_state["status"], state=resumed_state)


@app.post("/workflows/{workflow_id}/approval/stream")
async def approve_workflow_stream(workflow_id: str, payload: ApprovalRequest) -> StreamingResponse:
    config = _thread_config(workflow_id)

    # Verify workflow exists in checkpoint or store
    existing = _get_checkpoint_state(workflow_id) or workflow_store.get(workflow_id)
    if existing is None:
        logger.warning("Streaming approval submitted for missing workflow: workflow_id=%s", workflow_id)
        raise HTTPException(status_code=404, detail="Workflow not found")

    logger.info(
        "Streaming approval submitted: workflow_id=%s approved=%s comment_length=%s",
        workflow_id,
        payload.approved,
        len(payload.comment),
    )
    # Update the checkpoint state; stream resumes from the last checkpoint
    workflow_graph.update_state(config, {
        "approved": payload.approved,
        "human_feedback": payload.comment,
        "status": "awaiting_approval",
    })
    return StreamingResponse(_stream_workflow(None, config), media_type="text/event-stream")


# Serve frontend static files
frontend_path = Path(__file__).parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
