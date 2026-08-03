"""Ops Autopilot - Streamlit UI (construction-order step 6).

Thin layer over the LangGraph: login -> input form -> stream to the human
review interrupt -> Approve / Edit / Reject -> final report, with analyses
persisted to SQLite and a history page.

Run:
    streamlit run ui/app.py
"""

from __future__ import annotations

import time
from pathlib import Path

import streamlit as st

from app.list_history import list_history
from app.presets import load_preset
from app.run_analysis import build_runtime, resume_review, run_analysis
from domain.models import Assumptions, BrandProfile, Locale, Sector
from db.repo import (
    authenticate,
    checkpoint_db_path,
    create_analysis,
    create_user,
    init_db,
    user_to_dict,
)

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_DB = checkpoint_db_path()

T = {
    "fr": {
        "login_title": "Connexion",
        "login_subtitle": "Connectez-vous ou creez un compte",
        "email": "Email",
        "password": "Mot de passe",
        "login_btn": "Se connecter",
        "register_btn": "Creer un compte",
        "login_failed": "Email ou mot de passe incorrect.",
        "register_exists": "Cet email est deja enregistre.",
        "nav": "Navigation",
        "nav_analyse": "Nouvelle analyse",
        "nav_history": "Historique",
        "logout": "Se deconnecter",
        "brand": "1. Marque",
        "source": "Source",
        "preset": "Preset",
        "custom": "Personnalisee",
        "name": "Nom",
        "sector": "Secteur",
        "team_size": "Equipe (personnes)",
        "free_text": "Texte libre",
        "assumptions": "2. Hypotheses",
        "hourly_rate": "Taux horaire (EUR)",
        "weeks_per_month": "Semaines / mois",
        "llm": "3. LLM",
        "provider": "Fournisseur",
        "api_key": "Cle API Groq",
        "model": "Modele Groq",
        "launch": "Lancer l'analyse",
        "review": "Revue humaine",
        "scored": "Taches notees (ROI)",
        "rank": "Rang",
        "task": "Tache",
        "hours": "h/mois",
        "eur": "EUR/mois",
        "score": "Score",
        "dives": "Plans pilotes (top 3)",
        "degraded": "estimation degradee",
        "approve": "Approuver",
        "edit": "Modifier",
        "reject": "Rejeter",
        "edit_hint": "Modifier le taux horaire puis re-scorer",
        "new_rate": "Nouveau taux horaire (EUR)",
        "rescore": "Re-scorer avec ce taux",
        "steps": "Etapes",
        "report": "Rapport final",
        "rejected": "Analyse rejetee, aucun rapport genere.",
        "new_analysis": "Nouvelle analyse",
        "history_choice": "Analyse",
        "history_empty": "Aucune analyse enregistree pour ce compte.",
        "history_no_report": "Analyse rejetee : aucun rapport.",
    },
    "en": {
        "login_title": "Login",
        "login_subtitle": "Sign in or create an account",
        "email": "Email",
        "password": "Password",
        "login_btn": "Sign in",
        "register_btn": "Create account",
        "login_failed": "Wrong email or password.",
        "register_exists": "This email is already registered.",
        "nav": "Navigation",
        "nav_analyse": "New analysis",
        "nav_history": "History",
        "logout": "Sign out",
        "brand": "1. Brand",
        "source": "Source",
        "preset": "Preset",
        "custom": "Custom",
        "name": "Name",
        "sector": "Sector",
        "team_size": "Team size",
        "free_text": "Free text",
        "assumptions": "2. Assumptions",
        "hourly_rate": "Hourly rate (EUR)",
        "weeks_per_month": "Weeks / month",
        "llm": "3. LLM",
        "provider": "Provider",
        "api_key": "Groq API key",
        "model": "Groq model",
        "launch": "Run analysis",
        "review": "Human review",
        "scored": "Scored tasks (ROI)",
        "rank": "Rank",
        "task": "Task",
        "hours": "h/month",
        "eur": "EUR/month",
        "score": "Score",
        "dives": "Pilot plans (top 3)",
        "degraded": "degraded estimate",
        "approve": "Approve",
        "edit": "Edit",
        "reject": "Reject",
        "edit_hint": "Change the hourly rate, then re-score",
        "new_rate": "New hourly rate (EUR)",
        "rescore": "Re-score with this rate",
        "steps": "Steps",
        "report": "Final report",
        "rejected": "Analysis rejected, no report generated.",
        "new_analysis": "New analysis",
        "history_choice": "Analysis",
        "history_empty": "No saved analysis for this account.",
        "history_no_report": "Rejected analysis: no report.",
    },
}


def _build(provider: str, api_key: str, model: str):
    return build_runtime(provider=provider, api_key=api_key or "", model=model, checkpoint_db=CHECKPOINT_DB)


