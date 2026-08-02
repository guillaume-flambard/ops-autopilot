"""Edge routing for the analysis graph."""

from __future__ import annotations

from langgraph.graph import END


def route_review(state: dict) -> str:
    """From human_review: approve -> report, edit -> re-score, reject -> stop."""
    action = state.get("action", "approve")
    if action == "reject":
        return "reject"
    if action == "edit":
        return "edit"
    return "approve"


REVIEW_ROUTES = {"approve": "generate_report", "edit": "score", "reject": END}
