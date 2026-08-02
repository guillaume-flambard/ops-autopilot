"""LLM client abstraction with retry and a deterministic fallback.

Two implementations:

- ``GroqClient``: real LLM calls (Groq free tier), with retry/backoff on
  rate limits. Used when a Groq API key is configured.
- ``MockClient``: deterministic rule-based parser and canned deep-dive
  templates. Used when no key is set, so the CLI and tests run offline.

The graph never talks to Groq directly; it receives an ``LLMClient`` at
build time, which keeps nodes testable.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Optional

from domain.models import Assumptions, DeepDive, ScoredTask, Task

logger = logging.getLogger(__name__)

REPETITIVENESS_MAP = {
    "high": 5,
    "medium": 3,
    "low": 1,
}
AUTOMATABILITY_MAP = {
    "high": 4,
    "medium": 3,
    "low": 2,
}


def degraded_deep_dive(scored_tasks: list[ScoredTask], assumptions: Assumptions) -> list[DeepDive]:
    """Deterministic fallback used whenever the LLM path fails (offline, rate limit, parse error)."""
    dives = []
    for scored in scored_tasks:
        task = scored.task
        dives.append(
            DeepDive(
                task_name=task.name,
                substeps=[
                    "Cartographier le flux actuel et identifier les goulots d'etranglement",
                    "Prototyper une automatisation sur les cas les plus frequents",
                    "Mesurer le gain de temps sur deux semaines, puis generaliser",
                ],
                proposed_tool="Template degrade (hors ligne)",
                agent_flow="Template degrade (hors ligne)",
                main_risk="L'estimation est une approximation ; a valider par un humain avant tout engagement",
                effort_weeks=2,
                pilot_plan="Pilote de 2 semaines sur le volume le plus haut, puis arbitrage humain",
                degraded=True,
            )
        )
    return dives


class LLMClient:
    """Minimal interface the graph nodes depend on."""

    name = "base"

    def map_tasks_from_text(self, free_text: str, locale: str = "fr") -> list[Task]:
        raise NotImplementedError

    def deep_dive(self, scored_tasks: list[ScoredTask], assumptions: Assumptions) -> list[DeepDive]:
        raise NotImplementedError

    def executive_report(self, scored_tasks: list[ScoredTask], deep_dives: list[DeepDive], assumptions: Assumptions) -> str:
        raise NotImplementedError


class MockClient(LLMClient):
    """Deterministic offline fallback. No network, no key needed."""

    name = "mock"

    def map_tasks_from_text(self, free_text: str, locale: str = "fr") -> list[Task]:
        return _parse_free_text(free_text)

    def deep_dive(self, scored_tasks: list[ScoredTask], assumptions: Assumptions) -> list[DeepDive]:
        return degraded_deep_dive(scored_tasks, assumptions)

    def executive_report(self, scored_tasks: list[ScoredTask], deep_dives: list[DeepDive], assumptions: Assumptions) -> str:
        top = scored_tasks[0] if scored_tasks else None
        lines = [
            "Resume executif (mode degrade, LLM hors ligne)",
            f"Analyse de {len(scored_tasks)} taches, {assumptions.hourly_rate_eur} EUR/heure, {assumptions.weeks_per_month} semaines/mois.",
        ]
        if top:
            lines.append(f"Priorite 1 : {top.task.name} ({top.priority_score:.1f} points, {top.eur_per_month:.0f} EUR/mois).")
        lines.append("Chaque chiffre repose sur des hypotheses modifiables; revue humaine obligatoire avant toute decision.")
        return "\n".join(lines)


class GroqClient(LLMClient):
    """Real LLM calls through Groq, with retry on 429 / 5xx."""

    name = "groq"

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile", max_retries: int = 3):
        from groq import Groq

        self._client = Groq(api_key=api_key)
        self.model = model
        self.max_retries = max_retries

    def map_tasks_from_text(self, free_text: str, locale: str = "fr") -> list[Task]:
        from llm.prompts import MAP_TASKS_PROMPT

        prompt = MAP_TASKS_PROMPT.get(locale, MAP_TASKS_PROMPT["en"]).format(free_text=free_text)
        raw = self._complete(prompt)
        data = json.loads(raw)
        return [Task(**item) for item in data]

    def deep_dive(self, scored_tasks: list[ScoredTask], assumptions: Assumptions) -> list[DeepDive]:
        dives = []
        for scored in scored_tasks:
            raw = self._complete(
                f"Propose un plan pilote 2-3 semaines pour automatiser '{scored.task.name}' "
                f"({scored.eur_per_month:.0f} EUR/mois). Reponds en JSON: substeps, proposed_tool, "
                "agent_flow, main_risk, effort_weeks, pilot_plan."
            )
            try:
                data = json.loads(raw)
                data["task_name"] = scored.task.name
                dives.append(DeepDive(**data))
            except (json.JSONDecodeError, ValueError):
                logger.warning("deep_dive parse failed for %s; using degraded template", scored.task.name)
                dives.append(MockClient().deep_dive([scored], assumptions)[0])
        return dives

    def executive_report(self, scored_tasks: list[ScoredTask], deep_dives: list[DeepDive], assumptions: Assumptions) -> str:
        from llm.prompts import REPORT_EXECUTIVE_PROMPT

        total_hours = sum(s.hours_per_month for s in scored_tasks)
        top = scored_tasks[0] if scored_tasks else None
        prompt = REPORT_EXECUTIVE_PROMPT.get(
            assumptions.locale.value,
            REPORT_EXECUTIVE_PROMPT["en"],
        ).format(
            sector=assumptions.locale.value.upper(),
            total_hours=f"{total_hours:.0f}",
            total_eur=f"{total_hours * assumptions.hourly_rate_eur:.0f}",
            total_etp=f"{total_hours / 151.67:.2f}",
            top_name=top.task.name if top else "n/a",
        )
        return self._complete(prompt)

    def _complete(self, prompt: str, timeout: int = 30) -> str:
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
                return resp.choices[0].message.content or ""
            except Exception as exc:  # 429 and 5xx both surface here in the groq SDK
                last_error = exc
                delay = min(10.0, (1.5**attempt)) * (0.8 + 0.4 * random.random())
                logger.warning("groq retry %d/%d after %s (%.1fs)", attempt + 1, self.max_retries, exc, delay)
                time.sleep(delay)
        raise RuntimeError(f"Groq failed after {self.max_retries} retries: {last_error}")


def get_client(llm_provider: str = "mock", api_key: str = "", model: str = "llama-3.3-70b-versatile") -> LLMClient:
    if llm_provider == "groq" and api_key:
        return GroqClient(api_key=api_key, model=model)
    if llm_provider == "groq":
        logger.warning("LLM provider is groq but no API key set; falling back to mock")
    return MockClient()


# --- deterministic free-text parser (MockClient) -----------------------------


def _parse_free_text(free_text: str) -> list[Task]:
    tasks = []
    for sentence in re.split(r"[.;\n]+", free_text):
        sentence = sentence.strip()
        if not sentence:
            continue
        task = _parse_sentence(sentence)
        if task:
            tasks.append(task)
    return tasks


def _parse_sentence(sentence: str) -> Optional[Task]:
    name_match = re.match(r"^\s*([A-Za-z][^:]{0,80}?)\s*:", sentence)
    if not name_match:
        return None
    name = name_match.group(1).strip().strip("'\"")
    body = sentence[name_match.end():].lower()

    volume = 0
    vol_match = re.search(r"(\d+)\s*/\s*(day|week|month)", body)
    if vol_match:
        n = int(vol_match.group(1))
        unit = vol_match.group(2)
        volume = n * {"day": 7, "week": 1, "month": 1 / 4.33}[unit]
    elif re.search(r"\bweekly\b", body):
        volume = 1

    minutes = 0.0
    min_match = re.search(r"(\d+(?:\.\d+)?)\s*(min(?:ute)?s?|hour(?:s)?)\b", body)
    if min_match:
        value = float(min_match.group(1))
        minutes = value * 60 if min_match.group(2).startswith("hour") else value

    repetitiveness = 3
    rep_match = re.search(r"(highly?\s*repetitive|repetitive|medium\s*repetitive|low\s*repetitive)", body)
    if rep_match:
        token = rep_match.group(1)
        if token.startswith("high"):
            repetitiveness = REPETITIVENESS_MAP["high"]
        elif token.startswith("medium"):
            repetitiveness = REPETITIVENESS_MAP["medium"]
        else:
            repetitiveness = REPETITIVENESS_MAP["low"]

    automatability = 3
    if "highly repetitive" in body or "automatab" in body:
        automatability = 4

    return Task(
        name=name,
        volume_per_week=volume,
        minutes_per_unit=minutes,
        repetitiveness=repetitiveness,
        automatability=automatability,
    )
