"""Graph nodes. Each node returns a partial state update.

LLM-dependent nodes (map_tasks, deep_dive, report) take an ``LLMClient``
as an extra argument; build.py injects it via functools.partial so the
nodes stay plain, testable functions.
"""

from __future__ import annotations

from typing import Callable

from langgraph.types import interrupt

from domain.models import Assumptions
from domain.scoring import score_tasks, top_n


class AssumptionError(Exception):
    """Raised when an assumption required for scoring is missing or invalid."""


def ingest(state: dict) -> dict:
    brand = state["brand"]
    assumptions = state.get("assumptions") or brand.default_assumptions
    if assumptions is None or assumptions.hourly_rate_eur <= 0:
        raise AssumptionError(
            "hourly_rate_eur est obligatoire et doit etre > 0. "
            "Renseignez les hypotheses avant de lancer l'analyse."
        )
    return {
        "assumptions": assumptions,
        "tasks": list(brand.tasks),
        "step": "ingest",
        "events": [f"ingest: marque '{brand.name}' chargee ({brand.team_size} personnes, {len(brand.tasks)} taches)"],
    }


def map_tasks(state: dict, llm: LLMClient) -> dict:
    tasks = state.get("tasks")
    if tasks:
        return {"step": "map_tasks", "events": ["map_tasks: taches structurees fournies, pas de LLM necessaire"]}
    brand = state.get("brand")
    free_text = (brand.free_text if brand else "") or ""
    if not free_text.strip():
        return {"step": "map_tasks", "events": ["map_tasks: aucune tache ni texte libre"]}
    locale = state["assumptions"].locale.value
    tasks = llm.map_tasks_from_text(free_text, locale=locale)
    return {"tasks": tasks, "step": "map_tasks", "events": [f"map_tasks: {len(tasks)} taches extraites ({llm.name})"]}


def score(state: dict) -> dict:
    scored = score_tasks(state["tasks"], state["assumptions"])
    lead = scored[0].task.name if scored else "aucune"
    return {
        "scored_tasks": scored,
        "step": "score",
        "events": [f"score: {len(scored)} taches notees, priorite {lead}"],
    }


def check_data(state: dict) -> dict:
    assumptions: Assumptions = state["assumptions"]
    if assumptions.hourly_rate_eur <= 0 or assumptions.weeks_per_month <= 0:
        raise AssumptionError("Hypotheses invalides: taux horaire et semaines/mois doivent etre > 0.")
    if not state.get("scored_tasks"):
        return {"step": "check_data", "events": ["check_data: aucun score, nouveau passage"]}
    return {"step": "check_data", "events": ["check_data: hypotheses valides"]}


def deep_dive(state: dict, runner: callable) -> dict:
    """Run the CrewAI deep-dive on the top-3 tasks via the injected runner."""
    scored = top_n(state["scored_tasks"], n=3)
    dives = runner(scored, state["assumptions"])
    degraded = sum(1 for d in dives if d.degraded)
    tag = f" ({degraded} degrade(s))" if degraded else ""
    return {
        "deep_dives": dives,
        "step": "deep_dive",
        "events": [f"deep_dive: {len(dives)} plans pilotes{tag}"],
    }


def review_payload(state: dict) -> dict:
    """Serializable snapshot handed to the human at the review interrupt.

    The UI/CLI renders this without replaying the graph. Scored tasks and
    deep dives are also in the thread state; this is a compact projection.
    """
    scored = state.get("scored_tasks") or []
    dives = state.get("deep_dives") or []
    assumptions: Assumptions | None = state.get("assumptions")
    return {
        "scored_tasks": [
            {
                "rank": s.roi_rank,
                "task": s.task.name,
                "hours_per_month": round(s.hours_per_month, 1),
                "eur_per_month": round(s.eur_per_month, 0),
                "priority_score": round(s.priority_score, 1),
            }
            for s in scored
        ],
        "deep_dives": [
            {
                "task_name": d.task_name,
                "proposed_tool": d.proposed_tool,
                "effort_weeks": d.effort_weeks,
                "degraded": d.degraded,
            }
            for d in dives
        ],
        "assumptions": (
            {
                "hourly_rate_eur": assumptions.hourly_rate_eur,
                "weeks_per_month": assumptions.weeks_per_month,
                "locale": assumptions.locale.value,
            }
            if assumptions
            else None
        ),
    }


def human_review(state: dict) -> dict:
    """Human checkpoint. Halts the graph with an interrupt; resume via
    ``Command(resume="approve" | "edit" | "reject")``."""
    payload = review_payload(state)
    action = interrupt(payload)
    return {
        "action": action,
        "step": "human_review",
        "events": [f"human_review: {action}"],
    }


def report(state: dict, llm: LLMClient) -> dict:
    scored = state.get("scored_tasks") or []
    dives = state.get("deep_dives") or []
    brand = state.get("brand")
    sector = brand.sector.value if brand is not None else None
    text = llm.executive_report(scored, dives, state["assumptions"], sector=sector)
    return {
        "report": text,
        "step": "report",
        "events": [f"report: genere ({llm.name})"],
    }
