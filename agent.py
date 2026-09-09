import time
from typing import TypedDict

from langgraph.graph import StateGraph, END

from guardrails.grounding import (
    build_source_block,
    validate_citations,
)
from guardrails.safety import is_safe_question

from prompts import (
    ANSWER_PROMPT,
    FOLLOWUP_PROMPT,
    REFORMULATE_PROMPT,
    RELATED_PROMPT,
)

from services.llm import (
    ask_json,
    ask_text,
)

from services.providers import (
    finance_search,
    reddit_search,
    stackexchange_search,
    weather_search,
    web_search,
)

from services.ranking import rank


# ---------------------------------------------------------
# Optional LangSmith tracing
# ---------------------------------------------------------

try:
    from langsmith import traceable
except Exception:

    def traceable(function):
        return function


# ---------------------------------------------------------
# State
# ---------------------------------------------------------

class State(TypedDict, total=False):
    question: str
    output_template: str

    safe: bool

    route: list[str]
    sources: list[dict]

    intent: str
    ambiguity: str

    reformulated_queries: list[str]

    evidence: list[dict]

    answer: str
    grounded: bool

    confidence: str
    freshness: str

    follow_ups: list[str]
    related: list[str]

    activity: list[dict]

    error: str | None

    duration_ms: int


# ---------------------------------------------------------
# Activity helper
# ---------------------------------------------------------

def activity(message, status="done"):
    return {
        "message": str(message),
        "status": str(status),
    }


# ---------------------------------------------------------
# Safety node
# ---------------------------------------------------------

def safety_node(state: State):

    question = state.get("question", "").strip()

    state["activity"] = [
        activity("Checking the question for safety.")
    ]

    if not question:

        state["safe"] = False
        state["error"] = "Please enter a question."

        state["activity"].append(
            activity(
                "Question is empty.",
                "blocked"
            )
        )

        return state

    safe = is_safe_question(question)

    state["safe"] = safe

    if safe:

        state["activity"].append(
            activity(
                "Question passed the safety check."
            )
        )

    else:

        state["error"] = (
            "I can't help with requests to reveal "
            "credentials, secrets, or internal instructions."
        )

        state["activity"].append(
            activity(
                "Question blocked by the safety guardrail.",
                "blocked"
            )
        )

    return state


# ---------------------------------------------------------
# Intent + routing node
# ---------------------------------------------------------

def intent_node(state: State):

    if not state.get("safe"):
        return state

    from services.router import classify

    try:

        info = classify(
            state["question"]
        )

    except Exception as exc:

        # Universal fallback.
        info = {
            "sources": ["web"],
            "intent": "quick_answer",
            "ambiguity": "medium",
        }

        state["activity"].append(
            activity(
                f"Router fallback activated: "
                f"{type(exc).__name__}.",
                "warning"
            )
        )

    sources = info.get(
        "sources",
        ["web"]
    )

    if isinstance(sources, str):
        sources = [sources]

    sources = [
        str(source)
        for source in sources
        if source
    ]

    if not sources:
        sources = ["web"]

    state["route"] = sources

    state["intent"] = str(
        info.get(
            "intent",
            "quick_answer"
        )
    )

    state["ambiguity"] = str(
        info.get(
            "ambiguity",
            "low"
        )
    )

    state["activity"].append(
        activity(
            f"Intent detected: {state['intent']}."
        )
    )

    state["activity"].append(
        activity(
            "Search route selected: "
            + ", ".join(sources)
            + "."
        )
    )

    return state


# ---------------------------------------------------------
# Query reformulation node
# ---------------------------------------------------------

def reformulate_node(state: State):

    if not state.get("safe"):
        return state

    question = state["question"]

    queries = [question]

    if state.get("ambiguity") == "high":

        try:

            result = ask_json(
                REFORMULATE_PROMPT,
                question
            )

            if result:

                raw_queries = result.get(
                    "queries",
                    []
                )

                if isinstance(
                    raw_queries,
                    list
                ):

                    valid_queries = [
                        str(query).strip()
                        for query in raw_queries
                        if isinstance(
                            query,
                            str
                        )
                        and query.strip()
                    ]

                    if valid_queries:

                        queries = valid_queries[:3]

                        state["activity"].append(
                            activity(
                                "Reformulated the query "
                                "to improve retrieval."
                            )
                        )

        except Exception as exc:

            state["activity"].append(
                activity(
                    f"Query reformulation failed: "
                    f"{type(exc).__name__}. "
                    f"Using the original question.",
                    "warning"
                )
            )

    state["reformulated_queries"] = queries

    return state


