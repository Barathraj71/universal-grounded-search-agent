from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import configuration_status
from models import SearchRequest, SearchResponse
from agent import run_agent
from services.ranking import record


app = FastAPI(title="Universal Grounded Search Agent")

app.mount(
    "/static",
    StaticFiles(directory="frontend"),
    name="static"
)


@app.get("/")
def home():
    return FileResponse("frontend/index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config-status")
def config_status():
    return configuration_status()


@app.post("/api/search", response_model=SearchResponse)
def search(request: SearchRequest):

    try:
        result = run_agent(
            request.question,
            request.output_template
        )

        # Make sure route is always a list of strings.
        route = result.get("route", [])

        if isinstance(route, str):
            route = [route]

        if not isinstance(route, list):
            route = []

        route = [
            str(item)
            for item in route
            if item
        ]

        # Make sure sources are always dictionaries.
        raw_sources = result.get("sources", [])

        if not isinstance(raw_sources, list):
            raw_sources = []

        sources = []

        for source in raw_sources:

            if isinstance(source, dict):
                sources.append(source)

            elif isinstance(source, str):
                sources.append({
                    "source_id": "",
                    "type": source,
                    "title": source,
                    "url": "",
                    "content": "",
                    "retrieved_at": "",
                })

        # Make sure activity is always a list of dictionaries.
        raw_activity = result.get("activity", [])

        if not isinstance(raw_activity, list):
            raw_activity = []

        activity = []

        for item in raw_activity:

            if isinstance(item, dict):
                activity.append({
                    "message": str(item.get("message", "")),
                    "status": str(item.get("status", "done"))
                })

            elif isinstance(item, str):
                activity.append({
                    "message": item,
                    "status": "done"
                })

        # Make sure follow-ups and related are strings.
        follow_ups = result.get("follow_ups", [])

        if not isinstance(follow_ups, list):
            follow_ups = []

        follow_ups = [
            str(x)
            for x in follow_ups
            if isinstance(x, str)
        ][:3]

        related = result.get("related", [])

        if not isinstance(related, list):
            related = []

        related = [
            str(x)
            for x in related
            if isinstance(x, str)
        ][:3]

        return {
            "answer": str(result.get("answer", "")),
            "route": route,
            "intent": str(
                result.get("intent", "quick_answer")
            ),
            "grounded": bool(
                result.get("grounded", False)
            ),
            "confidence": str(
                result.get("confidence", "low")
            ),
            "freshness": str(
                result.get("freshness", "not verified")
            ),
            "sources": sources,
            "follow_ups": follow_ups,
            "related": related,
            "activity": activity,
            "duration_ms": int(
                result.get("duration_ms", 0)
            ),
            "error": result.get("error"),
        }

    except Exception as exc:

        print(
            f"SEARCH ERROR: {type(exc).__name__}: {exc}"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                f"Search failed: "
                f"{type(exc).__name__}: {exc}"
            )
        )


@app.post("/api/feedback")
def feedback(payload: dict):

    sources = payload.get("sources", [])
    helpful = bool(
        payload.get("helpful", False)
    )

    record(
        sources,
        helpful
    )

    return {
        "ok": True
    }