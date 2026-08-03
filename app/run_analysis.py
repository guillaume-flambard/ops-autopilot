"""Run-analysis use case: shared orchestration for the CLI and the Streamlit UI.

Construction-order step 7: extract the graph-driving logic out of the
entrypoints so both run the exact same code path (spec architecture, section 3).

Presentation stays in the entrypoints (argparse prompts, session state,
rendering); building the runtime, streaming the graph and resuming at the
human-review interrupt live here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from langgraph.types import Command

from domain.models import Assumptions, BrandProfile
from graph.build import build_graph
from graph.checkpointer import sqlite_checkpointer
from graph.driver import drive
from llm.client import get_client


@dataclass
class Runtime:
    """A compiled graph plus the LLM client it was built with."""

    app: object
    llm_name: str


@dataclass
class RunResult:
    """Outcome of a single graph stream until it halts."""

    final: dict
    events: list[tuple[str, str]]
    interrupted: dict | None
    thread_id: str
    config: dict


def build_runtime(
    provider: str = "mock",
    api_key: str = "",
    model: str = "llama-3.3-70b-versatile",
    checkpoint_db: str = "ops_autopilot_checkpoints.db",
) -> Runtime:
    """Build the graph with the right LLM clients.

    ``crew_llm`` is only wired when a Groq key is present; otherwise the
    deep-dive falls back to the deterministic degraded template.
    """
    llm = get_client(llm_provider=provider, api_key=api_key or "", model=model)
    crew_llm = None
    if provider == "groq" and api_key:
        from crewai import LLM

        crew_llm = LLM(model=f"groq/{model}", api_key=api_key)
    app = build_graph(llm=llm, crew_llm=crew_llm, checkpointer=sqlite_checkpointer(checkpoint_db))
    return Runtime(app=app, llm_name=llm.name)


def run_analysis(
    brand: BrandProfile,
    assumptions: Assumptions,
    runtime: Runtime,
    thread_id: str | None = None,
) -> RunResult:
    """Stream a full analysis until it halts (human review or final report)."""
    if thread_id is None:
        thread_id = f"run-{int(time.time() * 1000)}"
    config = {"configurable": {"thread_id": thread_id}}
    final, events, interrupted = drive(runtime.app, config, {"brand": brand, "assumptions": assumptions})
    return RunResult(final=final, events=events, interrupted=interrupted, thread_id=thread_id, config=config)


def resume_review(
    runtime: Runtime,
    config: dict,
    action: str,
    assumptions: Assumptions | None = None,
) -> RunResult:
    """Resume a paused run at the human-review interrupt.

    ``action`` is ``approve``, ``edit`` or ``reject``. For ``edit``, pass the
    revised ``assumptions`` so the graph re-scores before continuing.
    """
    if assumptions is not None:
        runtime.app.update_state(config, {"assumptions": assumptions})
    final, events, interrupted = drive(runtime.app, config, Command(resume=action))
    thread_id = config["configurable"]["thread_id"]
    return RunResult(final=final, events=events, interrupted=interrupted, thread_id=thread_id, config=config)
