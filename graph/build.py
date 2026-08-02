"""Assemble and compile the analysis graph."""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from llm.client import LLMClient, get_client
from crew.run_deep_dive import run_deep_dive
from graph.checkpointer import memory_checkpointer
from graph.edges import REVIEW_ROUTES, route_review
from graph.nodes import check_data, deep_dive, human_review, ingest, map_tasks, report, score
from graph.state import AnalysisState


def build_graph(
    llm: LLMClient | None = None,
    crew_llm=None,
    checkpointer=None,
) -> StateGraph:
    """Compile the LangGraph.

    ``llm`` drives map_tasks + report (an ``LLMClient``). ``crew_llm`` is a
    CrewAI-compatible model for the deep-dive; ``None`` uses the degraded
    template. ``checkpointer`` enables interrupt/resume; defaults to an
    in-memory saver so human_review works out of the box.
    """
    llm = llm or get_client()
    deep_dive_runner = partial(run_deep_dive, llm=crew_llm)

    graph = StateGraph(AnalysisState)
    graph.add_node("ingest", ingest)
    graph.add_node("map_tasks", partial(map_tasks, llm=llm))
    graph.add_node("score", score)
    graph.add_node("check_data", check_data)
    graph.add_node("deep_dive", partial(deep_dive, runner=deep_dive_runner))
    graph.add_node("human_review", human_review)
    graph.add_node("generate_report", partial(report, llm=llm))

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "map_tasks")
    graph.add_edge("map_tasks", "score")
    graph.add_edge("score", "check_data")
    graph.add_edge("check_data", "deep_dive")
    graph.add_edge("deep_dive", "human_review")
    graph.add_conditional_edges("human_review", route_review, REVIEW_ROUTES)
    graph.add_edge("generate_report", END)

    return graph.compile(checkpointer=checkpointer or memory_checkpointer())
