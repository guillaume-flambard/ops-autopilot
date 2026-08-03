"""Hermetic tests for website analysis (fetch + LLM extraction).

No network: httpx transports / monkeypatched fetch stand in for the site and
the Ollama server.
"""

from __future__ import annotations

import httpx
import pytest

from llm.client import MockClient, OllamaClient, _strip_html, fetch_page_text


def _fake_page(payload: bytes) -> httpx.Response:
    return httpx.Response(200, content=payload)


def test_strip_html_removes_tags_and_scripts() -> None:
    raw = "<html><script>var x=1;</script><body><p>Bonjour <b>monde</b></p></body></html>"
    assert _strip_html(raw) == "Bonjour monde"


def test_fetch_page_text_returns_clean_text(monkeypatch: pytest.MonkeyPatch) -> None:
    html = b"<html><body><h1>Shop</h1><p>Nous vendons du the.</p></body></html>"
    monkeypatch.setattr("llm.client.httpx.get", lambda *a, **k: _fake_page(html))
    text = fetch_page_text("https://shop.test")
    assert "Shop" in text
    assert "the" in text


def test_fetch_page_text_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Error:
        status_code = 500

        def raise_for_status(self):
            raise httpx.HTTPStatusError("500", request=None, response=httpx.Response(500))

    monkeypatch.setattr("llm.client.httpx.get", lambda *a, **k: _Error())
    with pytest.raises(httpx.HTTPStatusError):
        fetch_page_text("https://shop.test")


def test_mock_analyze_website_parses_structured_free_text(monkeypatch: pytest.MonkeyPatch) -> None:
    html = b"<p>Email support: ~40/week, 10 min each, highly repetitive.</p>"
    monkeypatch.setattr("llm.client.httpx.get", lambda *a, **k: _fake_page(html))
    profile = MockClient().analyze_website("https://shop.test")
    assert len(profile["tasks"]) == 1
    assert profile["tasks"][0]["name"] == "Email support"


def test_mock_analyze_website_returns_free_text_when_no_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    html = b"<p>Nous vendons du the bio en ligne.</p>"
    monkeypatch.setattr("llm.client.httpx.get", lambda *a, **k: _fake_page(html))
    profile = MockClient().analyze_website("https://shop.test")
    assert profile["tasks"] == []
    assert "the bio" in profile["free_text"]


def _ollama_with_llm_response(payload: str):
    """OllamaClient whose /api/chat returns one canned response."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"message": {"content": payload}})

    client = OllamaClient(transport=httpx.MockTransport(handler))
    client._complete = lambda prompt, timeout=None: payload  # avoid second round-trip
    return client, calls


def test_ollama_analyze_website_extracts_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    html = b"<p>Brand page about skincare.</p>"
    monkeypatch.setattr("llm.client.httpx.get", lambda *a, **k: _fake_page(html))
    llm_json = (
        '{"name": "Glow", "sector": "D2C", "team_size": 20, '
        '"free_text": "Vend du skincare.", '
        '"tasks": [{"name": "Orders", "volume_per_week": 100, "minutes_per_unit": 5, '
        '"repetitiveness": 5, "automatability": 5}]}'
    )
    client, _ = _ollama_with_llm_response(llm_json)
    profile = client.analyze_website("https://glow.test")
    assert profile["name"] == "Glow"
    assert profile["sector"] == "D2C"
    assert profile["team_size"] == 20
    assert len(profile["tasks"]) == 1
    assert profile["tasks"][0]["name"] == "Orders"
    assert profile["tasks"][0]["volume_per_week"] == 100


def test_ollama_analyze_website_ignores_invalid_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    html = b"<p>x</p>"
    monkeypatch.setattr("llm.client.httpx.get", lambda *a, **k: _fake_page(html))
    llm_json = (
        '{"name": "X", "sector": "Unknown", "team_size": 3, "free_text": "f", '
        '"tasks": [{"name": "ok", "volume_per_week": 5, "minutes_per_unit": 2, '
        '"repetitiveness": 3, "automatability": 3}, {"name": ""}]}'
    )
    client, _ = _ollama_with_llm_response(llm_json)
    profile = client.analyze_website("https://x.test")
    assert profile["sector"] == "Other"  # unknown sector falls back
    assert len(profile["tasks"]) == 1  # empty-name task dropped
    assert profile["tasks"][0]["name"] == "ok"
