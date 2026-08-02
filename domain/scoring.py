"""Deterministic ROI scoring.

Every number that commits money or effort is computed here, in plain Python,
so it can be unit-tested without any LLM, graph framework, or UI in play.

Formulas (see domain/formulas.md for the human-readable version):

    hours_per_month = volume_per_week * (minutes_per_unit / 60) * weeks_per_month
    eur_per_month   = hours_per_month * hourly_rate_eur
    etp             = hours_per_month / 151.67
    priority_score  = hours_per_month * (repetitiveness / 5) * (automatability / 5)

ROI ranking: descending priority_score, tie-broken on eur_per_month.
"""

from __future__ import annotations

from typing import Iterable

from domain.models import Assumptions, ScoredTask, Task

# A 35h/week, 52-week year divided by 12 months.
HOURS_PER_FTE_PER_MONTH = 151.67


def hours_per_month(task: Task, weeks_per_month: float = Assumptions.model_fields["weeks_per_month"].default) -> float:
    return task.volume_per_week * (task.minutes_per_unit / 60.0) * weeks_per_month


def eur_per_month(hours: float, hourly_rate_eur: float) -> float:
    return hours * hourly_rate_eur


def etp(hours: float) -> float:
    return hours / HOURS_PER_FTE_PER_MONTH


def priority_score(task: Task, weeks_per_month: float = Assumptions.model_fields["weeks_per_month"].default) -> float:
    hours = hours_per_month(task, weeks_per_month)
    return hours * (task.repetitiveness / 5.0) * (task.automatability / 5.0)


def score_task(task: Task, assumptions: Assumptions) -> ScoredTask:
    """Compute every derived figure for a single task."""
    hours = hours_per_month(task, assumptions.weeks_per_month)
    return ScoredTask(
        task=task,
        hours_per_month=hours,
        eur_per_month=eur_per_month(hours, assumptions.hourly_rate_eur),
        etp=etp(hours),
        priority_score=priority_score(task, assumptions.weeks_per_month),
    )


def rank_tasks(scored_tasks: Iterable[ScoredTask]) -> list[ScoredTask]:
    """Assign ROI ranks in place. Highest priority_score = rank 1; ties on eur_per_month."""
    ordered = sorted(scored_tasks, key=lambda s: (-s.priority_score, -s.eur_per_month))
    for rank, scored in enumerate(ordered, start=1):
        scored.roi_rank = rank
    return ordered


def score_tasks(tasks: Iterable[Task], assumptions: Assumptions) -> list[ScoredTask]:
    """Score and rank every task in one call."""
    return rank_tasks(score_task(t, assumptions) for t in tasks)


def top_n(scored_tasks: Iterable[ScoredTask], n: int = 3) -> list[ScoredTask]:
    """Select the n highest-ranked tasks for deep dive."""
    ranked = [s for s in scored_tasks if s.roi_rank is not None]
    return sorted(ranked, key=lambda s: s.roi_rank or 0)[:n]


def totals(scored_tasks: Iterable[ScoredTask]) -> dict[str, float]:
    total_hours = sum(s.hours_per_month for s in scored_tasks)
    return {
        "total_hours_per_month": total_hours,
        "total_eur_per_month": sum(s.eur_per_month for s in scored_tasks),
        "total_etp": total_hours / HOURS_PER_FTE_PER_MONTH,
    }
