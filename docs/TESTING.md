# Guide de test - Ops Autopilot

Pour tester l'app en 5 minutes, sans config, avec le compte de démo deja cree.

## L'app est deja lancee

Adresse : http://localhost:8501

Elle tourne en **mode mock** (LLM hors ligne, deterministe). C'est le mode le
plus fiable pour tester : il ne consomme aucun quota et repond en quelques
secondes. Voir plus bas pour passer en mode groq (LLM reel).

Compte de test existant :
- Email : `guide@test.com`
- Mot de passe : `Test-pw-123`

## Parcours de test complet (6 minutes)

### 1. Connexion

1. Ouvre http://localhost:8501
2. Renseigne `guide@test.com` et `Test-pw-123`
3. Clique "Se connecter"

La page d'analyse s'affiche : preset Lumea charge, taux horaire a 40 EUR/h,
fournisseur sur "mock".

### 2. Lancer une analyse

1. Clique "Lancer l'analyse"
2. En quelques secondes tu arrives a l'ecran **Revue humaine - Lumea** :
   - tableau des taches notees (ROI) : Shopify order processing, Instagram DM
     responses, Email support tickets, Product photography planning
   - les 3 plans pilotes (en mode mock ils affichent "Template degrade (hors
     ligne)"). C'est normal, c'est le fallback offline. En mode groq ils
     sont generes par CrewAI.
3. Ouvre le panneau "Etapes" pour voir le pipeline : ingest, map_tasks, score,
   check_data, deep_dive.

### 3. Tester les 3 actions de revue

- **Approuver** : genere le rapport final, le sauvegarde en base, propose
  "Nouvelle analyse".
- **Modifier** : ouvre un champ "Nouveau taux horaire", entre une valeur plus
  haute (ex. 60), clique "Re-scorer avec ce taux". Les montants EUR/mois
  remontent. Puis Approuve.
- **Rejeter** : termine sans rapport, mais l'analyse reste en historique avec
  le statut "rejected".

### 4. Verifier l'historique

1. Dans la sidebar, choisis "Historique"
2. Le selecteur "Analyse" liste tes analyses, triees de la plus recente :
   `#2 - Lumea (approved, 2026-08-03T06:53)` par exemple
3. Choisis-en une : le rapport s'affiche sous le selecteur.

### 5. Test rapide en marque personnalisee

1. Retour sur "Nouvelle analyse"
2. Source = "Personnalisee"
3. Renseigne un nom de marque, un secteur, et une description en francais,
   par exemple :
   `Email support tickets: ~40/week, 10 min each, highly repetitive.`
4. L'analyse part du texte libre et arrive aussi a la revue humaine.

## Lancer l'app soi-meme

```bash
cd ~/projects/ops-autopilot
make run        # mode mock, lit .env
```

Pour forcer le mode groq (LLM reel) :

```bash
LLM_PROVIDER=groq GROQ_API_KEY=ta_cle .venv/bin/streamlit run ui/app.py
```

Le mode groq est aussi utilisable depuis l'UI : dans le formulaire, choisis
"Fournisseur = groq" et renseigne ta cle API Groq.

## CLI (sans UI)

```bash
cd ~/projects/ops-autopilot
make demo       # arc demo offline, mock LLM, preset lumea
.venv/bin/python -m graph.cli run --preset lumea --non-interactive
.venv/bin/python -m graph.cli run --name "Acme" --sector D2C \
  --free-text "Instagram DMs: ~50/day, 2 min each, highly repetitive."
```

Chaque run s'arrete a la revue humaine. Reponds a /m pour modifier, a pour
approuver, r pour rejeter.

## Tests et couverture

```bash
make test                 # 85 tests, hermetiches, ~10 s
make coverage             # 93 % de couverture globale
```

Points d'attention :

- Les tests UI sont isoles du reseau grace a `tests/conftest.py` : meme si
  ton `.env` contient une cle Groq, les tests ne l'utilisent jamais.
- Le quota Groq quotidien (100 000 tokens) peut se vider en testant en mode
  groq. Le fallback mock prend alors le relais automatiquement, l'app reste
  utilisable.

## Depannage

| Symptome | Cause | Solution |
|---|---|---|
| "Template degrade (hors ligne)" dans les plans pilotes | mode mock, ou quota Groq epuise | normal en mock ; en groq, attends la reset du quota |
| Le rapport n'apparait pas en mode groq | quota 429, retries puis echec | repasse en mock ou attends |
| Port 8501 deja utilise | une autre instance tourne | `lsof -iTCP:8501 -sTCP:LISTEN` puis kill le PID |
| L'app ne se lance pas | venv absent | `make install` |

## Architecture en bref

- `domain/` : regles metier pures (scoring, formules). Aucun LLM, aucun framework.
- `app/` : couche use-case partagee CLI + UI (`build_runtime`, `run_analysis`, `resume_review`).
- `graph/` : LangGraph (ingest, map_tasks, score, deep_dive, check_data, human_review, report).
- `crew/` : CrewAI, appele uniquement par deep_dive (3 agents).
- `llm/` : client Groq avec retry/backoff + fallback mock deterministe.
- `db/` : SQLite, schema Postgres-ready (User, Analysis).
- `ui/` : Streamlit, couche fine.

La regle produit a garder en tete : **l'agent ne finalise jamais seul des
chiffres qui engagent un budget, la revue humaine est obligatoire**. Et tout
montant passe par `domain/scoring.py`, jamais par le LLM.
