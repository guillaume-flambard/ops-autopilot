"""Prompt templates for LLM calls. FR and EN variants.

The LLM never computes financial figures. It only structures input and
writes prose; every euro is derived in domain/scoring.py.
"""

MAP_TASKS_PROMPT = {
    "fr": (
        "Tu es un analyste d'operations. Transforme la description d'une marque en liste de taches "
        "structurees au format JSON. Pour chaque tache, fournis : name (court), volume_per_week "
        "(nombre d'unites par semaine), minutes_per_unit (minutes par unite), repetitiveness "
        "(entier 1 a 5 : 1 = creatif/imprevisible, 5 = identique chaque fois), automatability "
        "(entier 1 a 5 : 1 = jugement humain requis, 5 = trivialement automatisable). "
        "Reponds uniquement avec un tableau JSON valide.\n\nDescription :\n{free_text}"
    ),
    "en": (
        "You are an operations analyst. Turn the brand description below into a list of structured "
        "tasks as JSON. For each task provide: name (short), volume_per_week (units per week), "
        "minutes_per_unit (minutes per unit), repetitiveness (integer 1 to 5: 1 = creative or "
        "unpredictable, 5 = identical every time), automatability (integer 1 to 5: 1 = needs human "
        "judgment, 5 = trivially automatable). Respond with a single valid JSON array only.\n\n"
        "Description:\n{free_text}"
    ),
}

REPORT_EXECUTIVE_PROMPT = {
    "fr": (
        "Redige un resume executif de 5 lignes pour un rapport d'automatisation. "
        "Secteur de la marque : {sector}. Volume mensuel estime : {total_hours} heures, "
        "{total_eur} EUR, {total_etp} ETP. Mentionne la priorite numero 1 ({top_name}) "
        "et le fait que les chiffres reposent sur des hypotheses visibles. Ne reponds qu'avec le resume."
    ),
    "en": (
        "Write a 5-line executive summary for an automation report. Brand sector: {sector}. "
        "Estimated monthly volume: {total_hours} hours, {total_eur} EUR, {total_etp} ETP. "
        "Mention the number one priority ({top_name}) and that figures rest on visible assumptions. "
        "Respond with the summary only."
    ),
}

ANALYZE_WEBSITE_PROMPT = {
    "fr": (
        "Tu es un analyste d'operations. Analyse le site web d'une marque et reponds en JSON avec "
        "cet objet exact : {{\"name\": \"nom de la marque\", \"sector\": \"D2C|SaaS|Agency|Other\", "
        "\"team_size\": entier, \"free_text\": \"description des operations en 2-3 phrases\", "
        "\"tasks\": [{{\"name\": \"tache courte\", \"volume_per_week\": nombre, \"minutes_per_unit\": nombre, "
        "\"repetitiveness\": entier 1-5, \"automatability\": entier 1-5}}]}}. "
        "Infer 3-6 taches operationnelles reelles (support, logistique, marketing manuel, admin...). "
        "Ne reponds qu'avec le JSON.\n\nSite : {url}\n\nContenu de la page :\n{page}"
    ),
    "en": (
        "You are an operations analyst. Analyze a brand's website and answer as JSON with this exact "
        "object: {{\"name\": \"brand name\", \"sector\": \"D2C|SaaS|Agency|Other\", "
        "\"team_size\": integer, \"free_text\": \"2-3 sentence description of operations\", "
        "\"tasks\": [{{\"name\": \"short task\", \"volume_per_week\": number, \"minutes_per_unit\": number, "
        "\"repetitiveness\": integer 1-5, \"automatability\": integer 1-5}}]}}. "
        "Infer 3-6 real operational tasks (support, logistics, manual marketing, admin...). "
        "Respond with the JSON only.\n\nSite: {url}\n\nPage content:\n{page}"
    ),
}
