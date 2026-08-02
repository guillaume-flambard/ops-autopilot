"""Unit tests for domain model validation and serialization."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.models import (
    Analysis,
    Assumptions,
    BrandProfile,
    DeepDive,
    Locale,
    ReviewStatus,
    Sector,
    Task,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# Assumptions


def test_assumptions_defaults():
    a = Assumptions(hourly_rate_eur=35)
    assert a.weeks_per_month == 4.33
    assert a.locale == Locale.FR


@pytest.mark.parametrize("bad_rate", [0, -1, -10])
def test_assumptions_rejects_non_positive_rate(bad_rate):
    with pytest.raises(ValidationError):
        Assumptions(hourly_rate_eur=bad_rate)


@pytest.mark.parametrize("bad_weeks", [0, -1])
def test_assumptions_rejects_non_positive_weeks(bad_weeks):
    with pytest.raises(ValidationError):
        Assumptions(hourly_rate_eur=35, weeks_per_month=bad_weeks)


def test_assumptions_accepts_english_locale():
    a = Assumptions(hourly_rate_eur=35, locale="en")
    assert a.locale == Locale.EN


def test_assumptions_rejects_unknown_locale():
    with pytest.raises(ValidationError):
        Assumptions(hourly_rate_eur=35, locale="de")


# Task


def test_task_validation_ranges():
    with pytest.raises(ValidationError):
        Task(name="x", volume_per_week=5, minutes_per_unit=10, repetitiveness=6, automatability=3)
    with pytest.raises(ValidationError):
        Task(name="x", volume_per_week=5, minutes_per_unit=10, repetitiveness=0, automatability=3)
    with pytest.raises(ValidationError):
        Task(name="", volume_per_week=5, minutes_per_unit=10, repetitiveness=3, automatability=3)


def test_task_accepts_zero_volume():
    t = Task(name="x", volume_per_week=0, minutes_per_unit=10, repetitiveness=3, automatability=3)
    assert t.volume_per_week == 0


# BrandProfile


def test_brand_profile_validates_sector():
    with pytest.raises(ValidationError):
        BrandProfile(name="X", sector="Unknown", team_size=5)


def test_brand_profile_sector_enum():
    p = BrandProfile(name="Lumea", sector="D2C", team_size=12)
    assert p.sector == Sector.D2C


def test_brand_profile_round_trip_json():
    p = BrandProfile(
        name="Lumea",
        sector="D2C",
        team_size=12,
        channels=["Instagram", "Shopify"],
        tasks=[Task(name="DM", volume_per_week=350, minutes_per_unit=2, repetitiveness=5, automatability=4)],
    )
    restored = BrandProfile.model_validate(json.loads(p.model_dump_json()))
    assert restored == p


def test_profiles_on_disk_load_as_brand_profiles():
    for name in ("lumea", "saas"):
        with open(REPO_ROOT / "profiles" / f"{name}.json") as f:
            p = BrandProfile(**json.load(f))
        assert p.name
        assert p.team_size >= 1
        assert len(p.tasks) == 4
        assert p.default_assumptions.hourly_rate_eur > 0


# DeepDive


def test_deep_dive_defaults():
    d = DeepDive(task_name="DM")
    assert d.effort_weeks == 2
    assert d.degraded is False
    assert d.substeps == []


def test_deep_dive_rejects_absurd_effort():
    with pytest.raises(ValidationError):
        DeepDive(task_name="DM", effort_weeks=30)


# Analysis


def test_analysis_default_status_pending():
    a = Analysis(brand=BrandProfile(name="Lumea", sector="D2C", team_size=12), assumptions=Assumptions(hourly_rate_eur=35))
    assert a.review_status == ReviewStatus.PENDING
    assert a.id is None


def test_analysis_round_trip_serialization():
    a = Analysis(
        brand=BrandProfile(name="Lumea", sector="D2C", team_size=12),
        assumptions=Assumptions(hourly_rate_eur=35),
        review_status=ReviewStatus.APPROVED,
        report="Résumé",
    )
    restored = Analysis.model_validate(json.loads(a.model_dump_json()))
    assert restored.review_status == ReviewStatus.APPROVED
    assert restored.report == "Résumé"
