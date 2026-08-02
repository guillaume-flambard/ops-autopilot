"""LangGraph state schema for an analysis run."""

from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict

from domain.models import Assumptions, BrandProfile, DeepDive, ScoredTask, Task


class AnalysisState(TypedDict, total=False):
    """Everything flowing through the graph between nodes."""

    brand: BrandProfile
    assumptions: Assumptions
    tasks: list[Task]
    scored_tasks: list[ScoredTask]
    deep_dives: list[DeepDive]
    step: str
    action: str
    report: Optional[str]
    error: Optional[str]
    events: Annotated[list[str], operator.add]
