"""Headless smoke tests for the Streamlit UI (construction-order step 5).

These run the app through Streamlit's AppTest harness with the mock LLM, so
they are fully offline and deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[2] / "ui" / "app.py")


@pytest.fixture()
def at() -> AppTest:
    app = AppTest.from_file(APP, default_timeout=15)
    app.run()
    assert not app.exception, app.exception
    return app


def _button(at: AppTest, label: str):
    for button in at.button:
        if button.label == label:
            return button
    raise AssertionError(f"button '{label}' not found; got {[b.label for b in at.button]}")


def _ss(at: AppTest, key: str, default=None):
    try:
        return at.session_state[key]
    except (KeyError, AttributeError):
        return default


def test_app_loads(at: AppTest) -> None:
    assert at.title[0].value == "Ops Autopilot"
    assert _ss(at, "status") is None


def test_preset_launch_reaches_review(at: AppTest) -> None:
    _button(at, "Lancer l'analyse").click().run()
    assert not at.exception, at.exception
    assert at.session_state["status"] == "review"
    payload = at.session_state["interrupted"]
    assert payload["scored_tasks"], "review payload must include scored tasks"
    assert payload["deep_dives"], "review payload must include deep dives"
    assert len(at.dataframe) >= 1


def test_approve_produces_report(at: AppTest) -> None:
    _button(at, "Lancer l'analyse").click().run()
    _button(at, "Approuver").click().run()
    assert not at.exception, at.exception
    assert at.session_state["status"] == "done"
    assert at.session_state["report"]


def test_reject_ends_without_report(at: AppTest) -> None:
    _button(at, "Lancer l'analyse").click().run()
    _button(at, "Rejeter").click().run()
    assert not at.exception, at.exception
    assert at.session_state["status"] == "rejected"
    assert not _ss(at, "report")


def test_custom_free_text_runs(at: AppTest) -> None:
    at.radio[0].set_value("Personnalisee")
    at.run()
    _button(at, "Lancer l'analyse").click().run()
    assert not at.exception, at.exception
    assert at.session_state["status"] == "review"
    assert at.session_state["brand_name"] == "Acme"


def test_edit_rescores_with_new_rate(at: AppTest) -> None:
    _button(at, "Lancer l'analyse").click().run()
    before = at.session_state["interrupted"]["scored_tasks"]
    _button(at, "Modifier").click().run()
    number_inputs = [n for n in at.number_input if n.label == "Nouveau taux horaire (EUR)"]
    assert number_inputs, "edit expander must expose the new-rate input"
    number_inputs[0].set_value(100.0)
    at.run()
    _button(at, "Re-scorer avec ce taux").click().run()
    assert not at.exception, at.exception
    assert at.session_state["status"] == "review"
    after = at.session_state["interrupted"]["scored_tasks"]
    assert after[0]["eur_per_month"] > before[0]["eur_per_month"], "higher rate must raise EUR/month"


def test_custom_source_with_groq_needs_api_key_renders_field(at: AppTest) -> None:
    # switching provider to groq must render the API key + model inputs
    at.radio[0].set_value("Personnalisee")
    at.run()
    provider_selects = at.selectbox
    # find the provider selectbox by label
    for sb in provider_selects:
        if sb.label == "Fournisseur":
            sb.set_value("groq")
            break
    else:
        raise AssertionError("provider selectbox not found")
    at.run()
    labels = [t.label for t in at.text_input]
    assert "Cle API Groq" in labels
