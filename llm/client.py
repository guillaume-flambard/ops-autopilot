"""LLM client abstraction with retry and a deterministic fallback.

Three implementations:

- ``GroqClient``: real LLM calls (Groq free tier), with retry/backoff on
  rate limits. Used when a Groq API key is configured.
- ``OllamaClient``: local LLM calls (Ollama server, no quota). Used when the
  Ollama server is reachable and a model is available.
- ``MockClient``: deterministic rule-based parser and canned deep-dive
  templates. Used when no key is set, so the CLI and tests run offline.

The graph never talks to an LLM provider directly; it receives an
``LLMClient`` at build time, which keeps nodes testable.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Optional

import httpx

from domain.models import Assumptions, DeepDive, ScoredTask, Sector, Task

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

    def executive_report(
        self,
        scored_tasks: list[ScoredTask],
        deep_dives: list[DeepDive],
        assumptions: Assumptions,
        sector: str | None = None,
    ) -> str:
        raise NotImplementedError

    def analyze_website(self, url: str, locale: str = "fr") -> dict:
        """Fetch a site and return a structured brand profile.

        Returns a dict compatible with ``BrandProfile``: name, sector,
        team_size, free_text, tasks (list of ``Task`` dicts).
        """
        raise NotImplementedError


class MockClient(LLMClient):
    """Deterministic offline fallback. No network, no key needed."""

    name = "mock"

    def map_tasks_from_text(self, free_text: str, locale: str = "fr") -> list[Task]:
        return _parse_free_text(free_text)

    def analyze_website(self, url: str, locale: str = "fr") -> dict:
        """Fetch the page and derive a brand profile from structured free text.

        Deterministic: no LLM. If the page contains ``task: <vol>/day...``
        lines they are parsed; otherwise the page text becomes free_text.
        """
        try:
            page = fetch_page_text(url)
        except Exception as exc:
            raise ValueError(f"Impossible de charger le site ({exc}).") from exc
        tasks = _parse_free_text(page)
        return {
            "name": url,
            "sector": "Other",
            "team_size": 5,
            "free_text": page,
            "tasks": [t.model_dump() for t in tasks],
        }

    def deep_dive(self, scored_tasks: list[ScoredTask], assumptions: Assumptions) -> list[DeepDive]:
        return degraded_deep_dive(scored_tasks, assumptions)

    def executive_report(
        self,
        scored_tasks: list[ScoredTask],
        deep_dives: list[DeepDive],
        assumptions: Assumptions,
        sector: str | None = None,
    ) -> str:
        top = scored_tasks[0] if scored_tasks else None
        sector = sector or assumptions.locale.value
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
        data = _extract_json(raw, expect_array=True)
        return [Task(**item) for item in data]

    def analyze_website(self, url: str, locale: str = "fr") -> dict:
        return _analyze_website_llm(self, url, locale=locale)

    def deep_dive(self, scored_tasks: list[ScoredTask], assumptions: Assumptions) -> list[DeepDive]:
        dives = []
        for scored in scored_tasks:
            raw = self._complete(
                f"Propose un plan pilote 2-3 semaines pour automatiser '{scored.task.name}' "
                f"({scored.eur_per_month:.0f} EUR/mois). Reponds en JSON: substeps, proposed_tool, "
                "agent_flow, main_risk, effort_weeks, pilot_plan."
            )
            try:
                data = _extract_json(raw, expect_array=False)
                dives.append(DeepDive(**_normalize_deep_dive(data, scored.task.name)))
            except (json.JSONDecodeError, ValueError, TypeError, KeyError):
                logger.warning("deep_dive parse failed for %s; using degraded template", scored.task.name)
                dives.append(MockClient().deep_dive([scored], assumptions)[0])
        return dives

    def executive_report(
        self,
        scored_tasks: list[ScoredTask],
        deep_dives: list[DeepDive],
        assumptions: Assumptions,
        sector: str | None = None,
    ) -> str:
        from llm.prompts import REPORT_EXECUTIVE_PROMPT

        total_hours = sum(s.hours_per_month for s in scored_tasks)
        top = scored_tasks[0] if scored_tasks else None
        prompt = REPORT_EXECUTIVE_PROMPT.get(
            assumptions.locale.value,
            REPORT_EXECUTIVE_PROMPT["en"],
        ).format(
            sector=sector or assumptions.locale.value,
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


class OllamaClient(LLMClient):
    """Local LLM calls through an Ollama server. No API key, no quota."""

    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:3b",
        max_retries: int = 2,
        timeout: float = 60.0,
        transport=None,
    ):
        self._base_url = base_url.rstrip("/")
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        self._client = httpx.Client(transport=transport, timeout=timeout)

    def map_tasks_from_text(self, free_text: str, locale: str = "fr") -> list[Task]:
        from llm.prompts import MAP_TASKS_PROMPT

        prompt = MAP_TASKS_PROMPT.get(locale, MAP_TASKS_PROMPT["en"]).format(free_text=free_text)
        raw = self._complete(prompt)
        data = _extract_json(raw, expect_array=True)
        return [Task(**item) for item in data]

    def analyze_website(self, url: str, locale: str = "fr") -> dict:
        return _analyze_website_llm(self, url, locale=locale)

    def deep_dive(self, scored_tasks: list[ScoredTask], assumptions: Assumptions) -> list[DeepDive]:
        dives = []
        for scored in scored_tasks:
            raw = self._complete(
                f"Propose un plan pilote 2-3 semaines pour automatiser '{scored.task.name}' "
                f"({scored.eur_per_month:.0f} EUR/mois). Reponds en JSON: substeps, proposed_tool, "
                "agent_flow, main_risk, effort_weeks, pilot_plan."
            )
            try:
                data = _extract_json(raw, expect_array=False)
                dives.append(DeepDive(**_normalize_deep_dive(data, scored.task.name)))
            except (json.JSONDecodeError, ValueError, TypeError, KeyError):
                logger.warning("ollama deep_dive parse failed for %s; using degraded template", scored.task.name)
                dives.append(MockClient().deep_dive([scored], assumptions)[0])
        return dives

    def executive_report(
        self,
        scored_tasks: list[ScoredTask],
        deep_dives: list[DeepDive],
        assumptions: Assumptions,
        sector: str | None = None,
    ) -> str:
        from llm.prompts import REPORT_EXECUTIVE_PROMPT

        total_hours = sum(s.hours_per_month for s in scored_tasks)
        top = scored_tasks[0] if scored_tasks else None
        prompt = REPORT_EXECUTIVE_PROMPT.get(
            assumptions.locale.value,
            REPORT_EXECUTIVE_PROMPT["en"],
        ).format(
            sector=sector or assumptions.locale.value,
            total_hours=f"{total_hours:.0f}",
            total_eur=f"{total_hours * assumptions.hourly_rate_eur:.0f}",
            total_etp=f"{total_hours / 151.67:.2f}",
            top_name=top.task.name if top else "n/a",
        )
        return self._complete(prompt)

    def _complete(self, prompt: str, timeout: float | None = None) -> str:
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                resp = self._client.post(
                    f"{self._base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "options": {"temperature": 0.2},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("message", {}).get("content", "") or ""
            except Exception as exc:  # connection refused, 5xx, malformed body
                last_error = exc
                delay = min(5.0, (1.5**attempt)) * (0.8 + 0.4 * random.random())
                logger.warning("ollama retry %d/%d after %s (%.1fs)", attempt + 1, self.max_retries, exc, delay)
                time.sleep(delay)
        raise RuntimeError(f"Ollama failed after {self.max_retries} retries: {last_error}")


def _ollama_reachable(base_url: str, timeout: float = 2.0) -> bool:
    """Light reachability probe for the local Ollama server.

    Called at runtime build time so an offline Ollama selection falls back to
    the deterministic mock client instead of crashing mid-analysis.
    """
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def _strip_html(raw: str, max_chars: int = 6000) -> str:
    """Rough HTML to text: drop tags/scripts/styles, collapse whitespace."""
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip()[:max_chars]


def fetch_page_text(url: str, timeout: float = 15.0, max_chars: int = 6000) -> str:
    """Fetch a page and return readable text (best effort, no JS rendering)."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
    }
    resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    if resp.status_code != 200:
        resp.raise_for_status()  # surface 4xx/5xx for the caller
    return _strip_html(resp.text, max_chars=max_chars)


