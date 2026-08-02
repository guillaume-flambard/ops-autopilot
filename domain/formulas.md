# Ops Autopilot formula documentation

Every figure shown by the product is computed from three configurable
inputs and the formulas below. There are no magic numbers: change an input
and every downstream figure updates through these formulas.

## Inputs (the assumptions panel)

| Input | Meaning | Default |
| --- | --- | --- |
| `hourly_rate_eur` | Cost of one hour of team time, in EUR | none, user must set it |
| `weeks_per_month` | Working weeks per calendar month | 4.33 |
| `locale` | Report and UI language | fr |

## Task inputs

| Input | Meaning |
| --- | --- |
| `volume_per_week` | How many units of this task happen per week |
| `minutes_per_unit` | How many minutes one unit takes |
| `repetitiveness` | 1 = creative or unpredictable, 5 = identical every time |
| `automatability` | 1 = needs human judgment, 5 = trivially automatable |

## Formulas

```
hours_per_month = volume_per_week * (minutes_per_unit / 60) * weeks_per_month
eur_per_month   = hours_per_month * hourly_rate_eur
etp             = hours_per_month / 151.67

priority_score  = hours_per_month * (repetitiveness / 5) * (automatability / 5)
```

### Worked example

A task at 350 units/week, 2 minutes per unit, repetitiveness 5,
automatability 4, with a 35 EUR/hour rate:

```
hours_per_month = 350 * (2 / 60) * 4.33 = 50.52
eur_per_month   = 50.52 * 35 = 1768.1 EUR
etp             = 50.52 / 151.67 = 0.333
priority_score  = 50.52 * (5 / 5) * (4 / 5) = 40.42
```

## Constants

| Constant | Value | Why |
| --- | --- | --- |
| `HOURS_PER_FTE_PER_MONTH` | 151.67 | 35 h/week, 52 weeks, divided by 12 |

## Ranking

Tasks are ranked by descending `priority_score`. On a tie, the task with
the higher `eur_per_month` wins. The top three ranked tasks are the only
ones that receive a deep dive.

## Totals

The assumptions panel shows three aggregate figures across all scored tasks:

```
total_hours_per_month = sum(hours_per_month)
total_eur_per_month   = sum(eur_per_month)
total_etp             = total_hours_per_month / 151.67
```

## Why scoring is code, not an LLM output

The LLM maps free text into structured tasks. It never computes a euro.
All money and priority figures flow through this module so they are
deterministic, auditable, and testable.