def _launch(brand: BrandProfile, assumptions: Assumptions, provider: str, api_key: str, model: str) -> None:
    runtime = _build(provider, api_key, model)
    thread_id = f"ui-{int(time.time() * 1000)}"
    try:
        result = run_analysis(brand=brand, assumptions=assumptions, runtime=runtime, thread_id=thread_id)
    except Exception as exc:
        st.session_state["error"] = str(exc)
        return
    final, events, interrupted = result.final, result.events, result.interrupted
    st.session_state.update(
        {
            "status": "review" if interrupted is not None else ("done" if final.get("report") else "rejected"),
            "thread_id": thread_id,
            "config": result.config,
            "events": events,
            "interrupted": interrupted,
            "final": final,
            "report": final.get("report"),
            "brand_name": brand.name,
            "provider": provider,
            "api_key": api_key,
            "model": model,
            "runtime": runtime,
            "error": None,
            "persisted_id": None,
        }
    )


def _resume(action: str, rate: float | None = None, locale: str | None = None) -> None:
    runtime = st.session_state.get("runtime")
    if runtime is None:
        runtime = _build(
            st.session_state.get("provider", "mock"),
            st.session_state.get("api_key", ""),
            st.session_state.get("model", "llama-3.3-70b-versatile"),
        )
        st.session_state["runtime"] = runtime
    config = st.session_state["config"]
    edit_assumptions = None
    if rate is not None:
        current = st.session_state["interrupted"]["assumptions"]
        edit_assumptions = Assumptions(
            hourly_rate_eur=rate,
            weeks_per_month=current["weeks_per_month"],
            locale=Locale(locale or current["locale"]),
        )
    result = resume_review(runtime, config, action, assumptions=edit_assumptions)
    final, events, interrupted = result.final, result.events, result.interrupted
    st.session_state["events"].extend(events)
    st.session_state["final"].update(final)
    st.session_state["interrupted"] = interrupted
    if interrupted is not None:
        st.session_state["status"] = "review"
        st.session_state["persisted_id"] = None
    elif final.get("action") == "reject":
        st.session_state["status"] = "rejected"
        st.session_state["report"] = None
    elif final.get("report"):
        st.session_state["status"] = "done"
        st.session_state["report"] = final["report"]


def _persist_analysis() -> None:
    status = st.session_state.get("status")
    mapping = {"done": "approved", "rejected": "rejected"}
    if status not in mapping or st.session_state.get("persisted_id"):
        return
    final = st.session_state.get("final", {})
    assumptions = final.get("assumptions")
    result = {
        "scored_tasks": [s.model_dump(mode="json") for s in final.get("scored_tasks", [])],
        "deep_dives": [d.model_dump(mode="json") for d in final.get("deep_dives", [])],
        "brand": final["brand"].model_dump(mode="json") if final.get("brand") else {},
    }
    st.session_state["persisted_id"] = create_analysis(
        user_id=st.session_state["user"]["id"],
        brand_name=st.session_state["brand_name"],
        review_status=mapping[status],
        assumptions=assumptions.model_dump(mode="json") if assumptions else {},
        result=result,
        report=st.session_state.get("report"),
    )


def _render_timeline(labels: dict) -> None:
    with st.expander(labels["steps"], expanded=False):
        for node, msg in st.session_state["events"]:
            st.markdown(f"- **{node}**: {msg}")


def _render_review(labels: dict) -> None:
    payload = st.session_state["interrupted"]
    st.subheader(f"{labels['review']} - {st.session_state['brand_name']}")
    _render_timeline(labels)

    st.markdown(f"#### {labels['scored']}")
    rows = [
        {
            labels["rank"]: r["rank"],
            labels["task"]: r["task"],
            labels["hours"]: r["hours_per_month"],
            labels["eur"]: r["eur_per_month"],
            labels["score"]: r["priority_score"],
        }
        for r in payload["scored_tasks"]
    ]
    st.dataframe(rows, hide_index=True, width="stretch")

    st.markdown(f"#### {labels['dives']}")
    for dive in payload["deep_dives"]:
        badge = f" ⚠️ {labels['degraded']}" if dive["degraded"] else ""
        with st.expander(f"{dive['task_name']} -> {dive['proposed_tool']}{badge}"):
            st.write(f"Effort: {dive['effort_weeks']} semaines")

    assumptions = payload["assumptions"]
    st.caption(
        f"{assumptions['hourly_rate_eur']:.0f} EUR/h - {assumptions['weeks_per_month']} semaines/mois - "
        f"locale {assumptions['locale']}"
    )

    col1, col2, col3 = st.columns(3)
    if col1.button(labels["approve"], type="primary", width="stretch"):
        _resume("approve")
    if col2.button(labels["edit"], width="stretch"):
        st.session_state["edit_open"] = not st.session_state.get("edit_open", False)
    if col3.button(labels["reject"], width="stretch"):
        _resume("reject")

    if st.session_state.get("edit_open"):
        with st.expander(labels["edit_hint"], expanded=True):
            current_rate = payload["assumptions"]["hourly_rate_eur"]
            new_rate = st.number_input(labels["new_rate"], min_value=1.0, value=float(current_rate))
            if st.button(labels["rescore"]):
                _resume("edit", rate=new_rate, locale=payload["assumptions"]["locale"])


