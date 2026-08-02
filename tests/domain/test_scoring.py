"""Unit tests for the deterministic ROI scoring engine.

These run with no LLM, no graph, and no UI: pure formula math against the
Lumea and SaaS fixture profiles.
"""

import json
from pathlib import Path

import pytest

from domain.models import Assumptions, BrandProfile
from domain.scoring import (
    HOURS_PER_FTE_PER_MONTH,
    etp,
    eur_per_month,
    hours_per_month,
    priority_score,
    score_task,
    score_tasks,
    top_n,
    totals,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILES_DIR = REPO_ROOT / "profiles"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def load_profile(name: str) -> tuple[BrandProfile, dict]:
    with open(PROFILES_DIR / f"{name}.json") as f:
        data = json.load(f)
    profile = BrandProfile(**data)
    with open(FIXTURES_DIR / f"{name}_expected.json") as f:
        expected = json.load(f)
    return profile, expected


@pytest.mark.parametrize("profile_name", ["lumea", "saas"])
def test_profile_matches_expected_scores(profile_name):
    profile, expected = load_profile(profile_name)
    scored = score_tasks(profile.tasks, profile.default_assumptions)
    assert len(scored) == len(expected["tasks"])

    for scored_task, exp in zip(scored, expected["tasks"], strict=True):
        assert scored_task.task.name == exp["task"]
        assert scored_task.hours_per_month == pytest.approx(exp["hours_per_month"], abs=1e-3)
        assert scored_task.eur_per_month == pytest.approx(exp["eur_per_month"], abs=1e-3)
        assert scored_task.etp == pytest.approx(exp["etp"], abs=1e-3)
        assert scored_task.priority_score == pytest.approx(exp["priority_score"], abs=1e-3)
        assert scored_task.roi_rank == exp["roi_rank"]


def test_lumea_roi_rank_order():
    """The highest priority_score task must rank first."""
    profile, _ = load_profile("lumea")
    scored = score_tasks(profile.tasks, profile.default_assumptions)
    names = [s.task.name for s in scored]
    assert names[0] == "Shopify order processing"
    assert names[1] == "Instagram DM responses"
    assert names[2] == "Email support tickets"
    assert names[3] == "Product photography planning"


def test_top_n_selects_three_highest():
    profile, _ = load_profile("lumea")
    scored = score_tasks(profile.tasks, profile.default_assumptions)
    selected = top_n(scored, n=3)
    assert [s.task.name for s in selected] == [
        "Shopify order processing",
        "Instagram DM responses",
        "Email support tickets",
    ]
    assert all(s.roi_rank is not None and s.roi_rank <= 3 for s in selected)


def test_totals_match_fixture():
    profile, expected = load_profile("lumea")
    scored = score_tasks(profile.tasks, profile.default_assumptions)
    t = totals(scored)
    assert t["total_hours_per_month"] == pytest.approx(expected["totals"]["total_hours_per_month"], abs=1e-3)
    assert t["total_eur_per_month"] == pytest.approx(expected["totals"]["total_eur_per_month"], abs=1e-3)
    assert t["total_etp"] == pytest.approx(expected["totals"]["total_etp"], abs=1e-3)


def test_assumptions_totals_agree_with_scoring():
    profile, _ = load_profile("lumea")
    scored = score_tasks(profile.tasks, profile.default_assumptions)
    panel = profile.default_assumptions.totals(scored)
    t = totals(scored)
    assert panel == pytest.approx(t)


def test_hours_per_month_formula():
    task = _task(volume=100, minutes=60, rep=5, auto=5)
    assert hours_per_month(task, weeks_per_month=4.0) == pytest.approx(400.0)
    assert eur_per_month(400.0, hourly_rate_eur=50) == pytest.approx(20000.0)
    assert etp(151.67) == pytest.approx(1.0)
    assert priority_score(task, weeks_per_month=4.0) == pytest.approx(400.0)


def test_zero_volume_task_scores_zero():
    task = _task(volume=0, minutes=30, rep=5, auto=5)
    scored = score_task(task, Assumptions(hourly_rate_eur=35))
    assert scored.hours_per_month == 0
    assert scored.eur_per_month == 0
    assert scored.etp == 0
    assert scored.priority_score == 0


def test_high_repetitiveness_dominates():
    a = Assumptions(hourly_rate_eur=35)
    low = score_task(_task(volume=10, minutes=60, rep=1, auto=1), a)
    high = score_task(_task(volume=10, minutes=60, rep=5, auto=5), a)
    assert high.priority_score == pytest.approx(low.priority_score * 25)


def test_tie_breaks_stably_on_eur_per_month():
    """Same priority_score tasks keep input order via a stable sort."""
    a = Assumptions(hourly_rate_eur=35)
    t1 = _task(volume=10, minutes=30, rep=5, auto=5)
    t2 = _task(volume=10, minutes=30, rep=5, auto=5)
    ranked = score_tasks([t2, t1], a)  # reversed input order
    assert [s.roi_rank for s in ranked] == [1, 2]


def _task(volume, minutes, rep, auto):
    from domain.models import Task

    return Task(
        name=f"t-{volume}-{minutes}",
        volume_per_week=volume,
        minutes_per_unit=minutes,
        repetitiveness=rep,
        automatability=auto,
    )
