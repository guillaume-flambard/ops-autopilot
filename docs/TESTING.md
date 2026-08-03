# Guide de test - Ops Autopilot

Pour tester l'app en 5 minutes, sans config, avec le compte de démo deja cree.

## L'app est deja lancee

Adresse : http://localhost:8501

Elle tourne en **mode ollama** : LLM local (qwen2.5:3b), aucun quota, repond
en quelques secondes. C'est le mode le plus pratique pour tester. Si le
serveur Ollama est arrete, l'app rechute automatiquement sur le mode mock
(LLM hors ligne, deterministe). Voir plus bas pour passer en mode groq (LLM
reel, sujet au quota quotidien).

Compte de test existant :
- Email : `guide@test.com`
- Mot de passe : `Test-pw-123`

## Parcours de test complet (6 minutes)

### 1. Connexion

1. Ouvre http://localhost:8501
2. Renseigne `guide@test.com` et `Test-pw-123`
3. Clique "Se connecter"

La page d'analyse s'affiche : preset Lumea charge, taux horaire a 40 EUR/h,
fournisseur sur "ollama".

### 2. Lancer une analyse

1. Clique "Lancer l'analyse"
2. En quelques secondes tu arrives a l'ecran **Revue humaine - Lumea** :
   - tableau des taches notees (ROI) : Shopify order processing, Instagram DM
     responses, Email support tickets, Product photography planning
   - les 3 plans pilotes generes par CrewAI avec le modele local. Si le
     serveur Ollama est down ou si le modele repond mal, ils affichent
     "Template degrade (hors ligne)", c'est le fallback.
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

### 6. Analyser n'importe quel site web

1. Retour sur "Nouvelle analyse"
2. Source = "Site web (URL)"
3. Renseigne l'URL d'une marque, par exemple `https://www.glossier.com`
4. L'app charge la page et le LLM local (ou groq) en extrait la marque, le
   secteur et 3-6 taches operationnelles.
5. L'analyse arrive a la revue humaine comme les autres sources, puis tu
   Approuves pour le rapport.

Astuce : fonctionne avec n'importe quel site. En mode mock (LLM hors ligne)
l'analyse extrait les taches du texte de la page, c'est moins riche mais ca
reste testable.

## Lancer l'app soi-meme

```bash
cd ~/projects/ops-autopilot
make run        # mode ollama (local) si LLM_PROVIDER=ollama dans .env
```

Pour forcer le mode groq (LLM reel) :

```bash
LLM_PROVIDER=groq GROQ_API_KEY=ta_cle .venv/bin/streamlit run ui/app.py
```

Le fournisseur se change aussi depuis l'UI : dans le formulaire, choisis
"Fournisseur" = ollama (local) ou groq. Le mode groq n'apparait que si une
cle est configuree dans `.env`.

## CLI (sans UI)

```bash
cd ~/projects/ops-autopilot
make demo       # arc demo offline, mock LLM, preset lumea
.venv/bin/python -m graph.cli run --preset lumea --non-interactive
.venv/bin/python -m graph.cli run --llm-provider ollama --preset lumea
.venv/bin/python -m graph.cli run --llm-provider ollama --url https://www.glossier.com --non-interactive
.venv/bin/python -m graph.cli run --llm-provider groq --groq-api-key "$GROQ_API_KEY" --preset lumea
.venv/bin/python -m graph.cli run --name "Acme" --sector D2C \
  --free-text "Instagram DMs: ~50/day, 2 min each, highly repetitive."
```

Chaque run s'arrete a la revue humaine. Reponds a /m pour modifier, a pour
approuver, r pour rejeter.

## Tests et couverture

```bash
make test                 # 95 tests, hermetiches, ~10 s
make coverage             # 93 % de couverture globale
```

Points d'attention :

- Les tests sont isoles du reseau grace a `tests/conftest.py` : meme si ton
  `.env` contient une cle Groq, les tests ne l'utilisent jamais. Le client
  Ollama est teste via un transport HTTP mock (aucun vrai serveur en CI).
- Le quota Groq quotidien (100 000 tokens) peut se vider en testant en mode
  groq. Le fallback mock prend alors le relais automatiquement, l'app reste
  utilisable. En mode ollama il n'y a aucun quota.

## Depannage

| Symptome | Cause | Solution |
|---|---|---|
| "Template degrade (hors ligne)" dans les plans pilotes | mode mock, Ollama down, ou quota Groq epuise | normal en mock ; en ollama, verifie `ollama serve` ; en groq, attends la reset du quota |
| L'analyse retombe sur mock alors que ollama est choisi | serveur Ollama arrete | lance `ollama serve`, puis relance l'analyse |
| Le rapport n'apparait pas en mode groq | quota 429, retries puis echec | repasse en ollama ou mock, ou attends |
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
