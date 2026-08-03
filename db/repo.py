"""Repositories + auth helpers over SQLAlchemy (construction-order step 6).

Engines are cached per URL so tests can point at a temp database without
disturbing the app's default. Public functions accept an explicit ``url``
and otherwise fall back to ``DATABASE_URL`` env / config default.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

import bcrypt
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import settings
from db.models import Analysis, Base, User

_engines: dict[str, Engine] = {}
_sessionmakers: dict[str, sessionmaker] = {}


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def resolve_database_url() -> str:
    return os.getenv("DATABASE_URL") or settings.database_url


def get_engine(url: Optional[str] = None) -> Engine:
    url = url or resolve_database_url()
    if url not in _engines:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engines[url] = create_engine(url, connect_args=connect_args)
    return _engines[url]


def _sessionmaker(url: Optional[str] = None) -> sessionmaker:
    url = url or resolve_database_url()
    if url not in _sessionmakers:
        _sessionmakers[url] = sessionmaker(bind=get_engine(url), expire_on_commit=False)
    return _sessionmakers[url]


def init_db(url: Optional[str] = None) -> None:
    Base.metadata.create_all(get_engine(url))


@contextmanager
def session_scope(url: Optional[str] = None) -> Iterator[Session]:
    session = _sessionmaker(url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --- users / auth ---------------------------------------------------------


def create_user(email: str, password: str, url: Optional[str] = None) -> User:
    email = email.strip().lower()
    with session_scope(url) as s:
        if s.scalar(select(User).where(User.email == email)):
            raise ValueError("email_already_registered")
        user = User(email=email, password_hash=_hash_password(password))
        s.add(user)
        s.flush()
        return user


def get_user_by_email(email: str, url: Optional[str] = None) -> User | None:
    email = email.strip().lower()
    with session_scope(url) as s:
        return s.scalar(select(User).where(User.email == email))


def authenticate(email: str, password: str, url: Optional[str] = None) -> User | None:
    user = get_user_by_email(email, url=url)
    if user is not None and _verify_password(password, user.password_hash):
        return user
    return None


def user_to_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email}


# --- analyses / history ---------------------------------------------------


def create_analysis(
    user_id: int | None,
    brand_name: str,
    review_status: str,
    assumptions: dict,
    result: dict,
    report: str | None = None,
    url: Optional[str] = None,
) -> int:
    with session_scope(url) as s:
        row = Analysis(
            user_id=user_id,
            brand_name=brand_name,
            review_status=review_status,
            assumptions_json=json.dumps(assumptions, default=str),
            result_json=json.dumps(result, default=str),
            report=report,
        )
        s.add(row)
        s.flush()
        return row.id


def update_analysis(
    analysis_id: int,
    review_status: str | None = None,
    report: str | None = None,
    url: Optional[str] = None,
) -> None:
    with session_scope(url) as s:
        row = s.get(Analysis, analysis_id)
        if row is None:
            return
        if review_status is not None:
            row.review_status = review_status
        if report is not None:
            row.report = report
        row.updated_at = datetime.now(timezone.utc)


def get_analysis(analysis_id: int, user_id: int | None, url: Optional[str] = None) -> dict | None:
    with session_scope(url) as s:
        row = s.get(Analysis, analysis_id)
        if row is None or row.user_id != user_id:
            return None
        return analysis_to_dict(row)


def list_analyses(user_id: int, limit: int = 50, url: Optional[str] = None) -> list[dict]:
    with session_scope(url) as s:
        rows = (
            s.execute(
                select(Analysis)
                .where(Analysis.user_id == user_id)
                .order_by(Analysis.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [analysis_to_dict(row) for row in rows]


def analysis_to_dict(row: Analysis) -> dict:
    return {
        "id": row.id,
        "brand_name": row.brand_name,
        "review_status": row.review_status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "report": row.report,
    }


def delete_analysis(analysis_id: int, user_id: int | None, url: Optional[str] = None) -> bool:
    with session_scope(url) as s:
        row = s.get(Analysis, analysis_id)
        if row is None or row.user_id != user_id:
            return False
        s.delete(row)
        return True


def checkpoint_db_path() -> str:
    """SQLite file path for the LangGraph checkpointer (same DB as app tables)."""
    url = resolve_database_url()
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///") :]
    # Non-sqlite backend: keep checkpoints in a sibling local file.
    return str(os.getenv("CHECKPOINT_DB", "ops_autopilot_checkpoints.db"))
