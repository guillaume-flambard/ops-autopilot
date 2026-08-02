"""Ops Autopilot - Streamlit UI (construction-order step 5).

Thin layer over the LangGraph: input form -> stream to the human review
interrupt -> Approve / Edit / Reject -> final report. No auth or persistent
history yet (step 6 adds DB repositories).

Run:
    streamlit run ui/app.py
"""

from __future__ import annotations

import time
from pathlib import Path

import streamlit as st
from langgraph.types import Command

from domain.models import Assumptions, BrandProfile, Locale, Sector
from graph.build import build_graph
from graph.checkpointer import sqlite_checkpointer
from graph.driver import drive
from llm.client import get_client

ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = ROOT / "profiles"
CHECKPOINT_DB = str(ROOT / "ops_autopilot_checkpoints.db")

T = {
    "fr": {
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
        "language": "Langue",
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
        "history": "Historique (session)",
        "totals": "Totaux",
    },
    "en": {
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
        "language": "Language",
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
        "history": "History (session)",
        "totals": "Totals",
    },
}


def load_preset(name: str) -> BrandProfile:
    import json

    with open(PROFILES_DIR / f"{name}.json") as f:
        return BrandProfile(**json.load(f))


def _build(provider: str, api_key: str, model: str):
    llm = get_client(llm_provider=provider, api_key=api_key or "", model=model)
    crew_llm = None
    if provider == "groq" and api_key:
        from crewai import LLM

        crew_llm = LLM(model=f"groq/{model}", api_key=api_key)
    return build_graph(
        llm=llm,
        crew_llm=crew_llm,
        checkpointer=sqlite_checkpointer(CHECKPOINT_DB),
    )


def _launch(brand: BrandProfile, assumptions: Assumptions, provider: str, api_key: str, model: str) -> None:
    app = _build(provider, api_key, model)
    thread_id = f"ui-{int(time.time() * 1000)}"
    config = {"configurable": {"thread_id": thread_id}}
    try:
        final, events, interrupted = drive(app, config, {"brand": brand, "assumptions": assumptions})
    except Exception as exc:
        st.session_state["error"] = str(exc)
        return
    st.session_state.update(
        {
            "status": "review" if interrupted is not None else ("done" if final.get("report") else "rejected"),
            "thread_id": thread_id,
            "config": config,
            "events": events,
            "interrupted": interrupted,
            "final": final,
            "report": final.get("report"),
            "brand_name": brand.name,
            "provider": provider,
            "api_key": api_key,
            "model": model,
            "error": None,
        }
    )


def _resume(action: str, rate: float | None = None, locale: str | None = None) -> None:
    app = _build(
        st.session_state.get("provider", "mock"),
        st.session_state.get("api_key", ""),
        st.session_state.get("model", "llama-3.3-70b-versatile"),
    )
    config = st.session_state["config"]
    if rate is not None:
        current = st.session_state["interrupted"]["assumptions"]
        new = Assumptions(
            hourly_rate_eur=rate,
            weeks_per_month=current["weeks_per_month"],
            locale=Locale(locale or current["locale"]),
        )
        app.update_state(config, {"assumptions": new})
    final, events, interrupted = drive(app, config, Command(resume=action))
    st.session_state["events"].extend(events)
    st.session_state["final"].update(final)
    st.session_state["interrupted"] = interrupted
    if interrupted is not None:
        st.session_state["status"] = "review"
    elif final.get("action") == "reject":
        st.session_state["status"] = "rejected"
        st.session_state["report"] = None
    elif final.get("report"):
        st.session_state["status"] = "done"
        st.session_state["report"] = final["report"]
    _append_history()


def _append_history() -> None:
    status = st.session_state["status"]
    if status not in ("done", "rejected"):
        return
    history = st.session_state.get("history", [])
    history.append(
        {
            "brand": st.session_state["brand_name"],
            "status": status,
            "when": time.strftime("%H:%M:%S"),
        }
    )
    st.session_state["history"] = history


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
        for key in ("status", "interrupted", "report", "final"):
            st.session_state.pop(key, None)


def _render_rejected(labels: dict) -> None:
    st.subheader(f"{labels['rejected']} - {st.session_state['brand_name']}")
    _render_timeline(labels)
    if st.button(labels["new_analysis"]):
        for key in ("status", "interrupted", "report", "final"):
            st.session_state.pop(key, None)


def main() -> None:
    st.set_page_config(page_title="Ops Autopilot", layout="wide")
    st.title("Ops Autopilot")

    if st.session_state.get("error"):
        st.error(st.session_state["error"])

    with st.sidebar.form("input_form"):
        locale = st.selectbox("Langue / Language", ["fr", "en"])
        labels = T[locale]

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
            locale=Locale(locale),
        )
        _launch(brand, assumptions, provider, api_key, model)

    status = st.session_state.get("status")
    if status == "review":
        _render_review(labels)
    elif status == "done":
        _render_done(labels)
    elif status == "rejected":
        _render_rejected(labels)
    elif "history" in st.session_state:
        history = st.session_state["history"]
        if history:
            with st.expander(labels["history"], expanded=True):
                for h in history:
                    st.write(f"- {h['when']} **{h['brand']}** - {h['status']}")
        else:
            st.info("No analysis run in this session yet.")


main()
