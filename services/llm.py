import json
from groq import Groq
from config import GROQ_API_KEY, MODEL_NAME

_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


def available() -> bool:
    return _client is not None


def ask_json(system: str, user: str):
    if not _client:
        return None

    try:
        response = _client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

        content = response.choices[0].message.content

        if not content:
            return None

        return json.loads(content)

    except Exception as exc:
        print(f"LLM JSON error: {type(exc).__name__}: {exc}")
        return None


def ask_text(system: str, user: str):
    if not _client:
        return None

    try:
        response = _client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

        content = response.choices[0].message.content

        if not content:
            return None

        return content.strip()

    except Exception as exc:
        print(f"LLM text error: {type(exc).__name__}: {exc}")
        return None