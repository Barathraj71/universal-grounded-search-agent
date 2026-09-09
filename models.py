from typing import Literal
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=5000)
    output_template: Literal[
        "balanced", "quick", "deep", "tutorial", "comparison", "summary"
    ] = "balanced"


class SearchResponse(BaseModel):
    answer: str
    route: list[str] = []
    intent: str
    grounded: bool
    confidence: str
    freshness: str
    sources: list[dict] = []
    follow_ups: list[str] = []
    related: list[str] = []
    activity: list[dict] = []
    duration_ms: int
    error: str | None = None