def fetch_page_markdown(url: str, timeout: float = 40.0, max_chars: int = 6000) -> str:
    """Fetch a page through the Jina Reader (r.jina.ai) and return markdown.

    Jina renders JavaScript and returns clean markdown, which unblocks
    modern sites whose content is invisible to a plain httpx GET (the page
    shell is empty until JS runs). Falls back to the plain text fetcher when
    the reader is unreachable, so the pipeline never hard-fails.
    """
    headers = {"X-Respond-With": "markdown"}
    try:
        from config import settings

        if settings.jina_api_key:
            headers["Authorization"] = f"Bearer {settings.jina_api_key}"
    except Exception:
        pass
    try:
        resp = httpx.get(
            f"https://r.jina.ai/{url}",
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code == 200 and resp.text.strip():
            return resp.text[:max_chars]
        logger.warning("jina reader returned status %s for %s; falling back to plain fetch", resp.status_code, url)
    except Exception as exc:
        logger.warning("jina reader unavailable for %s (%s); falling back to plain fetch", url, exc)
    return fetch_page_text(url, max_chars=max_chars)


_SITE_PATHS = [
    "/pages/shipping",
    "/pages/returns",
    "/shipping-returns",
    "/shipping",
    "/returns",
    "/pages/faq",
    "/faq",
    "/help",
    "/support",
    "/pages/contact",
    "/contact",
    "/contact-us",
    "/pages/about",
    "/about",
    "/about-us",
    "/careers",
    "/jobs",
    "/team",
]


def _body_key(text: str) -> str:
    """Fingerprint the real content, ignoring the Jina/HTML header block."""
    if "Markdown Content:" in text:
        text = text.split("Markdown Content:", 1)[1]
    # skip the promo/nav banner that repeats on every page
    for marker in ("Skip To Main", "Score free shipping", "Get a free", "Skip to main"):
        idx = text.find(marker)
        if idx != -1:
            text = text[idx + len(marker) :]
            break
    return text[:200]


def _is_error_page(text: str) -> bool:
    """Jina returns a small '404 Not Found' page for missing URLs."""
    low = text.lower()
    return "404 not found" in low or "404:" in low or "target url returned error" in low


def _strip_markdown(raw: str, max_chars: int = 6000) -> str:
    """Reduce Jina markdown to readable text: drop images, links, headers.

    Jina output is verbose (logos, image URLs, nav). The operational signal
    (policy prose, contact methods) sits between the noise, so we strip it
    before the page text reaches the LLM.
    """
    text = re.sub(r"!\[.*?\]\(.*?\)", " ", raw)          # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # link text only
    text = re.sub(r"[*_>`#]{1,}", " ", text)              # markdown markers
    text = re.sub(r"^\s*[-•]\s*", " ", text, flags=re.M)  # list bullets
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:max_chars]


