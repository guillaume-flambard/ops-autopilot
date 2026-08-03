"""Preset brand profiles (data in ``profiles/*.json``)."""

from __future__ import annotations

import json
from pathlib import Path

from domain.models import BrandProfile

PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"


def load_preset(name: str) -> BrandProfile:
    with open(PROFILES_DIR / f"{name}.json") as f:
        return BrandProfile(**json.load(f))
