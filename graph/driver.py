"""Shared streaming driver for the analysis graph.

Both the CLI and the Streamlit UI drive the graph through this function so
their event timelines and interrupt handling stay identical.
"""

from __future__ import annotations


def drive(app, config: dict, payload):
    """Stream one graph run until it halts.

    Returns ``(final, events, interrupted)`` where ``events`` is a list of
    ``(node, message)`` timeline entries and ``interrupted`` is the
    ``human_review`` interrupt payload, or ``None`` when the run ended.
    """
    final: dict = {}
    events: list[tuple[str, str]] = []
    interrupted = None
    for chunk in app.stream(payload, config=config):
        for key, update in chunk.items():
            if key == "__interrupt__":
                interrupted = update[0].value
            else:
                events.extend((key, event) for event in update.get("events", []))
                final.update(update)
    return final, events, interrupted
