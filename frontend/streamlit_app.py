from __future__ import annotations

import json
import os
from typing import Any, Iterator

import requests
import streamlit as st


DEFAULT_API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
NODE_LABELS = {
    "product_owner": "Product Owner",
    "architect": "Architect",
    "scrum_master": "Scrum Master",
    "developer": "Developer",
    "qa": "QA Engineer",
    "security": "Security Agent",
    "reviewer": "Reviewer",
    "aggregate": "Aggregation",
    "human_review": "Human Approval",
    "devops": "DevOps",
}


def parse_sse(response: requests.Response) -> Iterator[dict[str, Any]]:
    event = "message"
    data_lines: list[str] = []
    for line in response.iter_lines(decode_unicode=True):
        if line is None:
            continue
        if not line:
            if data_lines:
                yield {"event": event, "data": json.loads("\n".join(data_lines))}
            event = "message"
            data_lines = []
            continue
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())


def stream_post(url: str, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    with requests.post(url, json=payload, stream=True, timeout=300) as response:
        response.raise_for_status()
        yield from parse_sse(response)


def get_state(api_base_url: str, workflow_id: str) -> dict[str, Any] | None:
    if not workflow_id:
        return None
    response = requests.get(f"{api_base_url}/workflows/{workflow_id}", timeout=30)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()["state"]


def render_agent_outputs(state: dict[str, Any]) -> None:
    if not state:
        st.info("Run a workflow to see agent outputs.")
        return

    tabs = st.tabs(["Plan", "Build", "Review", "Deploy", "Raw State"])
    with tabs[0]:
        st.subheader("Requirements")
        st.json(state.get("requirements", {}), expanded=True)
        st.subheader("Architecture")
        st.json(state.get("architecture", {}), expanded=True)
        st.subheader("Tasks")
        st.json(state.get("tasks", []), expanded=True)

    with tabs[1]:
        st.subheader("Generated Code")
        st.code(state.get("generated_code", ""), language="python")
        st.subheader("Test Cases")
        st.code(state.get("test_cases", ""), language="python")

    with tabs[2]:
        st.subheader("Security Findings")
        for finding in state.get("security_findings", []):
            st.write(f"- {finding}")
        st.subheader("Review Comments")
        for comment in state.get("review_comments", []):
            st.write(f"- {comment}")

    with tabs[3]:
        st.subheader("Deployment Plan")
        st.json(state.get("deployment_plan", {}), expanded=True)

    with tabs[4]:
        st.json(state, expanded=False)


def render_event(event: dict[str, Any]) -> str:
    event_name = event["event"]
    data = event["data"]
    if event_name == "agent_update":
        node = data.get("node", "unknown")
        label = NODE_LABELS.get(node, node)
        status = data.get("status", "unknown")
        return f"{label} completed. Status: {status}"
    if event_name == "workflow_completed":
        return f"Workflow completed. Status: {data.get('status')}"
    if event_name == "workflow_error":
        return f"Workflow failed: {data.get('error')}"
    return f"Workflow started. ID: {data.get('workflow_id')}"


def main() -> None:
    st.set_page_config(page_title="AI Software Delivery Team", layout="wide")
    st.title("AI Software Delivery Team")

    with st.sidebar:
        api_base_url = st.text_input("FastAPI base URL", value=DEFAULT_API_BASE_URL).rstrip("/")
        st.caption("Run FastAPI separately on port 8000 for local development.")
        if st.button("Refresh current workflow", use_container_width=True):
            state = get_state(api_base_url, st.session_state.get("workflow_id", ""))
            if state:
                st.session_state["workflow_state"] = state

    if "workflow_id" not in st.session_state:
        st.session_state["workflow_id"] = ""
    if "workflow_state" not in st.session_state:
        st.session_state["workflow_state"] = {}
    if "events" not in st.session_state:
        st.session_state["events"] = []

    left, right = st.columns([0.42, 0.58], gap="large")

    with left:
        st.subheader("Feature Request")
        feature_request = st.text_area(
            "Request",
            value="Build login API with JWT authentication",
            height=140,
            label_visibility="collapsed",
        )
        max_iterations = st.number_input("Max iterations", min_value=1, max_value=10, value=3, step=1)

        if st.button("Run Workflow", type="primary", use_container_width=True):
            st.session_state["events"] = []
            st.session_state["workflow_state"] = {}
            payload = {"user_request": feature_request, "max_iterations": int(max_iterations)}
            progress = st.empty()
            try:
                for event in stream_post(f"{api_base_url}/workflows/stream", payload):
                    st.session_state["events"].append(render_event(event))
                    progress.info(st.session_state["events"][-1])
                    data = event["data"]
                    if data.get("workflow_id"):
                        st.session_state["workflow_id"] = data["workflow_id"]
                    if event["event"] == "workflow_completed":
                        st.session_state["workflow_state"] = data["state"]
            except requests.RequestException as exc:
                st.error(f"Workflow request failed: {exc}")

        st.subheader("Human Approval")
        workflow_id = st.text_input("Workflow ID", value=st.session_state["workflow_id"])
        st.session_state["workflow_id"] = workflow_id
        feedback = st.text_area("Feedback", value="Approved for deployment planning.", height=100)

        approve_col, reject_col = st.columns(2)
        with approve_col:
            approve_clicked = st.button("Approve", use_container_width=True)
        with reject_col:
            reject_clicked = st.button("Reject", use_container_width=True)

        if approve_clicked or reject_clicked:
            if not workflow_id:
                st.warning("Run or load a workflow first.")
            else:
                payload = {"approved": approve_clicked, "comment": feedback}
                progress = st.empty()
                try:
                    for event in stream_post(f"{api_base_url}/workflows/{workflow_id}/approval/stream", payload):
                        st.session_state["events"].append(render_event(event))
                        progress.info(st.session_state["events"][-1])
                        if event["event"] == "workflow_completed":
                            st.session_state["workflow_state"] = event["data"]["state"]
                except requests.RequestException as exc:
                    st.error(f"Approval request failed: {exc}")

        st.subheader("Live Events")
        for item in st.session_state["events"][-14:]:
            st.write(item)

    with right:
        status = st.session_state["workflow_state"].get("status", "not_started")
        st.metric("Workflow Status", status)
        render_agent_outputs(st.session_state["workflow_state"])


if __name__ == "__main__":
    main()
