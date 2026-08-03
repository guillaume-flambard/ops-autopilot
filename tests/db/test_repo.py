"""Tests for the DB layer: users, auth, and analysis history."""

from __future__ import annotations

import os
import uuid

import pytest

from db.repo import (
    authenticate,
    checkpoint_db_path,
    create_analysis,
    create_user,
    delete_analysis,
    get_analysis,
    get_user_by_email,
    init_db,
    list_analyses,
    resolve_database_url,
    update_analysis,
)


@pytest.fixture()
def url(tmp_path) -> str:
    return "sqlite:///" + str(tmp_path / "test.db")


@pytest.fixture()
def user_id(url) -> int:
    init_db(url)
    email = f"user{uuid.uuid4().hex[:10]}@example.com"
    return create_user(email, "s3cret!", url=url).id


def test_create_user_normalizes_email_and_hashes_password(url) -> None:
    init_db(url)
    email = f"User{uuid.uuid4().hex[:8]}@Example.com"
    user = create_user(email, "hunter2", url=url)
    assert user.email == email.lower()
    assert user.password_hash != "hunter2"
    assert user.password_hash.startswith("$2")


def test_duplicate_email_rejected(url, user_id) -> None:
    dup = create_user("A@Example.com", "x", url=url)
    with pytest.raises(ValueError, match="email_already_registered"):
        create_user("a@example.com", "y", url=url)
    delete_analysis(1, dup.id, url=url)


def test_authenticate(url, user_id) -> None:
    email = get_user_by_email(f"a@example.com", url=url)
    # the user_id fixture uses a random email; fetch it via a fresh create instead
    e = f"auth{uuid.uuid4().hex[:8]}@example.com"
    create_user(e, "pw", url=url)
    assert authenticate(e, "pw", url=url) is not None
    assert authenticate(e, "wrong", url=url) is None
    assert authenticate("missing@example.com", "pw", url=url) is None


def test_analysis_lifecycle(url, user_id) -> None:
    aid = create_analysis(
        user_id, "Lumea", "approved", {"hourly_rate_eur": 40}, {"scored_tasks": [{"rank": 1}]}, "report v1", url=url
    )
    row = get_analysis(aid, user_id, url=url)
    assert row["review_status"] == "approved"
    assert row["report"] == "report v1"

    update_analysis(aid, review_status="edited", report="report v2", url=url)
    assert get_analysis(aid, user_id, url=url)["review_status"] == "edited"

    rows = list_analyses(user_id, url=url)
    assert len(rows) == 1
    assert rows[0]["brand_name"] == "Lumea"

    assert get_analysis(aid, 999, url=url) is None, "cross-user read must be denied"
    assert delete_analysis(aid, 999, url=url) is False, "cross-user delete must be denied"
    assert delete_analysis(aid, user_id, url=url) is True
    assert get_analysis(aid, user_id, url=url) is None


def test_list_analyses_orders_by_newest_first(url, user_id) -> None:
    for i in range(3):
        create_analysis(user_id, f"Brand{i}", "pending", {}, {}, url=url)
    rows = list_analyses(user_id, url=url)
    assert [r["brand_name"] for r in rows] == ["Brand2", "Brand1", "Brand0"]


def test_list_analyses_scoped_to_user(url, user_id) -> None:
    other = create_user(f"other{uuid.uuid4().hex[:8]}@example.com", "pw", url=url)
    create_analysis(user_id, "Mine", "pending", {}, {}, url=url)
    create_analysis(other.id, "Theirs", "pending", {}, {}, url=url)
    assert [r["brand_name"] for r in list_analyses(user_id, url=url)] == ["Mine"]
    assert [r["brand_name"] for r in list_analyses(other.id, url=url)] == ["Theirs"]


def test_checkpoint_db_path_uses_database_url(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "app.db"))
    assert checkpoint_db_path() == str(tmp_path / "app.db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host/db")
    monkeypatch.delenv("CHECKPOINT_DB", raising=False)
    assert checkpoint_db_path() == "ops_autopilot_checkpoints.db"


def test_postgres_database_url_passes_through(monkeypatch) -> None:
    """A non-SQLite URL is used verbatim (no sqlite path rewriting)."""
    dsn = "postgresql+psycopg://user:pw@host:5432/ops_autopilot"
    monkeypatch.setenv("DATABASE_URL", dsn)
    assert resolve_database_url() == dsn


def test_checkpoint_path_for_postgres_backend_stays_local(monkeypatch, tmp_path) -> None:
    """With Postgres as the app DB, the checkpointer still uses a local SQLite
    file, honouring CHECKPOINT_DB, and never returns the Postgres DSN."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pw@host/db")
    ckpt = str(tmp_path / "ckpt.db")
    monkeypatch.setenv("CHECKPOINT_DB", ckpt)
    resolved = checkpoint_db_path()
    assert resolved == ckpt
    assert not resolved.startswith("postgresql")
