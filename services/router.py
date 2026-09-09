import re
from prompts import ROUTER_PROMPT
from services.llm import ask_json

SOCIAL = [
    "what do people think", "opinions", "reviews", "review", "owner experience",
    "user experience", "complaints", "reddit", "community", "worth buying",
]
TECH = [
    "python", "javascript", "java", "react", "node", "sql", "api", "error",
    "exception", "debug", "bug", "code", "programming", "developer", "github",
]
WEATHER = ["weather", "forecast", "temperature", "rain", "wind", "humidity"]
FINANCE = ["stock", "share price", "share", "market price", "ticker", "nasdaq", "nyse"]


def deterministic(question: str):
    q = question.lower()
    if any(x in q for x in WEATHER):
        return ["weather"], "Weather/live forecast intent."
    if any(x in q for x in FINANCE):
        return ["finance"], "Current market/quote intent."
    if any(x in q for x in SOCIAL):
        return ["reddit"], "Opinion/review/community intent."
    if any(x in q for x in TECH):
        return ["stackexchange"], "Programming/technical intent."
    return ["web"], "General web-search fallback."


def classify(question: str):
    sources, reason = deterministic(question)
    llm = ask_json(
        ROUTER_PROMPT,
        question,
    )
    if llm and isinstance(llm.get("sources"), list):
        llm_sources = [x for x in llm["sources"] if x in {"reddit","stackexchange","weather","finance","web"}]
        # Deterministic specialized routes win when the wording is obvious.
        if sources == ["web"] and llm_sources:
            sources = llm_sources
            reason = "LLM intent classification selected the most relevant source(s)."
        elif sources != ["web"]:
            reason = "Deterministic high-confidence intent route selected."
        return {
            "sources": sources,
            "intent": llm.get("intent", "quick_answer"),
            "needs_freshness": bool(llm.get("needs_freshness", True)),
            "ambiguity": llm.get("ambiguity", "low"),
            "reformulation_needed": bool(llm.get("reformulation_needed", False)),
            "reason": reason,
        }

    q = question.lower()
    intent = "quick_answer"
    if "how do i" in q or q.startswith("how to") or "tutorial" in q:
        intent = "tutorial"
    elif "compare" in q or " vs " in q or "versus" in q:
        intent = "comparison"
    elif "deep dive" in q or "in detail" in q:
        intent = "deep_dive"
    elif "summary" in q or "summarize" in q:
        intent = "summary"
    elif "why" in q or "explain" in q:
        intent = "deep_dive"

    return {
        "sources": sources,
        "intent": intent,
        "needs_freshness": True,
        "ambiguity": "low",
        "reformulation_needed": False,
        "reason": reason,
    }
