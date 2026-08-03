"""Unit tests for LLM JSON extraction (the live Groq path).

Chat models wrap JSON in markdown fences or prose; ``_extract_json`` must
recover a valid value from those responses.
"""

from __future__ import annotations

import pytest

from domain.models import Assumptions, ScoredTask, Task
from llm.client import GroqClient, _extract_json


class _StubGroq(GroqClient):
    """GroqClient whose ``_complete`` returns canned text (no network)."""

    def __init__(self, responses: list[str]) -> None:
        super().__init__(api_key="dummy-key")
        self._responses = list(responses)
        self.calls = 0

    def _complete(self, prompt: str, timeout: int = 30) -> str:
        self.calls += 1
        return self._responses.pop(0)


def test_plain_array() -> None:
    out = _extract_json('[{"name": "a"}]', expect_array=True)
    assert out == [{"name": "a"}]


def test_markdown_fenced_array() -> None:
    raw = "```json\n[{\"name\": \"a\"}]\n```"
    assert _extract_json(raw, expect_array=True) == [{"name": "a"}]


def test_array_embedded_in_prose() -> None:
    raw = 'Voici les taches : [{"name": "a"}, {"name": "b"}]. Fin.'
    assert _extract_json(raw, expect_array=True) == [{"name": "a"}, {"name": "b"}]


def test_object_embedded_in_prose() -> None:
    raw = 'Response: {"task_name": "x", "effort_weeks": 2} -- done.'
    out = _extract_json(raw, expect_array=False)
    assert out["task_name"] == "x"
    assert out["effort_weeks"] == 2


def test_missing_json_raises() -> None:
    with pytest.raises(ValueError):
        _extract_json("Je ne peux pas repondre.", expect_array=True)


def test_unbalanced_json_raises() -> None:
    with pytest.raises(ValueError):
        _extract_json('[{"name": "a"}', expect_array=True)


# --- GroqClient methods through a stubbed _complete --------------------------


def test_map_tasks_parses_fenced_response() -> None:
    client = _StubGroq(
        [
            '```json\n[{"name": "DM", "volume_per_week": 350, "minutes_per_unit": 2, '
            '"repetitiveness": 5, "automatability": 4}]\n```'
        ]
    )
    tasks = client.map_tasks_from_text("anything")
    assert len(tasks) == 1
    assert tasks[0].name == "DM"
    assert tasks[0].volume_per_week == 350
    assert client.calls == 1


def test_deep_dive_degrades_on_bad_json() -> None:
    client = _StubGroq(["je ne suis pas du json"])
    assumptions = Assumptions(hourly_rate_eur=40)
    task = Task(name="DM", volume_per_week=350, minutes_per_unit=2, repetitiveness=5, automatability=4)
    scored = [ScoredTask(task=task, hours_per_month=1, eur_per_month=100, etp=0.01, priority_score=1.0)]
    dives = client.deep_dive(scored, assumptions)
    assert len(dives) == 1
    assert dives[0].degraded is True
    assert dives[0].task_name == "DM"


def test_executive_report_passes_sector() -> None:
    client = _StubGroq(["rapport"])
    assumptions = Assumptions(hourly_rate_eur=40)
    out = client.executive_report([], [], assumptions, sector="D2C")
    assert out == "rapport"
    assert client.calls == 1
