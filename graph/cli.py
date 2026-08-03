"""CLI entrypoint for the analysis graph. No UI, prints only.

Construction-order step 1: proves the full flow works before Streamlit.
Step 7: graph driving lives in the app/ use-case layer.

Usage:
    python graph/cli.py run --preset lumea
    python graph/cli.py run --name "Acme" --sector D2C --free-text "..."
    python graph/cli.py run --preset lumea --non-interactive
"""

from __future__ import annotations

import argparse
import sys
import time

from app.presets import load_preset
from app.run_analysis import build_runtime, resume_review, run_analysis
from domain.models import Assumptions, BrandProfile, Sector


def prompt_review(state: dict) -> str:
    print("\n--- REVUE HUMAINE (obligatoire avant le rapport final) ---")
    for scored in state.get("scored_tasks", []):
        print(
            f"  #{scored.get('roi_rank')} {scored.get('task'):<32} "
            f"{scored.get('hours_per_month'):>7.1f} h/mois  {scored.get('eur_per_month'):>8.0f} EUR/mois  "
            f"score {scored.get('priority_score'):>5.1f}"
        )
    for dive in state.get("deep_dives", []):
        badge = " [estimation degradee]" if dive.get("degraded") else ""
        print(f"  - deep dive: {dive.get('task_name')} -> {dive.get('proposed_tool')}{badge}")
    while True:
        choice = input("\nApprouver / Modifier / Rejeter [a/m/r] ? ").strip().lower()
        if choice.startswith("a"):
            return "approve"
        if choice.startswith("m"):
            print("Modification non prise en charge en CLI v1 ; passage en re-score.")
            return "edit"
        if choice.startswith("r"):
            return "reject"
        print("Reponse invalide.")


def build_inputs(args) -> dict:
    if args.preset:
        brand = load_preset(args.preset)
    else:
        sector = Sector(args.sector) if args.sector else Sector.OTHER
        brand = BrandProfile(
            name=args.name or "Marque sans nom",
            sector=sector,
            team_size=args.team_size or 10,
            channels=[],
            free_text=args.free_text or "",
        )
    default_assumptions = brand.default_assumptions or Assumptions(hourly_rate_eur=40)
    assumptions = Assumptions(
        hourly_rate_eur=args.hourly_rate or default_assumptions.hourly_rate_eur,
        weeks_per_month=args.weeks_per_month or default_assumptions.weeks_per_month,
        locale=default_assumptions.locale,
    )
    return {"brand": brand, "assumptions": assumptions}


def _crew_mode(args) -> str:
    return "crewai" if args.groq_api_key else "degrade"


def run(args) -> int:
    inputs = build_inputs(args)
    runtime = build_runtime(
        provider=args.llm_provider,
        api_key=args.groq_api_key,
        model=args.groq_model,
        checkpoint_db=args.checkpoint_db,
    )
    thread_id = f"cli-{int(time.time())}"
    result = run_analysis(
        brand=inputs["brand"],
        assumptions=inputs["assumptions"],
        runtime=runtime,
        thread_id=thread_id,
    )
    print(
        f"=== Analyse '{inputs['brand'].name}' "
        f"(llm={runtime.llm_name}, deep_dive={_crew_mode(args)}) ==="
    )
    config = result.config
    while True:
        for node, event in result.events:
            print(f"  [{node}] {event}")
        if result.interrupted is None:
            break
        action = "approve" if args.non_interactive else prompt_review(result.interrupted)
        result = resume_review(runtime, config, action)

    final = result.final
    if final.get("action") == "reject":
        print("\n=== Analyse rejetee, aucun rapport final genere. ===")
        return 0
    if final.get("report"):
        print("\n=== RAPPORT FINAL ===")
        print(final["report"])
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ops-autopilot")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a full analysis")
    run_p.add_argument("--preset", choices=["lumea", "saas"])
    run_p.add_argument("--name")
    run_p.add_argument("--sector", choices=[s.value for s in Sector])
    run_p.add_argument("--team-size", type=int)
    run_p.add_argument("--free-text")
    run_p.add_argument("--hourly-rate", type=float)
    run_p.add_argument("--weeks-per-month", type=float)
    run_p.add_argument("--non-interactive", action="store_true")
    run_p.add_argument("--llm-provider", default="mock", choices=["mock", "groq"])
    run_p.add_argument("--groq-api-key", default="")
    run_p.add_argument("--groq-model", default="llama-3.3-70b-versatile")
    run_p.add_argument("--checkpoint-db", default="ops_autopilot_checkpoints.db")
    run_p.set_defaults(func=run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
