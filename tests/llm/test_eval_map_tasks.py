"""Eval suite v1.1: ground-truth scoring of the free-text task parser.

Scores the deterministic MockClient parser (``_parse_free_text``) against a
hand-curated dataset of realistic free-text inputs. Each case carries the
expected task and the true field values; scoring tolerates small deviations
on numeric fields (volume / minutes) so phrasing differences do not flake.

The suite asserts an aggregate score floor. It runs offline with the mock
parser; a live Groq variant is a manual, keyed run (see ``eval/README``).
"""

from __future__ import annotations

from dataclasses import dataclass

from llm.client import MockClient

# tolerance on numeric fields (fraction of the expected value)
_TOL = 0.1


@dataclass
class Case:
    free_text: str
    expected_name: str
    volume_per_week: float
    minutes_per_unit: float
    repetitiveness: int
    automatability: int


CASES: list[Case] = [
    Case(
        "Instagram DM responses: ~50/day, 2 min each, highly repetitive.",
        "Instagram DM responses", 350, 2, 5, 4,
    ),
    Case(
        "Shopify order processing: ~100/day, 3 min each, medium repetitive.",
        "Shopify order processing", 700, 3, 3, 3,
    ),
    Case(
        "Onboarding calls: 10/week, 30 min each, medium repetitive.",
        "Onboarding calls", 10, 30, 3, 3,
    ),
    Case(
        "Email support tickets: 200/month, 15 min each, highly repetitive.",
        "Email support tickets", 46.19, 15, 5, 4,
    ),
    Case(
        "Product photography planning: weekly, 60 min, low repetitive.",
        "Product photography planning", 1, 60, 1, 1,
    ),
    Case(
        "Invoice reconciliation: 2 hours weekly, repetitive.",
        "Invoice reconciliation", 1, 120, 3, 3,
    ),
    Case(
        "Social media scheduling: ~5/day, 10 min, highly repetitive.",
        "Social media scheduling", 35, 10, 5, 4,
    ),
    Case(
        "Custom web dev for clients: 3/week, 4 hours, low repetitive.",
        "Custom web dev for clients", 3, 240, 1, 1,
    ),
    Case(
        "Data entry: 40/week, 5 min each, highly repetitive, automatable.",
        "Data entry", 40, 5, 5, 4,
    ),
    Case(
        "Client follow-ups: 15/week, 8 min, repetitive.",
        "Client follow-ups", 15, 8, 3, 3,
    ),
]


@dataclass
class CaseScore:
    case: Case
    ok: bool
    reason: str
    details: dict


def _score_case(case: Case) -> CaseScore:
    tasks = MockClient().map_tasks_from_text(case.free_text)
    match = next((t for t in tasks if t.name == case.expected_name), None)
    if match is None:
        return CaseScore(
            case, False,
            f"task '{case.expected_name}' not found; got {[t.name for t in tasks]}",
            {},
        )

    def _near(got: float, want: float) -> bool:
        if want == 0:
            return got == 0
        return abs(got - want) / want <= _TOL

    failures = []
    if not _near(match.volume_per_week, case.volume_per_week):
        failures.append(f"volume {match.volume_per_week} != {case.volume_per_week}")
    if not _near(match.minutes_per_unit, case.minutes_per_unit):
        failures.append(f"minutes {match.minutes_per_unit} != {case.minutes_per_unit}")
    if match.repetitiveness != case.repetitiveness:
        failures.append(f"repetitiveness {match.repetitiveness} != {case.repetitiveness}")
    if match.automatability != case.automatability:
        failures.append(f"automatability {match.automatability} != {case.automatability}")

    details = {
        "volume_per_week": (match.volume_per_week, case.volume_per_week),
        "minutes_per_unit": (match.minutes_per_unit, case.minutes_per_unit),
        "repetitiveness": (match.repetitiveness, case.repetitiveness),
        "automatability": (match.automatability, case.automatability),
    }
    return CaseScore(case, not failures, "; ".join(failures) or "ok", details)


def _run_suite() -> list[CaseScore]:
    return [_score_case(c) for c in CASES]


def _fmt_reason(s: CaseScore) -> str:
    mismatches = []
    for field, (got, want) in s.details.items():
        if abs(got - want) > (_TOL * want if want else 0.0) and got != want:
            mismatches.append(f"{field}: {got} vs {want}")
    return ", ".join(mismatches) or s.reason


def test_eval_suite_reaches_floor() -> None:
    scores = _run_suite()
    passed = sum(1 for s in scores if s.ok)
    total = len(scores)
    pct = 100.0 * passed / total
    failed = [s for s in scores if not s.ok]
    details = "\n".join(
        f"  - {s.case.expected_name}: {_fmt_reason(s)}" for s in failed
    )
    assert pct >= 90, (
        f"eval floor not reached: {passed}/{total} ({pct:.0f}%)\n"
        f"failing cases:\n{details}"
    )
