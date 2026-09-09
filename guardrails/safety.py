import re

BLOCKED_PATTERNS = [
    r"\b(ignore|forget)\s+(all\s+)?(previous|prior)\s+instructions\b",
    r"\b(reveal|show|print|give)\s+(me\s+)?(your|the)\s+(system\s+prompt|api\s*key|secret|password|token|credential)\b",
    r"\b(steal|extract)\s+(an?\s+)?(api\s*key|password|token|credential)\b",
]

INJECTION_PATTERNS = [
    r"\b(ignore|forget)\s+(all\s+)?(previous|prior)\s+instructions\b",
    r"\b(reveal|show)\s+(your\s+)?(system\s+prompt|api\s*key|secret|password|token)\b",
    r"\b(system|developer)\s+(message|instruction)\b",
    r"\boverride\s+(the|all)\s+instructions\b",
]


def is_safe_question(question: str) -> bool:
    if not question or len(question.strip()) > 5000:
        return False
    return not any(re.search(p, question, re.I) for p in BLOCKED_PATTERNS)


def looks_like_injection(text: str) -> bool:
    if not text:
        return False
    return any(re.search(p, text, re.I) for p in INJECTION_PATTERNS)