# ---------------------------------------------------------
# Retrieval node
# ---------------------------------------------------------

def retrieve_node(state: State):

    if not state.get("safe"):
        return state

    evidence = []

    seen_urls = set()

    def add(items):

        if not isinstance(items, list):
            return

        for item in items:

            if not isinstance(item, dict):
                continue

            url = str(
                item.get(
                    "url",
                    ""
                )
            ).strip()

            title = str(
                item.get(
                    "title",
                    ""
                )
            ).strip()

            content = str(
                item.get(
                    "content",
                    ""
                )
            ).strip()

            if not content:
                continue

            # Use URL for deduplication when available.
            # If no URL exists, use title + content.
            unique_key = (
                url
                if url
                else f"{title}|{content[:200]}"
            )

            if unique_key in seen_urls:
                continue

            seen_urls.add(unique_key)

            evidence.append(item)

    queries = state.get(
        "reformulated_queries",
        [state["question"]]
    )

    routes = state.get(
        "route",
        ["web"]
    )

    # -----------------------------------------------------
    # Search each query against each selected provider
    # -----------------------------------------------------

    for query in queries:

        for source in routes:

            try:

                if source == "reddit":

                    state["activity"].append(
                        activity(
                            "Searching Reddit."
                        )
                    )

                    add(
                        reddit_search(query)
                    )

                elif source == "stackexchange":

                    state["activity"].append(
                        activity(
                            "Searching Stack Exchange."
                        )
                    )

                    add(
                        stackexchange_search(query)
                    )

                elif source == "weather":

                    state["activity"].append(
                        activity(
                            "Fetching live weather data."
                        )
                    )

                    add(
                        weather_search(query)
                    )

                elif source == "finance":

                    state["activity"].append(
                        activity(
                            "Fetching the latest market quote."
                        )
                    )

                    add(
                        finance_search(query)
                    )

                elif source == "web":

                    state["activity"].append(
                        activity(
                            "Searching the open web."
                        )
                    )

                    add(
                        web_search(query)
                    )

            except Exception as exc:

                state["activity"].append(
                    activity(
                        f"{source} search failed: "
                        f"{type(exc).__name__}.",
                        "warning"
                    )
                )

    # -----------------------------------------------------
    # Universal fallback
    # -----------------------------------------------------

    if not evidence and "web" not in routes:

        state["activity"].append(
            activity(
                "Specialized sources returned no usable "
                "evidence; trying general web search.",
                "warning"
            )
        )

        try:

            add(
                web_search(
                    state["question"]
                )
            )

        except Exception as exc:

            state["activity"].append(
                activity(
                    f"General web fallback failed: "
                    f"{type(exc).__name__}.",
                    "warning"
                )
            )

    # -----------------------------------------------------
    # Rank evidence
    # -----------------------------------------------------

    try:

        evidence = rank(
            evidence
        )[:10]

    except Exception as exc:

        state["activity"].append(
            activity(
                f"Evidence ranking failed: "
                f"{type(exc).__name__}.",
                "warning"
            )
        )

        evidence = evidence[:10]

    # -----------------------------------------------------
    # Assign source IDs
    # -----------------------------------------------------

    for index, item in enumerate(
        evidence,
        start=1
    ):

        item["source_id"] = (
            f"S{index}"
        )

    state["evidence"] = evidence

    # IMPORTANT:
    # sources must contain dictionaries,
    # not strings such as "web".
    state["sources"] = evidence

    if evidence:

        state["activity"].append(
            activity(
                f"Found {len(evidence)} "
                f"usable evidence item(s)."
            )
        )

    else:

        state["activity"].append(
            activity(
                "No usable evidence was found.",
                "warning"
            )
        )

    return state


# ---------------------------------------------------------
# Answer generation node
# ---------------------------------------------------------

