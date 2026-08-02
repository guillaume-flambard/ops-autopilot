"""Crew deep-dive tests, isolated offline via a fake CrewAI LLM."""

import pytest

from crewai.llm import LLM

from crew.run_deep_dive import parse_crew_output, run_deep_dive
from domain.models import Assumptions, ScoredTask, Task
from domain.scoring import score_tasks


class FakeCrewLLM(LLM):
    """CrewAI-compatible fake that returns a canned reply."""

    def __init__(self, reply, error: Exception | None = None):
        super().__init__(model="fake", api_key="x")
        self.reply = reply
        self.error = error

    def call(self, messages, callbacks=None, **kwargs):
        if self.error:
            raise self.error
        return f"Final Answer: {self.reply}"


def _scored() -> list[ScoredTask]:
    tasks = [
        Task(name="DM", volume_per_week=350, minutes_per_unit=2, repetitiveness=5, automatability=4),
        Task(name="Orders", volume_per_week=700, minutes_per_unit=3, repetitiveness=3, automatability=4),
    ]
    return score_tasks(tasks, Assumptions(hourly_rate_eur=35))


GOOD_JSON = (
    '[{"task_name": "DM", "substeps": ["classer", "repondre"], "proposed_tool": "n8n", '
    '"agent_flow": "triage puis reponse", "main_risk": "ton de la marque", "effort_weeks": 2, '
    '"pilot_plan": "10% des DM pendant 2 semaines"}, '
    '{"task_name": "Orders", "substeps": ["importer", "valider"], "proposed_tool": "Zapier", '
    '"agent_flow": "webhook", "main_risk": "doublons", "effort_weeks": 3, "pilot_plan": "un canal"}'
    "]"
)


def test_no_llm_returns_degraded_template():
    dives = run_deep_dive(_scored(), Assumptions(hourly_rate_eur=35), llm=None)
    assert {d.task_name for d in dives} == {"DM", "Orders"}
    assert all(d.degraded for d in dives)


def test_crew_llm_parses_structured_output():
    dives = run_deep_dive(_scored(), Assumptions(hourly_rate_eur=35), llm=FakeCrewLLM(GOOD_JSON))
    assert len(dives) == 2
    d = dives[0]
    assert d.task_name == "DM"
    assert d.proposed_tool == "n8n"
    assert d.substeps == ["classer", "repondre"]
    assert d.main_risk == "ton de la marque"
    assert d.effort_weeks == 2
    assert d.pilot_plan
    assert d.degraded is False


def test_unparseable_output_falls_back_to_degraded():
    dives = run_deep_dive(_scored(), Assumptions(hourly_rate_eur=35), llm=FakeCrewLLM("no json here"))
    assert len(dives) == 2
    assert all(d.degraded for d in dives)


def test_crew_exception_falls_back_to_degraded():
    dives = run_deep_dive(
        _scored(),
        Assumptions(hourly_rate_eur=35),
        llm=FakeCrewLLM("", error=RuntimeError("rate limited")),
    )
    assert len(dives) == 2
    assert all(d.degraded for d in dives)


def test_parse_crew_output_ignores_unknown_tasks_and_bad_rows():
    raw = (
        '[{"task_name": "DM", "substeps": ["a"]}, {"task_name": "Ghost", "substeps": ["x"]}, '
        '"not a row", {"task_name": "Orders", "substeps": ["b"], "effort_weeks": "tres"}]'
    )
    dives = parse_crew_output(raw, _scored())
    assert [d.task_name for d in dives] == ["DM", "Orders"]
    # bad effort_weeks falls back to default 2
    assert dives[1].effort_weeks == 2


def test_parse_crew_output_empty_or_malformed():
    assert parse_crew_output("", _scored()) == []
    assert parse_crew_output("no brackets", _scored()) == []
    assert parse_crew_output("[broken", _scored()) == []
