from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .agents import (
    aggregate_agent,
    architect_agent,
    developer_agent,
    devops_agent,
    human_review_node,
    product_owner_agent,
    qa_agent,
    reviewer_agent,
    scrum_master_agent,
    security_agent,
)
from .state import WorkflowState


def entry_node(state: WorkflowState) -> dict:
    return {}


def route_from_entry(state: WorkflowState) -> str:
    if state.get("status") == "awaiting_approval":
        return "human_review"
    return "product_owner"


def route_after_human_review(state: WorkflowState) -> str:
    if state.get("approved") is True:
        return "approved"
    if state.get("approved") is False and state.get("iteration_count", 0) < state.get("max_iterations", 3):
        return "rejected"
    return "waiting"


def build_graph():
    graph = StateGraph(WorkflowState)

    graph.add_node("entry", entry_node)
    graph.add_node("product_owner", product_owner_agent)
    graph.add_node("architect", architect_agent)
    graph.add_node("scrum_master", scrum_master_agent)
    graph.add_node("developer", developer_agent)
    graph.add_node("qa", qa_agent)
    graph.add_node("security", security_agent)
    graph.add_node("reviewer", reviewer_agent)
    graph.add_node("aggregate", aggregate_agent)
    graph.add_node("human_review", human_review_node)
    graph.add_node("devops", devops_agent)

    graph.add_edge(START, "entry")
    graph.add_conditional_edges(
        "entry",
        route_from_entry,
        {
            "product_owner": "product_owner",
            "human_review": "human_review",
        },
    )
    graph.add_edge("product_owner", "architect")
    graph.add_edge("architect", "scrum_master")
    graph.add_edge("scrum_master", "developer")

    graph.add_edge("developer", "qa")
    graph.add_edge("developer", "security")
    graph.add_edge("developer", "reviewer")

    graph.add_edge("qa", "aggregate")
    graph.add_edge("security", "aggregate")
    graph.add_edge("reviewer", "aggregate")
    graph.add_edge("aggregate", "human_review")

    graph.add_conditional_edges(
        "human_review",
        route_after_human_review,
        {
            "approved": "devops",
            "rejected": "developer",
            "waiting": END,
        },
    )
    graph.add_edge("devops", END)

    return graph.compile()


workflow_graph = build_graph()
