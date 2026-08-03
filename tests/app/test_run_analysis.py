"""Tests for the app/ use-case layer (construction-order step 7).

These lock in that both the CLI and the Streamlit UI drive the graph through
the same code path: build_runtime -> run_analysis -> resume_review.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from app.list_history import list_history
from app.presets import load_preset
from app.run_analysis import build_runtime, resume_review, run_analysis
from db.repo import create_user, get_user_by_email, init_db

_TMP = tempfile.mkdtemp(prefix="oa-app-test-")
DB_URL = "sqlite:///" + os.path.join(_TMP, "test.db")
CHECKPOINT_DB = os.path.join(_TMP, "checkpoints.db")


@pytest.fixture()
def runtime():
    return build_runtime(checkpoint_db=CHECKPOINT_DB)


def _lumea():
    brand = load_preset("lumea")
    return brand, brand.default_assumptions


def test_build_runtime_mock() -> None:
    rt = build_runtime(checkpoint_db=CHECKPOINT_DB)
    assert rt.llm_name == "mock"
    assert rt.app is not None


def test_run_analysis_halts_at_review(runtime) -> None:
    brand, assumptions = _lumea()
    result = run_analysis(brand, assumptions, runtime)
    assert result.interrupted is not None
    assert result.interrupted["scored_tasks"][0]["rank"] == 1
    assert result.events
    assert result.thread_id in result.config["configurable"]["thread_id"]


def test_resume_approve_produces_report(runtime) -> None:
    brand, assumptions = _lumea()
    result = run_analysis(brand, assumptions, runtime)
    resumed = resume_review(runtime, result.config, "approve")
    assert resumed.interrupted is None
    assert resumed.final["action"] == "approve"
    assert resumed.final["report"]
    full = runtime.app.get_state(result.config).values
    assert len(full["deep_dives"]) == 3
    assert all(d.degraded for d in full["deep_dives"])


def test_resume_reject_skips_report(runtime) -> None:
    brand, assumptions = _lumea()
    result = run_analysis(brand, assumptions, runtime)
    resumed = resume_review(runtime, result.config, "reject")
    assert resumed.final["action"] == "reject"
    assert resumed.final.get("report") is None


def test_resume_edit_rescores_with_new_rate(runtime) -> None:
    brand, assumptions = _lumea()
    result = run_analysis(brand, assumptions, runtime)
    edited = assumptions.model_copy(update={"hourly_rate_eur": 90.0})
    re_scored = resume_review(runtime, result.config, "edit", assumptions=edited)
    assert re_scored.final["action"] == "edit"
    assert re_scored.interrupted is not None, "edited scores need a second review"
    approved = resume_review(runtime, result.config, "approve")
    assert approved.final["report"]
    full = runtime.app.get_state(result.config).values
    assert full["assumptions"].hourly_rate_eur == 90.0


def test_resume_edit_rescores_with_edited_tasks(runtime) -> None:
    """The human can correct task volumes before approving (website workflow)."""
    brand, assumptions = _lumea()
    result = run_analysis(brand, assumptions, runtime)
    full = runtime.app.get_state(result.config).values
    first = full["tasks"][0]
    corrected = [first.model_copy(update={"volume_per_week": 100.0})]
    re_scored = resume_review(runtime, result.config, "edit", tasks=corrected)
    assert re_scored.interrupted is not None, "edited tasks need a second review"
    after = runtime.app.get_state(result.config).values
    assert after["tasks"][0].volume_per_week == 100.0
    assert after["scored_tasks"][0].task.volume_per_week == 100.0
    approved = resume_review(runtime, result.config, "approve")
    assert approved.final["report"]


def test_list_history_delegates_to_repo() -> None:
    init_db(DB_URL)
    try:
        user = create_user("history@example.com", "pw", url=DB_URL)
    except ValueError:
        user = get_user_by_email("history@example.com", url=DB_URL)
    rows = list_history(user.id, url=DB_URL)
    assert rows == []
