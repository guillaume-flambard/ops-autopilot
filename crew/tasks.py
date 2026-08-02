"""CrewAI task definitions for the deep-dive step.

Three sequential tasks over the top-N scored tasks. The LLM never computes
money: the scored figures are injected as context, and the final output is
one JSON array with a DeepDive entry per task.
"""

from __future__ import annotations

from crewai import Task

from domain.models import Assumptions, ScoredTask


def _context_lines(scored_tasks: list[ScoredTask]) -> str:
    return "\n".join(
        f"- {s.task.name} : {s.hours_per_month:.1f} h/mois, {s.eur_per_month:.0f} EUR/mois, "
        f"repetitivite {s.task.repetitiveness}/5, automatisabilite {s.task.automatability}/5"
        for s in scored_tasks
    )


def build_tasks(
    scored_tasks: list[ScoredTask],
    assumptions: Assumptions,
    agents: tuple[object, object, object],
    locale: str = "fr",
) -> list[Task]:
    ops, roi, arch = agents
    context = _context_lines(scored_tasks)
    names = ", ".join(s.task.name for s in scored_tasks)

    if locale == "en":
        task1 = Task(
            description=(
                f"Break down these tasks into substeps and mark what is realistically automatable.\n"
                f"Tasks: {names}\n\nContext figures:\n{context}\n"
                "Output JSON array: [{\"task_name\": \"...\", \"substeps\": [\"...\"]}]"
            ),
            expected_output="A JSON array with task_name and substeps for every task.",
            agent=ops,
        )
        task2 = Task(
            description=(
                f"Using ONLY the figures above ({assumptions.hourly_rate_eur} EUR/hour, "
                f"{assumptions.weeks_per_month} weeks/month), note for each task the share of hours "
                "that automation can realistically save (0 to 1). Never invent rates or totals.\n"
                "Output JSON array: [{\"task_name\": \"...\", \"savable_share\": 0.6}]"
            ),
            expected_output="A JSON array with task_name and savable_share for every task.",
            agent=roi,
            context=[task1],
        )
        task3 = Task(
            description=(
                f"For each task propose the tool, the agent flow, the main risk, the effort in weeks "
                f"(2 to 3) and a short pilot plan. Flag human validation when money is involved.\n"
                "Output JSON array: [{\"task_name\": \"...\", \"proposed_tool\": \"...\", "
                "\"agent_flow\": \"...\", \"main_risk\": \"...\", \"effort_weeks\": 2, "
                "\"pilot_plan\": \"...\"}]"
            ),
            expected_output="A single JSON array, one object per task.",
            agent=arch,
            context=[task1, task2],
        )
    else:
        task1 = Task(
            description=(
                f"Decompose ces taches en sous-etapes et marque ce qui est realisable automatiquement.\n"
                f"Taches : {names}\n\nChiffres fournis :\n{context}\n"
                "Reponds avec un tableau JSON : [{\"task_name\": \"...\", \"substeps\": [\"...\"]}]"
            ),
            expected_output="Un tableau JSON avec task_name et substeps pour chaque tache.",
            agent=ops,
        )
        task2 = Task(
            description=(
                f"En utilisant UNIQUEMENT les chiffres ci-dessus ({assumptions.hourly_rate_eur} EUR/heure, "
                f"{assumptions.weeks_per_month} semaines/mois), indique pour chaque tache la part d'heures "
                "qu'une automatisation peut reellement gagner (0 a 1). N'invente jamais de taux ni de total.\n"
                "Reponds avec un tableau JSON : [{\"task_name\": \"...\", \"savable_share\": 0.6}]"
            ),
            expected_output="Un tableau JSON avec task_name et savable_share pour chaque tache.",
            agent=roi,
            context=[task1],
        )
        task3 = Task(
            description=(
                f"Pour chaque tache, propose l'outil, le flux d'agents, le risque principal, l'effort en "
                f"semaines (2 a 3) et un court plan pilote. Signale quand une decision engage de l'argent "
                "et exige une validation humaine.\n"
                "Reponds avec un tableau JSON : [{\"task_name\": \"...\", \"proposed_tool\": \"...\", "
                "\"agent_flow\": \"...\", \"main_risk\": \"...\", \"effort_weeks\": 2, "
                "\"pilot_plan\": \"...\"}]"
            ),
            expected_output="Un seul tableau JSON, un objet par tache.",
            agent=arch,
            context=[task1, task2],
        )

    return [task1, task2, task3]
