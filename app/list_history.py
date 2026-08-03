"""List past analyses for a user (history use case)."""

from __future__ import annotations

from db.repo import list_analyses


def list_history(user_id: int, limit: int = 50, url: str | None = None) -> list[dict]:
    return list_analyses(user_id, limit=limit, url=url)
