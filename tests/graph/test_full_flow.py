"""Integration tests for the full graph flow with a mocked LLM."""

import json
from pathlib import Path

import pytest
from langgraph.types import Command

from domain.models import Analysis, Assumptions, BrandProfile
from graph.build import build_graph
from graph.checkpointer import sqlite_checkpointer
from graph.nodes import AssumptionError
from llm.client import MockClient

REPO_ROOT = Path(__file__).resolve().parents[2]


class RecordingMockLLM(MockClient):
    """MockClient that records which calls the graph made."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def map_tasks_from_text(self, free_text, locale="fr"):
        self.calls.append("map_tasks")
        return super().map_tasks_from_text(free_text, locale)

    def deep_dive(self, scored_tasks, assumptions):
        self.calls.append("deep_dive")
        return super().deep_dive(scored_tasks, assumptions)

    def executive_report(self, scored_tasks, deep_dives, assumptions, sector=None):
        self.calls.append("report")
        return super().executive_report(scored_tasks, deep_dives, assumptions, sector=sector)


def load_lumea() -> dict:
    with open(REPO_ROOT / "profiles" / "lumea.json") as f:
        brand = BrandProfile(**json.load(f))
    return {"brand": brand, "assumptions": brand.default_assumptions}


def resume(app, thread, action: str) -> dict:
    return app.invoke(Command(resume=action), config=thread)


def test_full_flow_approve_produces_report():
    llm = RecordingMockLLM()
    app = build_graph(llm=llm)
    thread = {"configurable": {"thread_id": "t1"}}

    result = app.invoke(load_lumea(), config=thread)
    assert "__interrupt__" in result  # halts at human review
    payload = result["__interrupt__"][0].value
    assert payload["scored_tasks"][0]["rank"] == 1
    assert payload["deep_dives"]  # review data is available without replay

    result = resume(app, thread, "approve")
    assert result["action"] == "approve"
    assert len(result["scored_tasks"]) == 4
    assert len(result["deep_dives"]) == 3  # top-3 only
    assert all(d.degraded for d in result["deep_dives"])  # no crew LLM configured
    assert result["report"]
    assert llm.calls == ["report"]


def test_full_flow_reject_skips_report():
    llm = RecordingMockLLM()
    app = build_graph(llm=llm)
    thread = {"configurable": {"thread_id": "t2"}}

    app.invoke(load_lumea(), config=thread)
    result = resume(app, thread, "reject")

    assert result["action"] == "reject"
    assert result.get("report") is None
    assert llm.calls == []


def test_edit_loops_back_to_score_then_approves():
    llm = RecordingMockLLM()
    app = build_graph(llm=llm)
    thread = {"configurable": {"thread_id": "t3"}}

    app.invoke(load_lumea(), config=thread)
    app.invoke(Command(resume="edit"), config=thread)  # re-score, deep-dive, review again
    result = resume(app, thread, "approve")

    score_events = [e for e in result["events"] if e.startswith("score:")]
    assert len(score_events) == 2
    assert result["action"] == "approve"
    assert result["report"]


def test_free_text_path_uses_map_tasks():
    llm = RecordingMockLLM()
    brand = BrandProfile(
        name="Free",
        sector="SaaS",
        team_size=5,
        free_text="Churn emails: 50/week, 5 min each, highly repetitive. "
        "Doc updates: weekly, 2 hours, low repetitive.",
    )
    app = build_graph(llm=llm)
    thread = {"configurable": {"thread_id": "t4"}}

    app.invoke({"brand": brand, "assumptions": Assumptions(hourly_rate_eur=40)}, config=thread)
    result = resume(app, thread, "approve")

    assert llm.calls == ["map_tasks", "report"]
    assert len(result["scored_tasks"]) == 2
    assert result["scored_tasks"][0].task.name == "Churn emails"


def test_missing_hourly_rate_raises_assumption_error():
    """No assumptions and no preset defaults means scoring cannot proceed."""
    brand = BrandProfile(name="NoRate", sector="D2C", team_size=5)
    app = build_graph()
    thread = {"configurable": {"thread_id": "t5"}}

    with pytest.raises(AssumptionError):
        app.invoke({"brand": brand}, config=thread)


def test_scored_tasks_are_analysis_ready():
    """Scored output must serialize into an Analysis (persistence shape)."""
    app = build_graph()
    thread = {"configurable": {"thread_id": "t6"}}
    inputs = load_lumea()
    app.invoke(inputs, config=thread)
    result = resume(app, thread, "approve")

    analysis = Analysis(
        brand=inputs["brand"],
        assumptions=inputs["assumptions"],
        scored_tasks=result["scored_tasks"],
        deep_dives=result["deep_dives"],
        review_status="approved",
        report=result["report"],
    )
    assert analysis.review_status.value == "approved"
    assert analysis.scored_tasks[0].roi_rank == 1


def test_full_flow_with_crew_llm_produces_structured_dives():
    """Inject a fake CrewAI LLM; deep dives must be non-degraded."""
    from crewai.llm import LLM

    names = ["Shopify order processing", "Instagram DM responses", "Email support tickets"]
    rows = ", ".join(
        '{"task_name": "%s", "substeps": ["a"], "proposed_tool": "n8n", "agent_flow": "flow", '
        '"main_risk": "risk", "effort_weeks": 2, "pilot_plan": "pilot"}' % n
        for n in names
    )

    class FakeCrewLLM(LLM):
        def __init__(self):
            super().__init__(model="fake", api_key="x")

        def call(self, messages, callbacks=None, **kwargs):
            return f"Final Answer: [{rows}]"

    llm = RecordingMockLLM()
    app = build_graph(llm=llm, crew_llm=FakeCrewLLM())
    thread = {"configurable": {"thread_id": "t7"}}

    app.invoke(load_lumea(), config=thread)
    result = resume(app, thread, "approve")

    assert len(result["deep_dives"]) == 3
    assert all(not d.degraded for d in result["deep_dives"])
    assert result["deep_dives"][0].proposed_tool == "n8n"


def test_sqlite_checkpointer_resumes_same_thread_across_instances(tmp_path):
    """A fresh app built on the same DB file resumes the interrupted thread."""
    db = str(tmp_path / "checkpoints.db")

    app1 = build_graph(checkpointer=sqlite_checkpointer(db))
    thread = {"configurable": {"thread_id": "persist-1"}}
    app1.invoke(load_lumea(), config=thread)  # halts at review, state saved

    app2 = build_graph(checkpointer=sqlite_checkpointer(db))
    result = app2.invoke(Command(resume="approve"), config=thread)

    assert result["action"] == "approve"
    assert result["report"]
