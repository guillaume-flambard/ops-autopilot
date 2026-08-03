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

ANALYZE_SITE_FACTS_PROMPT = {
    "fr": (
        "Tu es un analyste d'operations. On te donne le contenu de plusieurs pages d'un site web (markdown). "
        "Reponds en JSON avec cet objet exact : "
        "{{\"name\": \"nom de la marque\", \"sector\": \"D2C|SaaS|Agency|Other\", "
        "\"team_size\": entier (0 si inconnu), "
        "\"facts\": [{{\"type\": \"support_email|support_phone|support_chat|shipping_policy|returns_policy|"
        "tracking|faq_topic|order_process|other\", \"value\": \"un fait concret, phrase courte\"}}]}}. "
        "REGLE : ne liste que des faits RELLEMENT ecrits sur le site, sans interpretation. "
        "Cible : email/chat/telephone de support, politique de livraison et retours (delais, frais, process), "
        "suivi de commande, FAQ, process de commande/paiement. "
        "3 a 10 faits. Si rien, facts=[]. Ne reponds qu'avec le JSON.\n\nSite : {url}\n\nContenu des pages :\n{page}"
    ),
    "en": (
        "You are an operations analyst. You are given the content of several pages of a brand's website (markdown). "
        "Answer as JSON with this exact object: "
        "{{\"name\": \"brand name\", \"sector\": \"D2C|SaaS|Agency|Other\", "
        "\"team_size\": integer (0 if unknown), "
        "\"facts\": [{{\"type\": \"support_email|support_phone|support_chat|shipping_policy|returns_policy|"
        "tracking|faq_topic|order_process|other\", \"value\": \"a concrete fact, short sentence\"}}]}}. "
        "RULE: only list facts ACTUALLY written on the site, no interpretation. "
        "Target: support email/chat/phone, shipping and returns policy (delays, fees, process), "
        "order tracking, FAQ, order/payment process. "
        "3 to 10 facts. If none, facts=[]. Respond with the JSON only.\n\nSite: {url}\n\nPage content:\n{page}"
    ),
}

ANALYZE_WEBSITE_PROMPT = {
    "fr": (
        "Tu es un analyste d'operations. On te donne des faits observes sur le site web d'une marque. "
        "Reponds en JSON avec cet objet exact : "
        "{{\"free_text\": \"description factuelle des operations observees\", "
        "\"tasks\": [{{\"name\": \"tache courte\", \"volume_per_week\": nombre, \"minutes_per_unit\": nombre, "
        "\"repetitiveness\": entier 1-5, \"automatability\": entier 1-5, "
        "\"evidence\": \"le fait (type+value) qui justifie cette tache, ou 'estimate'\"}}]}}. "
        "REGLE STRICTE : n'invente AUCUN volume ni duree. Si aucun fait ne donne de chiffre pour une tache, "
        "mets volume_per_week=0 et minutes_per_unit=0. "
        "evidence DOIT etre le type et la valeur du fait qui justifie la tache (ex. 'tracking: You'll get a shipment "
        "notification email'), PAS 'estimate'. N'utilise 'estimate' que si AUCUN fait ne correspond. "
        "Construis 2-6 taches a partir des faits (support par email, gestion des livraisons/retours, "
        "reponse FAQ, traitement des commandes...). Si aucun fait operationnel, renvoie tasks=[]. "
        "Ne reponds qu'avec le JSON.\n\nFaits observes :\n{facts}"
    ),
    "en": (
        "You are an operations analyst. You are given facts observed on a brand's website. "
        "Answer as JSON with this exact object: "
        "{{\"free_text\": \"factual description of the operations observed\", "
        "\"tasks\": [{{\"name\": \"short task\", \"volume_per_week\": number, \"minutes_per_unit\": number, "
        "\"repetitiveness\": integer 1-5, \"automatability\": integer 1-5, "
        "\"evidence\": \"the fact (type+value) justifying this task, or 'estimate'\"}}]}}. "
        "STRICT RULE: do not invent any volume or duration. If no fact gives a figure for a task, "
        "set volume_per_week=0 and minutes_per_unit=0. "
        "evidence MUST be the type and value of the fact justifying the task (e.g. 'tracking: You'll get a shipment "
        "notification email'), NOT 'estimate'. Only use 'estimate' if NO fact matches. "
        "Build 2-6 tasks from the facts (email support, shipping/returns handling, FAQ responses, "
        "order processing...). If no operational fact, return tasks=[]. "
        "Respond with the JSON only.\n\nObserved facts:\n{facts}"
    ),
}
