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
        "Tu es un analyste d'operations. On te donne le contenu de plusieurs pages d'un site web (markdown). "
        "Reponds en JSON avec cet objet exact : "
        "{{\"name\": \"nom de la marque\", \"sector\": \"D2C|SaaS|Agency|Other\", "
        "\"team_size\": entier (n'invente pas : 0 si inconnu), "
        "\"free_text\": \"description factuelle des operations observees\", "
        "\"tasks\": [{{\"name\": \"tache courte\", \"volume_per_week\": nombre, \"minutes_per_unit\": nombre, "
        "\"repetitiveness\": entier 1-5, \"automatability\": entier 1-5, "
        "\"evidence\": \"la phrase exacte du site qui justifie cette tache, ou 'estimate'\"}}]}}. "
        "REGLE STRICTE : n'invente AUCUN volume ni duree. Si le site ne donne pas de chiffre pour une tache, "
        "mets volume_per_week=0 et minutes_per_unit=0 et evidence='estimate' (l'humain confirmera a la revue). "
        "Cherche les vraies operations dans le contenu : email/chat/telephone de support (ex. 'email us at x@y.com'), "
        "FAQ, politique de shipping/returns (ex. 'allow 1-3 business days to process'), tracking, retours, "
        "abandon de panier, paiement, e-commerce. Extrais 2-6 taches. "
        "Si rien d'operationnel n'est visible, renvoie tasks=[]. "
        "Ne reponds qu'avec le JSON.\n\nSite : {url}\n\nContenu des pages :\n{page}"
    ),
    "en": (
        "You are an operations analyst. You are given the content of several pages of a brand's website (markdown). "
        "Answer as JSON with this exact object: "
        "{{\"name\": \"brand name\", \"sector\": \"D2C|SaaS|Agency|Other\", "
        "\"team_size\": integer (do not invent: 0 if unknown), "
        "\"free_text\": \"factual description of the operations observed\", "
        "\"tasks\": [{{\"name\": \"short task\", \"volume_per_week\": number, \"minutes_per_unit\": number, "
        "\"repetitiveness\": integer 1-5, \"automatability\": integer 1-5, "
        "\"evidence\": \"the exact site sentence justifying this task, or 'estimate'\"}}]}}. "
        "STRICT RULE: do not invent any volume or duration. If the site gives no figure for a task, "
        "set volume_per_week=0 and minutes_per_unit=0 and evidence='estimate' (a human will confirm at review). "
        "Look for real operations in the content: support email/chat/phone (e.g. 'email us at x@y.com'), "
        "FAQ, shipping/returns policy (e.g. 'allow 1-3 business days to process'), tracking, returns, "
        "cart abandonment, payments, e-commerce. Extract 2-6 tasks. "
        "If nothing operational is visible, return tasks=[]. "
        "Respond with the JSON only.\n\nSite: {url}\n\nPage content:\n{page}"
    ),
}
