from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
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
    archiver_node,
)
from .state import WorkflowState

load_dotenv()
load_dotenv(".ENV")

logger = logging.getLogger(__name__)


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


def _create_checkpointer():
    """Create a LangGraph checkpointer.

    Uses RedisSaver when REDIS_URL is set (requires Redis 8.0+ or Redis Stack
    with RedisJSON and RediSearch modules).  Falls back to an in-memory
    MemorySaver when Redis is unavailable, which is fine for local development
    but state will be lost on server restart.
    """
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            from langgraph.checkpoint.redis import RedisSaver

            checkpointer = RedisSaver.from_conn_string(redis_url)
            checkpointer.setup()
            logger.info("LangGraph checkpointer: RedisSaver (url=%s)", redis_url.split("@")[-1])
            return checkpointer
        except Exception as exc:
            logger.warning("Failed to create RedisSaver, falling back to MemorySaver: %s", exc)

    from langgraph.checkpoint.memory import MemorySaver

    logger.info("LangGraph checkpointer: MemorySaver (in-memory, state lost on restart)")
    return MemorySaver()


def route_after_aggregate(state: WorkflowState) -> str:
    """Route after aggregate: auto-rework or proceed to human review."""
    if state.get("status") == "auto_rework":
        return "developer"
    return "human_review"


def build_graph(checkpointer=None):
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
    graph.add_node("archiver", archiver_node)

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

    # After aggregate: auto-rework (back to developer) or human review
    graph.add_conditional_edges(
        "aggregate",
        route_after_aggregate,
        {
            "developer": "developer",
            "human_review": "human_review",
        },
    )

    graph.add_conditional_edges(
        "human_review",
        route_after_human_review,
        {
            "approved": "devops",
            "rejected": "developer",
            "waiting": END,
        },
    )
    graph.add_edge("devops", "archiver")
    graph.add_edge("archiver", END)

    return graph.compile(checkpointer=checkpointer)


workflow_graph = build_graph(checkpointer=_create_checkpointer())
