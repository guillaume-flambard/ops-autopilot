"""Unit tests for the deterministic free-text parser (MockClient fallback)."""

from llm.client import MockClient


def test_parse_day_volume_converts_to_week():
    tasks = MockClient().map_tasks_from_text("Instagram DM responses: ~50/day, 2 min each, highly repetitive.")
    assert len(tasks) == 1
    t = tasks[0]
    assert t.name == "Instagram DM responses"
    assert t.volume_per_week == 350
    assert t.minutes_per_unit == 2
    assert t.repetitiveness == 5
    assert t.automatability == 4


def test_parse_week_volume():
    tasks = MockClient().map_tasks_from_text("Onboarding calls: 10/week, 30 min each, medium repetitive.")
    assert tasks[0].volume_per_week == 10
    assert tasks[0].minutes_per_unit == 30
    assert tasks[0].repetitiveness == 3


def test_parse_weekly_and_hours():
    tasks = MockClient().map_tasks_from_text("Documentation updates: weekly, 2 hours, low repetitive.")
    t = tasks[0]
    assert t.volume_per_week == 1
    assert t.minutes_per_unit == 120
    assert t.repetitiveness == 1


def test_parse_multiple_sentences():
    text = (
        "Instagram DM responses: ~50/day, 2 min each, highly repetitive. "
        "Shopify order processing: ~100/day, 3 min each, medium repetitive. "
        "Product photography planning: weekly, 60 min, low repetitive."
    )
    tasks = MockClient().map_tasks_from_text(text)
    assert [t.name for t in tasks] == [
        "Instagram DM responses",
        "Shopify order processing",
        "Product photography planning",
    ]


def test_parse_skips_lines_without_task_name():
    tasks = MockClient().map_tasks_from_text("no colon here, nothing structured")
    assert tasks == []