def _render_done(labels: dict) -> None:
    st.subheader(f"{labels['report']} - {st.session_state['brand_name']}")
    _render_timeline(labels)
    st.markdown(st.session_state["report"] or "")
    if st.button(labels["new_analysis"]):
        for key in ("status", "interrupted", "report", "final", "persisted_id"):
            st.session_state.pop(key, None)


def _render_rejected(labels: dict) -> None:
    st.subheader(f"{labels['rejected']} - {st.session_state['brand_name']}")
    _render_timeline(labels)
    if st.button(labels["new_analysis"]):
        for key in ("status", "interrupted", "report", "final", "persisted_id"):
            st.session_state.pop(key, None)


def _render_history(labels: dict) -> None:
    st.subheader(labels["nav_history"])
    rows = list_history(st.session_state["user"]["id"])
    if not rows:
        st.info(labels["history_empty"])
        return
    options = {
        f"#{r['id']} - {r['brand_name']} ({r['review_status']}, {str(r['created_at'])[:16]})": r for r in rows
    }
    choice = st.selectbox(labels["history_choice"], list(options))
    row = options[choice]
    if row.get("report"):
        st.markdown(row["report"])
    else:
        st.warning(labels["history_no_report"])


def _render_login(labels: dict) -> None:
    st.subheader(labels["login_subtitle"])
    email = st.text_input(labels["email"])
    password = st.text_input(labels["password"], type="password")
    col1, col2 = st.columns(2)
    if col1.button(labels["login_btn"], type="primary"):
        user = authenticate(email, password)
        if user is not None:
            st.session_state["user"] = user_to_dict(user)
            st.session_state["locale"] = labels["_key"]
            st.rerun()
        else:
            st.error(labels["login_failed"])
    if col2.button(labels["register_btn"]):
        try:
            user = create_user(email, password)
        except ValueError:
            st.error(labels["register_exists"])
            return
        st.session_state["user"] = user_to_dict(user)
        st.session_state["locale"] = labels["_key"]
        st.rerun()


def _render_analysis(labels: dict) -> None:
    with st.sidebar.form("input_form"):
        st.markdown(f"**{labels['brand']}**")
        source = st.radio(labels["source"], [labels["preset"], labels["custom"]], horizontal=True)
        preset = "lumea"
        custom_name = "Acme"
        sector = Sector.D2C.value
        team_size = 10
        free_text = ""
        if source == labels["preset"]:
            preset = st.selectbox("Preset", ["lumea", "saas"])
        else:
            custom_name = st.text_input(labels["name"], value="Acme")
            sector = st.selectbox(labels["sector"], [s.value for s in Sector])
            team_size = st.number_input(labels["team_size"], min_value=1, value=10)
            free_text = st.text_area(
                labels["free_text"],
                value="Instagram DMs: ~50/day, 2 min each, highly repetitive.",
            )

        st.markdown(f"**{labels['assumptions']}**")
        hourly_rate = st.number_input(labels["hourly_rate"], min_value=1.0, value=40.0)
        weeks_per_month = st.number_input(labels["weeks_per_month"], min_value=1.0, max_value=6.0, value=4.33)

        st.markdown(f"**{labels['llm']}**")
        provider = st.selectbox(labels["provider"], ["mock", "groq"])
        api_key = ""
        model = "llama-3.3-70b-versatile"
        if provider == "groq":
            api_key = st.text_input(labels["api_key"], type="password")
            model = st.text_input(labels["model"], value=model)

        submitted = st.form_submit_button(labels["launch"], type="primary")

    if submitted:
        if source == labels["preset"]:
            brand = load_preset(preset)
        else:
            brand = BrandProfile(
                name=custom_name,
                sector=Sector(sector),
                team_size=team_size,
                channels=[],
                free_text=free_text,
            )
        assumptions = Assumptions(
            hourly_rate_eur=hourly_rate,
            weeks_per_month=weeks_per_month,
            locale=Locale(st.session_state.get("locale", "fr")),
        )
        _launch(brand, assumptions, provider, api_key, model)

    status = st.session_state.get("status")
    if status == "review":
        _render_review(labels)
    elif status == "done":
        _render_done(labels)
    elif status == "rejected":
        _render_rejected(labels)

    _persist_analysis()


def main() -> None:
    st.set_page_config(page_title="Ops Autopilot", layout="wide")
    st.title("Ops Autopilot")

    init_db()

    if st.session_state.get("error"):
        st.error(st.session_state["error"])

    if "user" not in st.session_state:
        lang = st.selectbox("Langue / Language", ["fr", "en"])
        labels = T[lang]
        labels = {**labels, "_key": lang}
        _render_login(labels)
        if "user" not in st.session_state:
            return

    locale_key = st.session_state.get("locale", "fr")
    labels = T[locale_key]

    with st.sidebar:
        st.write(f"👤 {st.session_state['user']['email']}")
        page = st.radio(labels["nav"], [labels["nav_analyse"], labels["nav_history"]])
        if st.button(labels["logout"]):
            for key in ("user", "status", "interrupted", "report", "final", "persisted_id", "error"):
                st.session_state.pop(key, None)
            st.rerun()

    if page == labels["nav_history"]:
        _render_history(labels)
    else:
        _render_analysis(labels)


main()
