from datetime import datetime, timezone
import re
from urllib.parse import parse_qs, urlparse
import httpx
from bs4 import BeautifulSoup
import praw

from config import (
    CACHE_TTL,
    MAX_RESULTS,
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_USER_AGENT,
    REQUEST_TIMEOUT,
)
from guardrails.safety import looks_like_injection
from services.cache import get, put, key


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean_html(value: str) -> str:
    return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)


def _get(url, params=None):
    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        r = client.get(url, params=params, headers={"User-Agent": "UniversalGroundedSearch/1.0"})
        r.raise_for_status()
        return r


def web_search(query: str) -> list[dict]:
    ck = key("web", query)
    cached = get(ck, CACHE_TTL)
    if cached is not None:
        return cached

    r = _get(
        "https://html.duckduckgo.com/html/",
        params={"q": query, "kl": "in-en"},
    )
    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for a in soup.select("a.result__a")[:MAX_RESULTS]:
        title = a.get_text(" ", strip=True)
        url = a.get("href", "")
        if url.startswith("//"):
            url = "https:" + url
        try:
            parsed = urlparse(url)
            target = parse_qs(parsed.query).get("uddg", [None])[0]
            if target:
                url = target
        except Exception:
            pass
        parent = a.find_parent("div", class_="result")
        snippet = parent.select_one(".result__snippet").get_text(" ", strip=True) if parent and parent.select_one(".result__snippet") else ""
        content = f"{title}. {snippet}"
        if not url or looks_like_injection(content):
            continue
        results.append({
            "type": "web",
            "title": title,
            "url": url,
            "content": content[:3000],
            "retrieved_at": now_iso(),
            "relevance": 0.75,
        })
    put(ck, results)
    return results


def reddit_search(query: str) -> list[dict]:
    if not (REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET):
        return []

    ck = key("reddit", query)
    cached = get(ck, CACHE_TTL)
    if cached is not None:
        return cached

    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
        check_for_async=False,
    )
    results = []
    for post in reddit.subreddit("all").search(query, sort="relevance", limit=MAX_RESULTS):
        body = post.selftext or ""
        comments = []
        try:
            post.comments.replace_more(limit=0)
            comments = [
                c.body for c in post.comments.list()
                if getattr(c, "body", None)
            ][:3]
        except Exception:
            pass
        content = f"{body} " + " ".join(comments)
        if looks_like_injection(content):
            continue
        results.append({
            "type": "reddit",
            "title": post.title,
            "url": f"https://www.reddit.com{post.permalink}",
            "content": content[:3500],
            "retrieved_at": now_iso(),
            "relevance": 0.90,
        })
    put(ck, results)
    return results


def stackexchange_search(query: str) -> list[dict]:
    ck = key("stackexchange", query)
    cached = get(ck, CACHE_TTL)
    if cached is not None:
        return cached

    data = _get(
        "https://api.stackexchange.com/2.3/search/advanced",
        params={
            "site": "stackoverflow",
            "q": query,
            "order": "desc",
            "sort": "relevance",
            "filter": "withbody",
            "pagesize": MAX_RESULTS,
        },
    ).json()

    results = []
    for item in data.get("items", []):
        body = clean_html(item.get("body", ""))
        if looks_like_injection(body):
            continue
        results.append({
            "type": "stackexchange",
            "title": clean_html(item.get("title", "")),
            "url": item.get("link", ""),
            "content": body[:3500],
            "retrieved_at": now_iso(),
            "relevance": 0.88,
        })
    put(ck, results)
    return results


def weather_search(query: str) -> list[dict]:
    ck = key("weather", query)
    cached = get(ck, CACHE_TTL)
    if cached is not None:
        return cached

    location = query
    match = re.search(
        r"\b(?:in|at|near|for)\s+([A-Za-z][A-Za-z .-]{1,80}?)(?:\s+(?:today|tomorrow|now|this week|tonight))?\s*$",
        query,
        re.I,
    )
    if match:
        location = match.group(1).strip()
    else:
        location = re.sub(
            r"\b(weather|forecast|temperature|rain|wind|humidity)\b",
            " ",
            query,
            flags=re.I,
        )
        location = re.sub(
            r"\b(today|tomorrow|now|tonight|this week)\b",
            " ",
            location,
            flags=re.I,
        ).strip(" ?.,")
    geo = _get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": location, "count": 1, "language": "en", "format": "json"},
    ).json()
    place = (geo.get("results") or [None])[0]
    if not place:
        return []

    data = _get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,wind_speed_10m,weather_code",
            "timezone": "auto",
        },
    ).json()
    current = data.get("current", {})
    content = (
        f"Current weather for {place.get('name')}, {place.get('country')}: "
        f"temperature {current.get('temperature_2m')} {data.get('current_units',{}).get('temperature_2m','')}; "
        f"feels like {current.get('apparent_temperature')}; "
        f"humidity {current.get('relative_humidity_2m')}%; "
        f"precipitation {current.get('precipitation')}; "
        f"wind {current.get('wind_speed_10m')}."
    )
    results = [{
        "type": "weather",
        "title": f"Open-Meteo current weather — {place.get('name')}",
        "url": "https://open-meteo.com/",
        "content": content,
        "retrieved_at": now_iso(),
        "relevance": 0.95,
    }]
    put(ck, results)
    return results


def finance_search(query: str) -> list[dict]:
    symbol_map = {
        "tata steel": "TATASTEEL.NS",
        "reliance": "RELIANCE.NS",
        "reliance industries": "RELIANCE.NS",
        "infosys": "INFY.NS",
        "tcs": "TCS.NS",
        "hdfc bank": "HDFCBANK.NS",
        "icici bank": "ICICIBANK.NS",
        "apple": "AAPL",
        "microsoft": "MSFT",
        "tesla": "TSLA",
        "amazon": "AMZN",
        "nvidia": "NVDA",
    }
    q = query.lower()
    symbol = next((v for k, v in symbol_map.items() if k in q), None)
    if not symbol:
        match = re.search(r"\b[A-Z]{1,6}(?:\.NS)?\b", query)
        symbol = match.group(0) if match else None
    if not symbol:
        return []

    ck = key("finance", symbol)
    cached = get(ck, CACHE_TTL)
    if cached is not None:
        return cached

    data = _get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"range": "1d", "interval": "1m"},
    ).json()
    result = data.get("chart", {}).get("result", [None])[0]
    if not result:
        return []
    meta = result.get("meta", {})
    price = meta.get("regularMarketPrice")
    previous = meta.get("previousClose")
    change = (price - previous) if price is not None and previous is not None else None
    currency = meta.get("currency", "")
    content = (
        f"Latest retrieved quote for {symbol}: {price} {currency}; "
        f"previous close {previous}; change {change}; "
        f"exchange {meta.get('exchangeName')}; market state {meta.get('marketState')}. "
        "This is a current/latest quote, not a future-price prediction."
    )
    results = [{
        "type": "finance",
        "title": f"Yahoo Finance quote — {symbol}",
        "url": f"https://finance.yahoo.com/quote/{symbol}",
        "content": content,
        "retrieved_at": now_iso(),
        "relevance": 0.95,
    }]
    put(ck, results)
    return results