def crawl_site_pages(url: str, max_pages: int = 5, per_page: int = 3500) -> str:
    """Fetch the homepage plus likely operational sub-pages and aggregate.

    Uses the Jina Reader for rendered markdown (unblocks JS-only sites),
    falling back to plain HTML fetch. Returns labelled, de-duplicated text
    so the analysis sees real signals (contact methods, shipping/returns
    policy, team size, FAQ) instead of a marketing-only homepage.
    """
    base = url.rstrip("/")
    sections = []
    seen: set[str] = set()
    candidates = [base] + [base + path for path in _SITE_PATHS]
    for page in candidates:
        if len(sections) >= max_pages:
            break
        try:
            text = fetch_page_markdown(page, max_chars=per_page)
        except Exception:
            continue
        if not text.strip() or _is_error_page(text):
            continue
        # de-dupe near-identical pages (many sites render the same shell)
        key = _body_key(text)
        if key in seen:
            continue
        seen.add(key)
        label = page.replace(base, "").strip("/") or "home"
        sections.append(f"=== {label} ===\n{_strip_markdown(text, max_chars=per_page)}")
        # stay under the public r.jina.ai rate limit between requests
        time.sleep(1.0)
    return "\n\n".join(sections) or ""


def get_client(
    llm_provider: str = "mock",
    api_key: str = "",
    model: str = "llama-3.3-70b-versatile",
    ollama_base_url: str = "http://localhost:11434",
) -> LLMClient:
    if llm_provider == "groq" and api_key:
        return GroqClient(api_key=api_key, model=model)
    if llm_provider == "groq":
        logger.warning("LLM provider is groq but no API key set; falling back to mock")
    if llm_provider == "ollama":
        if _ollama_reachable(ollama_base_url):
            return OllamaClient(base_url=ollama_base_url, model=model or "qwen2.5:3b")
        logger.warning("Ollama server not reachable at %s; falling back to mock", ollama_base_url)
        return MockClient()
    return MockClient()