def answer_node(state: State):

    if not state.get("safe"):
        return state

    evidence = state.get(
        "evidence",
        []
    )

    # -----------------------------------------------------
    # No evidence
    # -----------------------------------------------------

    if not evidence:

        state["answer"] = (
            "I couldn't find reliable live evidence "
            "for this question right now. Try "
            "rephrasing the question or making "
            "the target more specific."
        )

        state["grounded"] = False
        state["confidence"] = "low"
        state["freshness"] = "not verified"

        state["activity"].append(
            activity(
                "No grounded answer could be produced.",
                "warning"
            )
        )

        return state

    # -----------------------------------------------------
    # Build LLM prompt
    # -----------------------------------------------------

    source_block = build_source_block(
        evidence
    )

    prompt = (
        f"User question: "
        f"{state['question']}\n\n"

        f"Requested output template: "
        f"{state.get('output_template', 'balanced')}\n\n"

        f"Intent: "
        f"{state.get('intent', 'quick_answer')}\n\n"

        f"Evidence:\n"
        f"{source_block}"
    )

    # -----------------------------------------------------
    # Ask LLM
    # -----------------------------------------------------

    answer = None

    try:

        answer = ask_text(
            ANSWER_PROMPT,
            prompt
        )

    except Exception as exc:

        state["activity"].append(
            activity(
                f"LLM answer generation failed: "
                f"{type(exc).__name__}.",
                "warning"
            )
        )

    # -----------------------------------------------------
    # Conservative fallback
    # -----------------------------------------------------

    if not answer:

        top = evidence[0]

        title = str(
            top.get(
                "title",
                "Retrieved result"
            )
        )

        content = str(
            top.get(
                "content",
                ""
            )
        )

        answer = (
            "Based on the retrieved evidence, "
            f"the most relevant result is "
            f"“{title}”.\n\n"
            f"{content[:900]}\n\n"
            "[S1]"
        )

    state["answer"] = answer

    # -----------------------------------------------------
    # Validate grounding
    # -----------------------------------------------------

    try:

        grounded = validate_citations(
            answer,
            evidence
        )

    except Exception as exc:

        grounded = False

        state["activity"].append(
            activity(
                f"Citation validation failed: "
                f"{type(exc).__name__}.",
                "warning"
            )
        )

    state["grounded"] = grounded

    if grounded:

        if len(evidence) >= 3:
            state["confidence"] = "high"

        else:
            state["confidence"] = "medium"

    else:

        state["confidence"] = "low"

    state["freshness"] = (
        "verified just now"
        if evidence
        else "not verified"
    )

    state["activity"].append(
        activity(
            "Synthesized the answer "
            "from retrieved evidence."
        )
    )

    return state


# ---------------------------------------------------------
# Citation validation / repair node
# ---------------------------------------------------------

def citation_node(state: State):

    if not state.get("safe"):
        return state

    evidence = state.get(
        "evidence",
        []
    )

    if (
        not state.get("grounded")
        and evidence
    ):

        repair_prompt = (
            f"Question: "
            f"{state['question']}\n\n"

            f"Draft answer: "
            f"{state.get('answer', '')}\n\n"

            f"Evidence:\n"
            f"{build_source_block(evidence)}\n\n"

            "Rewrite the answer so every factual "
            "claim is supported by a valid [S#] "
            "citation. Do not add unsupported facts."
        )

        repaired = None

        try:

            repaired = ask_text(
                ANSWER_PROMPT,
                repair_prompt
            )

        except Exception as exc:

            state["activity"].append(
                activity(
                    f"Citation repair failed: "
                    f"{type(exc).__name__}.",
                    "warning"
                )
            )

        if repaired:

            try:

                valid = validate_citations(
                    repaired,
                    evidence
                )

            except Exception:

                valid = False

            if valid:

                state["answer"] = repaired
                state["grounded"] = True
                state["confidence"] = "medium"

                state["activity"].append(
                    activity(
                        "Rechecked and repaired "
                        "source citations."
                    )
                )

            else:

                state["activity"].append(
                    activity(
                        "Citation verification "
                        "remained uncertain.",
                        "warning"
                    )
                )

        else:

            state["activity"].append(
                activity(
                    "Citation repair produced "
                    "no usable answer.",
                    "warning"
                )
            )

    return state


