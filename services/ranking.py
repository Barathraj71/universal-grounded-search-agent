from collections import defaultdict

# Lightweight local preference model. It learns only from interaction events
# sent by the browser and is intentionally simple for an internship project.
_preferences = defaultdict(float)


def score_source(source_type: str) -> float:
    return _preferences[source_type]


def record(source_types: list[str], helpful: bool):
    delta = 1.0 if helpful else -0.5
    for source_type in source_types:
        _preferences[source_type] += delta


def rank(evidence: list[dict]) -> list[dict]:
    return sorted(
        evidence,
        key=lambda x: (
            float(x.get("relevance", 0)),
            score_source(x.get("type", "")),
        ),
        reverse=True,
    )
