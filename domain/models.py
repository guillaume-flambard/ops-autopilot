"""Pure domain models for Ops Autopilot.

No LangGraph, CrewAI, or Streamlit imports here. These entities are the
single source of truth used by the scoring engine, the graph state, the
database repositories, and the UI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Locale(str, Enum):
    FR = "fr"
    EN = "en"


class Sector(str, Enum):
    D2C = "D2C"
    SAAS = "SaaS"
    AGENCY = "Agency"
    OTHER = "Other"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class Assumptions(BaseModel):
    """Configurable assumptions driving every financial figure.

    No figure in the product is ever a magic number: every euro shown on
    screen is derived from these inputs.
    """

    hourly_rate_eur: float = Field(gt=0, description="Cost of one hour of team time, in EUR")
    weeks_per_month: float = Field(default=4.33, gt=0, description="Working weeks per month")
    locale: Locale = Locale.FR

    def totals(self, scored_tasks: list["ScoredTask"]) -> dict[str, float]:
        """Totals computed for the assumptions panel (hours / EUR / ETP)."""
        total_hours = sum(s.hours_per_month for s in scored_tasks)
        return {
            "total_hours_per_month": total_hours,
            "total_eur_per_month": total_hours * self.hourly_rate_eur,
            "total_etp": total_hours / 151.67,
        }


class Task(BaseModel):
    """A single operation the brand performs, ready to be scored."""

    name: str = Field(min_length=1)
    volume_per_week: float = Field(ge=0, description="Units processed per week")
    minutes_per_unit: float = Field(ge=0, description="Minutes spent per unit")
    repetitiveness: int = Field(ge=1, le=5, description="1=creative/unpredictable, 5=identical every time")
    automatability: int = Field(ge=1, le=5, description="1=needs human judgment, 5=trivially automatable")


class ScoredTask(BaseModel):
    """A task with all derived financial and priority figures baked in."""

    task: Task
    hours_per_month: float
    eur_per_month: float
    etp: float
    priority_score: float
    roi_rank: Optional[int] = Field(default=None, description="1 = highest priority; assigned by the scorer")


class DeepDive(BaseModel):
    """A 2 to 3 week implementation sketch for one high-priority task."""

    task_name: str
    substeps: list[str] = Field(default_factory=list)
    proposed_tool: str = ""
    agent_flow: str = ""
    main_risk: str = ""
    effort_weeks: float = Field(default=2, ge=0.5, le=12)
    pilot_plan: str = ""
    degraded: bool = Field(default=False, description="True when filled from a template because the LLM failed")


class Recommendation(BaseModel):
    """One actionable item surfaced in the final report."""

    task_name: str
    priority_score: float
    eur_per_month: float
    deep_dive: Optional[DeepDive] = None


class BrandProfile(BaseModel):
    """Snapshot of a brand's operations. Either structured tasks or free text."""

    name: str = Field(min_length=1)
    sector: Sector
    team_size: int = Field(ge=1)
    channels: list[str] = Field(default_factory=list)
    notes: str = ""
    tasks: list[Task] = Field(default_factory=list)
    free_text: str = ""
    default_assumptions: Optional[Assumptions] = Field(default=None)


class Analysis(BaseModel):
    """A full analysis run: inputs, scored output, review state, report."""

    id: Optional[int] = None
    user_id: Optional[str] = None
    brand: BrandProfile
    assumptions: Assumptions
    scored_tasks: list[ScoredTask] = Field(default_factory=list)
    deep_dives: list[DeepDive] = Field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.PENDING
    report: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