# ---------------------------------------------------------
# Follow-up + related discovery node
# ---------------------------------------------------------

def engagement_node(state: State):

    if not state.get("safe"):
        return state

    evidence = state.get(
        "evidence",
        []
    )

    context = (
        f"Question: "
        f"{state['question']}\n\n"

        f"Answer: "
        f"{state.get('answer', '')[:4000]}\n\n"

        f"Evidence: "
        f"{build_source_block(evidence[:5])}"
    )

    follow_result = None
    related_result = None

    # -----------------------------------------------------
    # Follow-ups
    # -----------------------------------------------------

    try:

        follow_result = ask_json(
            FOLLOWUP_PROMPT,
            context
        )

    except Exception as exc:

        state["activity"].append(
            activity(
                f"Follow-up generation failed: "
                f"{type(exc).__name__}.",
                "warning"
            )
        )

    # -----------------------------------------------------
    # Related discovery
    # -----------------------------------------------------

    try:

        related_result = ask_json(
            RELATED_PROMPT,
            context
        )

    except Exception as exc:

        state["activity"].append(
            activity(
                f"Related discovery failed: "
                f"{type(exc).__name__}.",
                "warning"
            )
        )

    # -----------------------------------------------------
    # Clean follow-ups
    # -----------------------------------------------------

    raw_followups = (
        follow_result or {}
    ).get(
        "follow_ups",
        []
    )

    if not isinstance(
        raw_followups,
        list
    ):
        raw_followups = []

    state["follow_ups"] = [
        str(item).strip()
        for item in raw_followups
        if isinstance(item, str)
        and item.strip()
    ][:3]

    # -----------------------------------------------------
    # Clean related results
    # -----------------------------------------------------

    raw_related = (
        related_result or {}
    ).get(
        "related",
        []
    )

    if not isinstance(
        raw_related,
        list
    ):
        raw_related = []

    state["related"] = [
        str(item).strip()
        for item in raw_related
        if isinstance(item, str)
        and item.strip()
    ][:3]

    # -----------------------------------------------------
    # Safe fallback suggestions
    # -----------------------------------------------------

    if not state["follow_ups"]:

        state["follow_ups"] = [
            "What are the most important details behind this answer?",
            "What are the main alternatives or trade-offs?",
            "Can you show me the latest evidence for this?",
        ]

    if not state["related"]:

        state["related"] = [
            "Explore a closely related topic",
            "Compare the main alternatives",
            "Check how this has changed recently",
        ]

    return state


# ---------------------------------------------------------
# Routing after safety
# ---------------------------------------------------------

def route_after_safety(state: State):

    if state.get("safe"):
        return "intent"

    return "end"


# ---------------------------------------------------------
# Build LangGraph
# ---------------------------------------------------------

def build_graph():

    graph = StateGraph(
        State
    )

    graph.add_node(
        "safety",
        safety_node
    )

    graph.add_node(
        "intent",
        intent_node
    )

    graph.add_node(
        "reformulate",
        reformulate_node
    )

    graph.add_node(
        "retrieve",
        retrieve_node
    )

    graph.add_node(
        "answer",
        answer_node
    )

    graph.add_node(
        "citation",
        citation_node
    )

    graph.add_node(
        "engagement",
        engagement_node
    )

    graph.set_entry_point(
        "safety"
    )

    graph.add_conditional_edges(
        "safety",
        route_after_safety,
        {
            "intent": "intent",
            "end": END,
        }
    )

    graph.add_edge(
        "intent",
        "reformulate"
    )

    graph.add_edge(
        "reformulate",
        "retrieve"
    )

    graph.add_edge(
        "retrieve",
        "answer"
    )

    graph.add_edge(
        "answer",
        "citation"
    )

    graph.add_edge(
        "citation",
        "engagement"
    )

    graph.add_edge(
        "engagement",
        END
    )

    return graph.compile()


# ---------------------------------------------------------
# Create graph
# ---------------------------------------------------------

GRAPH = build_graph()


# ---------------------------------------------------------
# Main agent function
# ---------------------------------------------------------

