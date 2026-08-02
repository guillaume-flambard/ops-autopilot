"""Deep-dive orchestrator: the only place CrewAI is used.

``run_deep_dive`` accepts a CrewAI-compatible llm (``crewai.LLM`` for Groq,
or a fake subclass in tests). With no llm, or on any failure (rate limit,
parse error, exception), it degrades to a deterministic template marked as
``degraded``.
"""

from __future__ import annotations

import json
import logging

from crewai import Crew, Process

from domain.models import Assumptions, DeepDive, ScoredTask
from llm.client import degraded_deep_dive

logger = logging.getLogger(__name__)


def run_deep_dive(
    scored_tasks: list[ScoredTask],
    assumptions: Assumptions,
    llm=None,
    locale: str = "fr",
) -> list[DeepDive]:
    if llm is None or not scored_tasks:
        return degraded_deep_dive(scored_tasks, assumptions)

    from crew.agents import build_agents
    from crew.tasks import build_tasks

    try:
        agents = build_agents(llm, locale=locale)
        tasks = build_tasks(scored_tasks, assumptions, agents, locale=locale)
        crew = Crew(agents=agents, tasks=tasks, process=Process.sequential, verbose=False)
        raw = str(crew.kickoff())
        dives = parse_crew_output(raw, scored_tasks)
        if not dives:
            logger.warning("deep-dive: crew output unparseable, using degraded template")
            return degraded_deep_dive(scored_tasks, assumptions)
        return dives
    except Exception as exc:  # rate limit, bad JSON, network
        logger.warning("deep-dive: crew failed (%s), using degraded template", exc)
        return degraded_deep_dive(scored_tasks, assumptions)


def parse_crew_output(raw: str, scored_tasks: list[ScoredTask]) -> list[DeepDive]:
    data = _extract_json_array(raw)
    if not isinstance(data, list):
        return []
    known = {s.task.name: s for s in scored_tasks}
    dives = []
    for item in data:
        if not isinstance(item, dict) or "task_name" not in item:
            continue
        name = item["task_name"]
        if name not in known:
            continue
        dives.append(
            DeepDive(
                task_name=name,
                substeps=[str(s) for s in item.get("substeps", [])],
                proposed_tool=str(item.get("proposed_tool", "")),
                agent_flow=str(item.get("agent_flow", "")),
                main_risk=str(item.get("main_risk", "")),
                effort_weeks=_as_float(item.get("effort_weeks"), 2),
                pilot_plan=str(item.get("pilot_plan", "")),
            )
        )
    return dives


def _extract_json_array(raw: str):
    start = raw.find("[")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "[":
            depth += 1
        elif raw[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
