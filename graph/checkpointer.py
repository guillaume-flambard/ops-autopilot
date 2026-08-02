"""Checkpointer helpers.

State contains Pydantic models (BrandProfile, ScoredTask, ...), so the
checkpointer must use a serializer that understands them
(``JsonPlusSerializer``). Plain JSON (the default) fails on BrandProfile.

The sqlite saver additionally JSON-encodes checkpoint ``metadata`` (which
carries node ``writes``) with plain ``json.dumps``, so we flatten any
Pydantic objects in the writes to plain dicts before saving.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

import domain.models as domain_models

# Register every class defined in domain.models so checkpoint resume does not warn.
_ALLOWED_MSGPACK_TYPES = {
    ("domain.models", name)
    for name, obj in vars(domain_models).items()
    if isinstance(obj, type)
}

SERDE = JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_MSGPACK_TYPES)


def _json_safe(value):
    """Recursively convert Pydantic models / datetimes to JSON-safe values."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(val) for val in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class PydanticSqliteSaver(SqliteSaver):
    """SqliteSaver whose checkpoint metadata tolerates Pydantic models."""

    def put(self, config, checkpoint, metadata, new_versions):
        if metadata and "writes" in metadata:
            metadata = {**metadata, "writes": _json_safe(metadata["writes"])}
        return super().put(config, checkpoint, metadata, new_versions)


def memory_checkpointer() -> MemorySaver:
    """In-memory saver, used by tests and as the default."""
    return MemorySaver(serde=SERDE)


def sqlite_checkpointer(db_path: str) -> PydanticSqliteSaver:
    """File-backed saver so a UI refresh / new process can resume a thread."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return PydanticSqliteSaver(conn, serde=SERDE)