@traceable
def run_agent(
    question: str,
    output_template: str = "balanced"
):

    started = time.perf_counter()

    # -----------------------------------------------------
    # Normalize input
    # -----------------------------------------------------

    question = (
        question
        if isinstance(question, str)
        else str(question or "")
    ).strip()

    # -----------------------------------------------------
    # Run graph safely
    # -----------------------------------------------------

    try:

        state = GRAPH.invoke(
            {
                "question": question,
                "output_template": output_template,
                "activity": [],
                "error": None,
            }
        )

    except Exception as exc:

        print(
            f"AGENT ERROR: "
            f"{type(exc).__name__}: {exc}"
        )

        state = {
            "question": question,

            "output_template": output_template,

            "answer": (
                "I couldn't complete the search "
                "because one of the research services "
                "failed. Please try again."
            ),

            "route": ["web"],

            "intent": "quick_answer",

            "ambiguity": "unknown",

            "reformulated_queries": [
                question
            ] if question else [],

            "grounded": False,

            "confidence": "low",

            "freshness": "not verified",

            "sources": [],

            "evidence": [],

            "follow_ups": [],

            "related": [],

            "activity": [
                activity(
                    "Search service encountered an error.",
                    "warning"
                ),
                activity(
                    f"{type(exc).__name__}: {exc}",
                    "warning"
                ),
            ],

            "error": str(exc),
        }

    # -----------------------------------------------------
    # Guarantee expected fields
    # -----------------------------------------------------

    state.setdefault(
        "route",
        []
    )

    state.setdefault(
        "sources",
        []
    )

    state.setdefault(
        "evidence",
        []
    )

    state.setdefault(
        "follow_ups",
        []
    )

    state.setdefault(
        "related",
        []
    )

    state.setdefault(
        "answer",
        ""
    )

    state.setdefault(
        "grounded",
        False
    )

    state.setdefault(
        "confidence",
        "low"
    )

    state.setdefault(
        "freshness",
        "not verified"
    )

    state.setdefault(
        "activity",
        []
    )

    state.setdefault(
        "error",
        None
    )

    # -----------------------------------------------------
    # Normalize route
    # -----------------------------------------------------

    if isinstance(
        state["route"],
        str
    ):

        state["route"] = [
            state["route"]
        ]

    if not isinstance(
        state["route"],
        list
    ):

        state["route"] = []

    state["route"] = [
        str(item)
        for item in state["route"]
        if item
    ]

    # -----------------------------------------------------
    # Normalize sources
    # -----------------------------------------------------

    if not isinstance(
        state["sources"],
        list
    ):

        state["sources"] = []

    clean_sources = []

    for source in state["sources"]:

        if isinstance(
            source,
            dict
        ):

            clean_sources.append(
                source
            )

    state["sources"] = clean_sources

    # -----------------------------------------------------
    # Normalize activity
    # -----------------------------------------------------

    if not isinstance(
        state["activity"],
        list
    ):

        state["activity"] = []

    clean_activity = []

    for item in state["activity"]:

        if isinstance(
            item,
            dict
        ):

            clean_activity.append(
                {
                    "message": str(
                        item.get(
                            "message",
                            ""
                        )
                    ),
                    "status": str(
                        item.get(
                            "status",
                            "done"
                        )
                    ),
                }
            )

        elif isinstance(
            item,
            str
        ):

            clean_activity.append(
                activity(item)

            )

    state["activity"] = clean_activity

    # -----------------------------------------------------
    # Normalize follow-ups
    # -----------------------------------------------------

    if not isinstance(
        state["follow_ups"],
        list
    ):

        state["follow_ups"] = []

    state["follow_ups"] = [
        str(item)
        for item in state["follow_ups"]
        if isinstance(item, str)
    ][:3]

    # -----------------------------------------------------
    # Normalize related
    # -----------------------------------------------------

    if not isinstance(
        state["related"],
        list
    ):

        state["related"] = []

    state["related"] = [
        str(item)
        for item in state["related"]
        if isinstance(item, str)
    ][:3]

    # -----------------------------------------------------
    # Duration
    # -----------------------------------------------------

    state["duration_ms"] = int(
        (
            time.perf_counter()
            - started
        ) * 1000
    )

    return state