def _extract_json(raw: str, *, expect_array: bool) -> dict | list:
    """Extract a JSON value from an LLM response.

    Chat models wrap JSON in markdown fences or add prose around it. Strip the
    fences, then fall back to locating the first balanced ``[...]`` or
    ``{...}`` region. Raises ``ValueError`` when nothing parseable is found.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    opener, closer = ("[", "]") if expect_array else ("{", "}")
    start = text.find(opener)
    if start == -1:
        raise ValueError(f"no JSON {closer}-container found in LLM response")
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("unbalanced JSON in LLM response")


def _normalize_deep_dive(data: dict, task_name: str) -> dict:
    """Make an LLM deep-dive response fit the ``DeepDive`` model.

    Small local models often return ``substeps`` as objects like
    ``{"step": "...", "description": "..."}`` while the model expects plain
    strings, and ``agent_flow`` / ``pilot_plan`` as lists of steps. Flatten
    every field the model expects as a plain string.
    """
    substeps = data.get("substeps") or []
    flattened = []
    for item in substeps:
        if isinstance(item, str):
            flattened.append(item)
        elif isinstance(item, dict):
            piece = item.get("description") or item.get("step") or item.get("title")
            if piece:
                flattened.append(str(piece))
        if len(flattened) >= 6:
            break

    def as_text(value) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = []
            for item in value:
                piece = as_text(item)
                if piece:
                    parts.append(piece)
            return " | ".join(parts) if parts else ""
        if isinstance(value, dict):
            # dicts like {"step1": "...", "step2": "..."} or
            # {"week": 1, "substeps": ["..."]} - recurse into values
            parts = []
            for v in value.values():
                piece = as_text(v)
                if piece:
                    parts.append(piece)
            return " | ".join(parts) if parts else ""
        return str(value) if value is not None else ""

    return {
        **data,
        "substeps": flattened,
        "agent_flow": as_text(data.get("agent_flow")),
        "main_risk": as_text(data.get("main_risk")),
        "pilot_plan": as_text(data.get("pilot_plan")),
        "task_name": task_name,
    }


def _analyze_website_llm(client: LLMClient, url: str, locale: str = "fr") -> dict:
    """Crawl a site and have the LLM extract a brand profile, with a retry.

    Small local models occasionally answer non-JSON; one retry smooths that.
    The crawl is done once and reused across attempts to avoid hammering the
    reader or the site.
    """
    from llm.prompts import ANALYZE_WEBSITE_PROMPT

    page = crawl_site_pages(url)
    prompt = ANALYZE_WEBSITE_PROMPT.get(locale, ANALYZE_WEBSITE_PROMPT["en"]).format(url=url, page=page)
    last_error: Optional[Exception] = None
    for attempt in range(2):
        try:
            raw = client._complete(prompt)
            data = _extract_json(raw, expect_array=False)
            if not isinstance(data, dict):
                raise ValueError("response is not a JSON object")
            return _normalize_website_profile(data)
        except (ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
            last_error = exc
            logger.warning("website analysis attempt %d failed (%s); retrying", attempt + 1, exc)
    raise ValueError(f"website analysis failed: {last_error}") from last_error


def _normalize_website_profile(data: dict) -> dict:
    """Validate a website-analysis LLM response into a BrandProfile-compatible dict."""
    tasks = []
    for item in data.get("tasks") or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        try:
            tasks.append(
                Task(
                    name=str(item["name"])[:80],
                    volume_per_week=float(item.get("volume_per_week", 0)),
                    minutes_per_unit=float(item.get("minutes_per_unit", 0)),
                    repetitiveness=int(item.get("repetitiveness", 3)),
                    automatability=int(item.get("automatability", 3)),
                    evidence=str(item.get("evidence") or "")[:200],
                ).model_dump()
            )
        except (ValueError, TypeError):
            continue
    sector = str(data.get("sector", "Other"))
    if sector not in {s.value for s in Sector}:
        sector = "Other"
    try:
        team_size = int(data.get("team_size", 0))
    except (ValueError, TypeError):
        team_size = 0
    return {
        "name": str(data.get("name") or "Site web")[:120],
        "sector": sector,
        "team_size": max(0, team_size),
        "free_text": str(data.get("free_text") or ""),
        "tasks": tasks,
    }


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
    rep_match = re.search(r"(highly?\s+repetitive|medium\s+repetitive|low\s+repetitive|repetitive)", body)
    if rep_match:
        token = rep_match.group(1)
        if token.startswith("high"):
            repetitiveness = REPETITIVENESS_MAP["high"]
        elif token.startswith("medium"):
            repetitiveness = REPETITIVENESS_MAP["medium"]
        elif token.startswith("low"):
            repetitiveness = REPETITIVENESS_MAP["low"]
        else:
            repetitiveness = REPETITIVENESS_MAP["medium"]

    automatability = 3
    if "highly repetitive" in body or "automatab" in body:
        automatability = 4
    elif "low repetitive" in body:
        automatability = 1

    return Task(
        name=name,
        volume_per_week=volume,
        minutes_per_unit=minutes,
        repetitiveness=repetitiveness,
        automatability=automatability,
    )
