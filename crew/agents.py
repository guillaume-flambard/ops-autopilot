"""CrewAI agents used by the deep-dive step only.

Each agent is a plain CrewAI ``Agent``. The llm argument accepts a real
``crewai.LLM`` (Groq) or a fake subclass for offline tests.
"""

from __future__ import annotations

from crewai import Agent

FR = {
    "ops_role": "Analyste Operations",
    "ops_goal": "Decomposer chaque tache prioritaire en sous-etapes et identifier ce qui est realisable automatiquement.",
    "ops_backstory": "Tu decomposes des flux operationnels complexes en briques simples. Tu sais reconnaitre une tache reelle d'une tache que l'automatisation ne peut pas toucher.",
    "roi_role": "Estimateur ROI",
    "roi_goal": "Estimer le gain realiste de chaque automatisation en t'appuyant UNIQUEMENT sur les chiffres fournis, sans jamais inventer de taux horaire.",
    "roi_backstory": "Tu rattaches des euros aux heures sauvees. Tu ne recalculer jamais les totaux : les heures et montants te sont donnes, tu en juges la part realisable.",
    "arch_role": "Architecte Solution",
    "arch_goal": "Proposer l'outil, le flux d'agents, le risque principal et un plan pilote de 2 a 3 semaines pour chaque tache.",
    "arch_backstory": "Tu conçois des automatisations pragmatiques. Tu signales quand une decision engage de l'argent et exige une validation humaine.",
}

EN = {
    "ops_role": "Ops Analyst",
    "ops_goal": "Break each priority task into substeps and mark what can realistically be automated.",
    "ops_backstory": "You decompose complex operational flows into simple units. You know when a task needs a human and when it does not.",
    "roi_role": "ROI Estimator",
    "roi_goal": "Estimate the realistic savings of each automation using ONLY the figures provided, never inventing an hourly rate.",
    "roi_backstory": "You attach euros to saved hours. You never recompute totals: hours and amounts are given to you, you judge what share is realistically automatable.",
    "arch_role": "Solution Architect",
    "arch_goal": "Propose the tool, the agent flow, the main risk and a 2 to 3 week pilot plan for each task.",
    "arch_backstory": "You design pragmatic automations. You flag when a decision commits money and requires human validation.",
}


def build_agents(llm, locale: str = "fr") -> tuple[Agent, Agent, Agent]:
    copy = EN if locale == "en" else FR
    return (
        Agent(
            role=copy["ops_role"],
            goal=copy["ops_goal"],
            backstory=copy["ops_backstory"],
            llm=llm,
            verbose=False,
        ),
        Agent(
            role=copy["roi_role"],
            goal=copy["roi_goal"],
            backstory=copy["roi_backstory"],
            llm=llm,
            verbose=False,
        ),
        Agent(
            role=copy["arch_role"],
            goal=copy["arch_goal"],
            backstory=copy["arch_backstory"],
            llm=llm,
            verbose=False,
        ),
    )
