"""Headless smoke tests for the Streamlit UI (construction-order steps 5-6).

These run the app through Streamlit's AppTest harness with the mock LLM, so
they are fully offline and deterministic. A module-level temp SQLite DB is
used.

Strategy: the analysis-flow tests SEED the session state directly (user +
full graph state) instead of clicking through login. Auth tests do at most ONE
login/app transition per test and then stop: `st.rerun()` merges the
pre-rerun widget tree into AppTest's tree, so a second `.run()` after a
transition raises `KeyError` on the phantom pre-rerun widgets.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from db.repo import create_user, get_user_by_email, init_db, user_to_dict

_TMP = tempfile.mkdtemp(prefix="oa-ui-test-")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMP, "test.db")
# Keep the UI hermetic: never launch real Groq calls during tests, even if a
# local .env sets a live key / provider.
os.environ["LLM_PROVIDER"] = "mock"
os.environ["GROQ_API_KEY"] = ""
os.environ["GROQ_MODEL"] = "llama-3.3-70b-versatile"
init_db()
try:
    _SEED_USER = user_to_dict(create_user("seeded@example.com", "pw"))
except ValueError:
    _SEED_USER = user_to_dict(get_user_by_email("seeded@example.com"))

APP = str(Path(__file__).resolve().parents[2] / "ui" / "app.py")
PASSWORD = "s3cret!x"


def _unique_email() -> str:
    return f"user{uuid.uuid4().hex[:10]}@example.com"


def _button(at: AppTest, label: str):
    for button in at.button:
        if button.label == label:
            return button
    raise AssertionError(f"button '{label}' not found; got {[b.label for b in at.button]}")


def _text_input(at: AppTest, label: str):
    for field in at.text_input:
        if field.label == label:
            return field
    raise AssertionError(f"text_input '{label}' not found; got {[f.label for f in at.text_input]}")


def _radio(at: AppTest, label: str):
    for field in at.radio:
        if field.label == label:
            return field
    raise AssertionError(f"radio '{label}' not found; got {[f.label for f in at.radio]}")


def _selectbox(at: AppTest, label: str):
    for field in at.selectbox:
        if field.label == label:
            return field
    raise AssertionError(f"selectbox '{label}' not found; got {[f.label for f in at.selectbox]}")


def _number_input(at: AppTest, label: str):
    for field in at.number_input:
        if field.label == label:
            return field
    raise AssertionError(f"number_input '{label}' not found; got {[f.label for f in at.number_input]}")


def _ss(at: AppTest, key: str, default=None):
    try:
        return at.session_state[key]
    except (KeyError, AttributeError):
        return default


@pytest.fixture()
def at() -> AppTest:
    app = AppTest.from_file(APP, default_timeout=15)
    app.session_state["user"] = dict(_SEED_USER)
    app.session_state["locale"] = "fr"
    app.run()
    assert not app.exception, app.exception
    return app


@pytest.fixture()
def login_at() -> AppTest:
    app = AppTest.from_file(APP, default_timeout=15)
    app.run()
    assert not app.exception, app.exception
    return app


# --- login / logout -------------------------------------------------------


def test_app_loads_to_login(login_at: AppTest) -> None:
    assert login_at.title[0].value == "Ops Autopilot"
    assert "user" not in login_at.session_state


def test_register_creates_account(login_at: AppTest) -> None:
    email = _unique_email()
    _text_input(login_at, "Email").set_value(email)
    _text_input(login_at, "Mot de passe").set_value(PASSWORD)
    _button(login_at, "Creer un compte").click().run()
    assert not login_at.exception, login_at.exception
    assert login_at.session_state["user"]["email"] == email


def test_login_rejects_wrong_password(login_at: AppTest) -> None:
    _text_input(login_at, "Email").set_value(_SEED_USER["email"])
    _text_input(login_at, "Mot de passe").set_value("wrong-pw")
    _button(login_at, "Se connecter").click().run()
    assert not login_at.exception, login_at.exception
    assert "user" not in login_at.session_state
    assert login_at.error, "failed login must surface an error"


def test_logout_returns_to_login(at: AppTest) -> None:
    _button(at, "Se deconnecter").click().run()
    assert not at.exception, at.exception
    assert "user" not in at.session_state
    assert at.selectbox[0].label == "Langue / Language"


# --- analysis flow (seeded user) ------------------------------------------


def test_preset_launch_reaches_review(at: AppTest) -> None:
    _button(at, "Lancer l'analyse").click().run()
    assert not at.exception, at.exception
    assert at.session_state["status"] == "review"
    payload = at.session_state["interrupted"]
    assert payload["scored_tasks"], "review payload must include scored tasks"
    assert payload["deep_dives"], "review payload must include deep dives"
    assert len(at.dataframe) >= 1


def test_approve_produces_report_and_persists(at: AppTest) -> None:
    _button(at, "Lancer l'analyse").click().run()
    _button(at, "Approuver").click().run()
    assert not at.exception, at.exception
    assert at.session_state["status"] == "done"
    assert at.session_state["report"]
    assert _ss(at, "persisted_id"), "approved analysis must be persisted"


def test_reject_ends_without_report_but_persists(at: AppTest) -> None:
    _button(at, "Lancer l'analyse").click().run()
    _button(at, "Rejeter").click().run()
    assert not at.exception, at.exception
    assert at.session_state["status"] == "rejected"
    assert not _ss(at, "report")
    assert _ss(at, "persisted_id"), "rejected analysis must be persisted"


def test_custom_free_text_runs(at: AppTest) -> None:
    _radio(at, "Source").set_value("Personnalisee")
    at.run()
    _button(at, "Lancer l'analyse").click().run()
    assert not at.exception, at.exception
    assert at.session_state["status"] == "review"
    assert at.session_state["brand_name"] == "Acme"


def test_edit_rescores_with_new_rate(at: AppTest) -> None:
    _button(at, "Lancer l'analyse").click().run()
    before = at.session_state["interrupted"]["scored_tasks"]
    _button(at, "Modifier").click().run()
    _number_input(at, "Nouveau taux horaire (EUR)").set_value(100.0)
    at.run()
    _button(at, "Re-scorer avec ce taux").click().run()
    assert not at.exception, at.exception
    assert at.session_state["status"] == "review"
    after = at.session_state["interrupted"]["scored_tasks"]
    assert after[0]["eur_per_month"] > before[0]["eur_per_month"], "higher rate must raise EUR/month"


def test_custom_source_with_groq_renders_api_key_field(at: AppTest) -> None:
    _radio(at, "Source").set_value("Personnalisee")
    at.run()
    _selectbox(at, "Fournisseur").set_value("groq")
    at.run()
    labels = [t.label for t in at.text_input]
    assert "Cle API Groq" in labels


def test_history_page_shows_persisted_analyses(at: AppTest) -> None:
    _button(at, "Lancer l'analyse").click().run()
    _button(at, "Approuver").click().run()
    assert at.session_state["status"] == "done"
    _radio(at, "Navigation").set_value("Historique")
    at.run()
    assert not at.exception, at.exception
    options = [sb.options for sb in at.selectbox if sb.label == "Analyse"]
    assert options, "history page must show the analysis selector"
    assert any("Lumea" in " ".join(opt) for opt in options)
    assert any("approved" in " ".join(opt) for opt in options)
