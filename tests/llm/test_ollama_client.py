"""Hermetic tests for OllamaClient (local LLM path).

A MockTransport stands in for the local Ollama server, so these run in CI
with no network and no Ollama installed.
"""

from __future__ import annotations

import httpx
import pytest

from domain.models import Assumptions, ScoredTask, Task
from llm.client import MockClient, OllamaClient, _ollama_reachable, get_client


def _client_for(responses: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = responses.pop(0)
        return httpx.Response(payload.pop("status", 200), json=payload)

    transport = httpx.MockTransport(handler)
    return OllamaClient(transport=transport)


def test_complete_returns_message_content() -> None:
    client = _client_for([{"message": {"content": "bonjour"}}])
    assert client._complete("salut") == "bonjour"


def test_complete_retries_then_raises_on_5xx() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={"error": "boom"})

    client = OllamaClient(max_retries=2, transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError):
        client._complete("salut")
    assert calls["n"] == 2


def test_map_tasks_parses_fenced_response() -> None:
    client = _client_for(
        [
            {
                "message": {
                    "content": (
                        '```json\n[{"name": "DM", "volume_per_week": 350, "minutes_per_unit": 2, '
                        '"repetitiveness": 5, "automatability": 4}]\n```'
                    )
                }
            }
        ]
    )
    tasks = client.map_tasks_from_text("anything")
    assert len(tasks) == 1
    assert tasks[0].name == "DM"
    assert tasks[0].volume_per_week == 350


def test_deep_dive_degrades_on_bad_json() -> None:
    client = _client_for([{"message": {"content": "je ne suis pas du json"}}])
    assumptions = Assumptions(hourly_rate_eur=40)
    task = Task(name="DM", volume_per_week=350, minutes_per_unit=2, repetitiveness=5, automatability=4)
    scored = [ScoredTask(task=task, hours_per_month=1, eur_per_month=100, etp=0.01, priority_score=1.0)]
    dives = client.deep_dive(scored, assumptions)
    assert len(dives) == 1
    assert dives[0].degraded is True
    assert dives[0].task_name == "DM"


def test_deep_dive_parses_valid_object() -> None:
    client = _client_for(
        [
            {
                "message": {
                    "content": (
                        '{"substeps": ["a"], "proposed_tool": "n8n", "agent_flow": "trigger", '
                        '"main_risk": "low", "effort_weeks": 2, "pilot_plan": "pilote"}'
                    )
                }
            }
        ]
    )
    assumptions = Assumptions(hourly_rate_eur=40)
    task = Task(name="DM", volume_per_week=350, minutes_per_unit=2, repetitiveness=5, automatability=4)
    scored = [ScoredTask(task=task, hours_per_month=1, eur_per_month=100, etp=0.01, priority_score=1.0)]
    dives = client.deep_dive(scored, assumptions)
    assert len(dives) == 1
    assert dives[0].degraded is False
    assert dives[0].proposed_tool == "n8n"


def test_deep_dive_flattens_object_substeps() -> None:
    """Small local models return substeps as objects; they must be flattened."""
    client = _client_for(
        [
            {
                "message": {
                    "content": (
                        '{"substeps": [{"step": "1", "description": "Analyser"}, '
                        '{"step": "2", "description": "Construire"}], '
                        '"proposed_tool": "n8n", "agent_flow": "trigger", '
                        '"main_risk": "low", "effort_weeks": 2, "pilot_plan": "pilote"}'
                    )
                }
            }
        ]
    )
    assumptions = Assumptions(hourly_rate_eur=40)
    task = Task(name="DM", volume_per_week=350, minutes_per_unit=2, repetitiveness=5, automatability=4)
    scored = [ScoredTask(task=task, hours_per_month=1, eur_per_month=100, etp=0.01, priority_score=1.0)]
    dives = client.deep_dive(scored, assumptions)
    assert len(dives) == 1
    assert dives[0].degraded is False
    assert dives[0].substeps == ["Analyser", "Construire"]


def test_deep_dive_flattens_list_and_dict_text_fields() -> None:
    """agent_flow / pilot_plan may come back as lists or dicts, not strings."""
    client = _client_for(
        [
            {
                "message": {
                    "content": (
                        '{"substeps": [{"description": "Etape A"}, "Etape B"], '
                        '"proposed_tool": "n8n", '
                        '"agent_flow": {"step1": "Reception", "step2": "Analyse"}, '
                        '"main_risk": ["Risque 1", {"description": "Risque 2"}], '
                        '"effort_weeks": 2, "pilot_plan": [{"week": 1, "substeps": ["Tester"]}]}'
                    )
                }
            }
        ]
    )
    assumptions = Assumptions(hourly_rate_eur=40)
    task = Task(name="DM", volume_per_week=350, minutes_per_unit=2, repetitiveness=5, automatability=4)
    scored = [ScoredTask(task=task, hours_per_month=1, eur_per_month=100, etp=0.01, priority_score=1.0)]
    dives = client.deep_dive(scored, assumptions)
    assert len(dives) == 1
    assert dives[0].degraded is False
    assert dives[0].substeps == ["Etape A", "Etape B"]
    assert dives[0].agent_flow == "Reception | Analyse"
    assert dives[0].main_risk == "Risque 1 | Risque 2"
    assert "Tester" in dives[0].pilot_plan


def test_executive_report_returns_raw_text() -> None:
    client = _client_for([{"message": {"content": "rapport executif"}}])
    assumptions = Assumptions(hourly_rate_eur=40)
    out = client.executive_report([], [], assumptions, sector="D2C")
    assert out == "rapport executif"


def test_ollama_reachable_true_when_tags_endpoint_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        status_code = 200

    monkeypatch.setattr("llm.client.httpx.get", lambda *a, **k: _FakeResponse())
    assert _ollama_reachable("http://localhost:11434") is True


def test_ollama_reachable_false_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a, **k):
        raise ConnectionError("refused")

    monkeypatch.setattr("llm.client.httpx.get", _boom)
    assert _ollama_reachable("http://localhost:11434") is False


def test_get_client_ollama_unreachable_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a, **k):
        raise ConnectionError("refused")

    monkeypatch.setattr("llm.client.httpx.get", _boom)
    client = get_client(llm_provider="ollama", model="qwen2.5:3b")
    assert isinstance(client, MockClient)
