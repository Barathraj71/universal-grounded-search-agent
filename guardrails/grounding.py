import re

CITATION_RE = re.compile(r"\[(S\d+)\]")


def validate_citations(answer: str, evidence: list[dict]) -> bool:
    valid_ids = {str(x.get("source_id")) for x in evidence if x.get("content")}
    used_ids = set(CITATION_RE.findall(answer or ""))
    return bool(used_ids) and used_ids.issubset(valid_ids)


def build_source_block(evidence: list[dict]) -> str:
    return "\n\n".join(
        f"[{x.get('source_id')}] {x.get('type')}\n"
        f"Title: {x.get('title','')}\n"
        f"URL: {x.get('url','')}\n"
        f"Retrieved: {x.get('retrieved_at','')}\n"
        f"Content: {x.get('content','')}"
        for x in evidence
    )
