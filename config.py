import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-oss-20b").strip()

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "").strip()
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
REDDIT_USER_AGENT = os.getenv(
    "REDDIT_USER_AGENT", "universal-grounded-search-agent/1.0"
).strip()

LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY", "").strip()
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
LANGSMITH_PROJECT = os.getenv(
    "LANGSMITH_PROJECT", "universal-grounded-search-agent"
).strip()

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "12"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "6"))


def configuration_status():
    return {
        "groq_configured": bool(GROQ_API_KEY),
        "reddit_configured": bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET),
        "langsmith_configured": bool(LANGSMITH_API_KEY and LANGSMITH_TRACING),
        "model": MODEL_NAME,
    }
