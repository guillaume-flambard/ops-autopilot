"""End-to-end integration tests (construction-order spec section 9).

Prove the whole production path works together against a real SQLite
database and a real on-disk checkpointer, with the deterministic mock LLM:

  graph (run -> human-review interrupt -> approve)  x  db (persist -> list)
                                                     x  checkpointer (resume the
                                                     same thread from a fresh
                                                     runtime, like a UI refresh)
"""

from __future__ import annotations

import os
import tempfile

from app.presets import load_preset
from app.run_analysis import build_runtime, resume_review, run_analysis
from db.repo import (
    authenticate,
    create_analysis,
    create_user,
    delete_analysis,
    get_analysis,
    init_db,
    list_analyses,
    update_analysis,
)

_TMP = tempfile.mkdtemp(prefix="oa-e2e-")
DB_URL = "sqlite:///" + os.path.join(_TMP, "e2e.db")
CHECKPOINT_DB = os.path.join(_TMP, "e2e-checkpoints.db")


def _run_to_review():
    brand, assumptions = load_preset("lumea"), load_preset("lumea").default_assumptions
    return brand, assumptions


def test_full_pipeline_persists_and_resumes_across_instances() -> None:
    init_db(DB_URL)

    user = create_user("e2e@example.com", "hunter2", url=DB_URL)
    assert authenticate("e2e@example.com", "hunter2", url=DB_URL) is not None
    assert authenticate("e2e@example.com", "wrong", url=DB_URL) is None

    brand, assumptions = _run_to_review()

    first = build_runtime(checkpoint_db=CHECKPOINT_DB)
    result = run_analysis(brand, assumptions, first)
    assert result.interrupted is not None, "run must halt at the human-review gate"

    fresh = build_runtime(checkpoint_db=CHECKPOINT_DB)
    resumed = resume_review(fresh, result.config, "approve")
    assert resumed.interrupted is None
    assert resumed.final["action"] == "approve"
    assert resumed.final["report"], "approved run must produce an executive report"

    analysis_id = create_analysis(
        user.id,
        brand.name,
        "approved",
        assumptions.model_dump(),
        resumed.final,
        report=resumed.final["report"],
        url=DB_URL,
    )
    update_analysis(analysis_id, review_status="approved", url=DB_URL)

    rows = list_analyses(user.id, url=DB_URL)
    assert [r["id"] for r in rows] == [analysis_id]
    stored = get_analysis(analysis_id, user.id, url=DB_URL)
    assert stored is not None
    assert stored["review_status"] == "approved"
    assert stored["report"] == resumed.final["report"]

    assert delete_analysis(analysis_id, user.id, url=DB_URL) is True
    assert list_analyses(user.id, url=DB_URL) == []


def test_paused_thread_resumes_from_fresh_runtime_like_a_ui_refresh() -> None:
    """A run halted at review survives "page refresh": a brand-new runtime
    built over the same checkpoint DB resumes the identical thread."""
    brand, assumptions = _run_to_review()

    runtime_a = build_runtime(checkpoint_db=CHECKPOINT_DB)
    result = run_analysis(brand, assumptions, runtime_a)
    assert result.interrupted is not None

    runtime_b = build_runtime(checkpoint_db=CHECKPOINT_DB)
    resumed = resume_review(runtime_b, result.config, "approve")
    assert resumed.interrupted is None
    assert resumed.final["report"]

    full = runtime_b.app.get_state(result.config).values
    assert full["brand"].name == brand.name
    assert len(full["scored_tasks"]) > 0
