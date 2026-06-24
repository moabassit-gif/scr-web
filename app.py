from __future__ import annotations

import json
import os
import hashlib
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, HttpUrl
from dotenv import load_dotenv


load_dotenv()
app = FastAPI(title="Article JSON Extractor")


class ExtractRequest(BaseModel):
    url: HttpUrl


class ArticleResponse(BaseModel):
    author: Optional[str]
    title: Optional[str]
    content: str
    website_url: str


class KeyRemaining(BaseModel):
    index: int
    key: str
    used: str
    remaining: str


class ArticleJsonResponse(BaseModel):
    url: str
    content: str
    keyword: list[str]
    author: Optional[str]
    published_date: Optional[str]
    keys: list[KeyRemaining]


class SearchResult(BaseModel):
    title: str
    link: str
    snippet: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    provider: str
    cached: bool
    results: list[SearchResult]
    articles: Optional[list[ArticleResponse]] = None


class SerperKeyUsage(BaseModel):
    index: int
    key: str
    used: int
    remaining: int
    monthly_limit: int


class SearchUsageResponse(BaseModel):
    month: str
    provider: str
    keys: list[SerperKeyUsage]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}
GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
SERPER_SEARCH_URL = "https://google.serper.dev/search"
SEARCH_CACHE_FILE = Path(os.getenv("TEMP", ".")) / "scr_web_search_cache.json"
SERPER_USAGE_FILE = Path(os.getenv("TEMP", ".")) / "scr_web_serper_usage.json"
SEARCH_CACHE_TTL_SECONDS = 6 * 60 * 60
SERPER_MONTHLY_LIMIT = int(os.getenv("SERPER_MONTHLY_LIMIT", "2500"))
SERPER_REQUESTS_PER_SECOND = float(os.getenv("SERPER_REQUESTS_PER_SECOND", "2"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
SERPER_RATE_LOCK = threading.Lock()
SERPER_LAST_REQUEST_AT = 0.0


def first_meta_content(soup: BeautifulSoup, selectors: list[tuple[str, str]]) -> Optional[str]:
    for attr, value in selectors:
        tag = soup.find("meta", attrs={attr: value})
        if tag and tag.get("content"):
            return clean_text(tag["content"])
    return None


def clean_text(value: str) -> str:
    return " ".join(value.split())


def extract_title(soup: BeautifulSoup) -> Optional[str]:
    title = first_meta_content(
        soup,
        [
            ("property", "og:title"),
            ("name", "twitter:title"),
            ("name", "title"),
        ],
    )
    if title:
        return title
    if soup.title and soup.title.string:
        return clean_text(soup.title.string)
    heading = soup.find("h1")
    return clean_text(heading.get_text(" ", strip=True)) if heading else None


def extract_author(soup: BeautifulSoup) -> Optional[str]:
    author = first_meta_content(
        soup,
        [
            ("name", "author"),
            ("property", "article:author"),
            ("name", "twitter:creator"),
            ("property", "book:author"),
        ],
    )
    if author:
        return author

    author_node = soup.find(attrs={"rel": "author"}) or soup.find(
        attrs={"class": lambda value: value and "author" in value.lower()}
    )
    if author_node:
        text = clean_text(author_node.get_text(" ", strip=True))
        return text or None
    return None


def extract_keywords(soup: BeautifulSoup) -> list[str]:
    keywords = []
    meta_keywords = first_meta_content(
        soup,
        [
            ("name", "keywords"),
            ("property", "article:tag"),
            ("name", "news_keywords"),
        ],
    )
    if meta_keywords:
        keywords.extend([item.strip() for item in meta_keywords.split(",") if item.strip()])

    for tag in soup.find_all("meta", attrs={"property": "article:tag"}):
        value = tag.get("content")
        if value:
            keywords.append(clean_text(value))

    return list(dict.fromkeys(keywords))


def find_json_ld_values(data: Any, keys: set[str]) -> list[str]:
    values = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key in keys and isinstance(value, str):
                values.append(value)
            else:
                values.extend(find_json_ld_values(value, keys))
    elif isinstance(data, list):
        for item in data:
            values.extend(find_json_ld_values(item, keys))
    return values


def extract_published_date(soup: BeautifulSoup) -> Optional[str]:
    published_date = first_meta_content(
        soup,
        [
            ("property", "article:published_time"),
            ("name", "pubdate"),
            ("name", "publishdate"),
            ("name", "date"),
            ("itemprop", "datePublished"),
        ],
    )
    if published_date:
        return published_date

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        values = find_json_ld_values(data, {"datePublished", "dateCreated"})
        if values:
            return clean_text(values[0])

    time_node = soup.find("time")
    if time_node:
        return time_node.get("datetime") or clean_text(time_node.get_text(" ", strip=True))
    return None


def remove_noise(soup: BeautifulSoup) -> None:
    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer", "aside"]):
        tag.decompose()


def extract_content(soup: BeautifulSoup) -> str:
    remove_noise(soup)
    article = soup.find("article") or soup.find("main") or soup.body
    if not article:
        return ""

    paragraphs = []
    for node in article.find_all(["p", "h2", "h3", "li"]):
        text = clean_text(node.get_text(" ", strip=True))
        if len(text) >= 30:
            paragraphs.append(text)

    if paragraphs:
        return "\n\n".join(dict.fromkeys(paragraphs))

    return clean_text(article.get_text(" ", strip=True))


def normalize_website_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def load_search_cache() -> dict:
    if not SEARCH_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(SEARCH_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_search_cache(cache: dict) -> None:
    SEARCH_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SEARCH_CACHE_FILE.exists():
        SEARCH_CACHE_FILE.touch()
    SEARCH_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=True, indent=2), encoding="utf-8")


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def load_serper_usage() -> dict:
    if not SERPER_USAGE_FILE.exists():
        return {"month": current_month(), "keys": {}}
    try:
        usage = json.loads(SERPER_USAGE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"month": current_month(), "keys": {}}
    if usage.get("month") != current_month():
        return {"month": current_month(), "keys": {}}
    usage.setdefault("keys", {})
    return usage


def save_serper_usage(usage: dict) -> None:
    SERPER_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SERPER_USAGE_FILE.write_text(json.dumps(usage, ensure_ascii=True, indent=2), encoding="utf-8")


def key_id(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def mask_key(api_key: str) -> str:
    if len(api_key) <= 10:
        return "*" * len(api_key)
    return f"{api_key[:6]}...{api_key[-4:]}"


def get_serper_key_used(api_key: str) -> int:
    usage = load_serper_usage()
    return int(usage["keys"].get(key_id(api_key), {}).get("used", 0))


def increment_serper_key_usage(api_key: str) -> None:
    usage = load_serper_usage()
    item = usage["keys"].setdefault(key_id(api_key), {"used": 0, "masked": mask_key(api_key)})
    item["used"] = int(item.get("used", 0)) + 1
    item["masked"] = mask_key(api_key)
    save_serper_usage(usage)


def build_serper_usage_response() -> SearchUsageResponse:
    usage = load_serper_usage()
    keys = []
    for index, api_key in enumerate(get_serper_keys(), start=1):
        used = int(usage["keys"].get(key_id(api_key), {}).get("used", 0))
        keys.append(
            SerperKeyUsage(
                index=index,
                key=mask_key(api_key),
                used=used,
                remaining=max(SERPER_MONTHLY_LIMIT - used, 0),
                monthly_limit=SERPER_MONTHLY_LIMIT,
            )
        )
    return SearchUsageResponse(month=usage["month"], provider="serper", keys=keys)


def build_key_remaining() -> list[KeyRemaining]:
    usage = load_serper_usage()
    keys = []
    for index, api_key in enumerate(get_serper_keys(), start=1):
        used_count = int(usage["keys"].get(key_id(api_key), {}).get("used", 0))
        remaining_count = max(SERPER_MONTHLY_LIMIT - used_count, 0)
        keys.append(
            KeyRemaining(
                index=index,
                key=mask_key(api_key),
                used=f"{used_count}/{SERPER_MONTHLY_LIMIT}",
                remaining=f"{remaining_count}/{SERPER_MONTHLY_LIMIT}",
            )
        )
    return keys


def wait_for_serper_rate_limit() -> None:
    global SERPER_LAST_REQUEST_AT
    if SERPER_REQUESTS_PER_SECOND <= 0:
        return

    min_interval = 1 / SERPER_REQUESTS_PER_SECOND
    with SERPER_RATE_LOCK:
        now = time.monotonic()
        wait_for = SERPER_LAST_REQUEST_AT + min_interval - now
        if wait_for > 0:
            time.sleep(wait_for)
            now = time.monotonic()
        SERPER_LAST_REQUEST_AT = now


def get_serper_keys() -> list[str]:
    keys = os.getenv("SERPER_API_KEYS") or os.getenv("SERPER_API_KEY") or ""
    return [key.strip() for key in keys.split(",") if key.strip()]


def get_search_provider() -> str:
    if get_serper_keys():
        return "serper"
    if os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_CSE_ID"):
        return "google"
    raise HTTPException(status_code=500, detail="Set SERPER_API_KEY or SERPER_API_KEYS in .env before using /search")


def search_web(query: str, limit: int, country: Optional[str] = None) -> tuple[list[SearchResult], bool, str]:
    provider = get_search_provider()
    country_key = (country or "").strip().lower()
    cache_key = f"{provider}::{query.strip().lower()}::{limit}::{country_key}"
    cache = load_search_cache()
    cached_item = cache.get(cache_key)
    now = time.time()

    if cached_item and now - cached_item.get("created_at", 0) < SEARCH_CACHE_TTL_SECONDS:
        return [SearchResult(**item) for item in cached_item["results"]], True, provider

    if provider == "serper":
        results = serper_search(query, limit, country)
    else:
        results = google_search(query, limit)

    cache[cache_key] = {
        "created_at": now,
        "results": [result.model_dump() for result in results],
    }
    save_search_cache(cache)
    return results, False, provider


def serper_payload(query: str, limit: int, country: Optional[str] = None) -> dict:
    payload = {"q": query, "num": limit}
    if country:
        payload["gl"] = country.strip().lower()
    return payload


def serper_search(query: str, limit: int, country: Optional[str] = None) -> list[SearchResult]:
    api_keys = get_serper_keys()
    if not api_keys:
        raise HTTPException(status_code=500, detail="Set SERPER_API_KEY or SERPER_API_KEYS in .env before using /search")

    last_error = "Serper API failed"
    for index, api_key in enumerate(api_keys, start=1):
        if get_serper_key_used(api_key) >= SERPER_MONTHLY_LIMIT:
            last_error = f"Serper API key #{index} reached local monthly limit"
            continue
        try:
            wait_for_serper_rate_limit()
            response = requests.post(
                SERPER_SEARCH_URL,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json=serper_payload(query, limit, country),
                timeout=15,
            )
            response.raise_for_status()
            increment_serper_key_usage(api_key)
            break
        except requests.HTTPError as exc:
            last_error = f"Serper API key #{index} failed: {exc}"
            try:
                error = response.json()
                if error.get("message"):
                    last_error = f"Serper API key #{index} failed: {error['message']}"
            except ValueError:
                pass
        except requests.RequestException as exc:
            last_error = f"Serper API key #{index} failed: {exc}"
    else:
        raise HTTPException(status_code=400, detail=last_error)

    payload = response.json()
    return [
        SearchResult(
            title=item.get("title", ""),
            link=item.get("link", ""),
            snippet=item.get("snippet"),
        )
        for item in payload.get("organic", [])
        if item.get("link")
    ]


def serper_raw_search(query: str, limit: int, country: Optional[str] = None) -> dict:
    api_keys = get_serper_keys()
    if not api_keys:
        raise HTTPException(status_code=500, detail="Set SERPER_API_KEY or SERPER_API_KEYS in .env before using /search")

    last_error = "Serper API failed"
    for index, api_key in enumerate(api_keys, start=1):
        if get_serper_key_used(api_key) >= SERPER_MONTHLY_LIMIT:
            last_error = f"Serper API key #{index} reached local monthly limit"
            continue
        try:
            wait_for_serper_rate_limit()
            response = requests.post(
                SERPER_SEARCH_URL,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json=serper_payload(query, limit, country),
                timeout=15,
            )
            response.raise_for_status()
            increment_serper_key_usage(api_key)
            return response.json()
        except requests.HTTPError as exc:
            last_error = f"Serper API key #{index} failed: {exc}"
            try:
                error = response.json()
                if error.get("message"):
                    last_error = f"Serper API key #{index} failed: {error['message']}"
            except ValueError:
                pass
        except requests.RequestException as exc:
            last_error = f"Serper API key #{index} failed: {exc}"

    raise HTTPException(status_code=400, detail=last_error)


def google_search(query: str, limit: int) -> list[SearchResult]:
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        raise HTTPException(
            status_code=500,
            detail="Set GOOGLE_API_KEY and GOOGLE_CSE_ID in a .env file before using /search",
        )

    try:
        response = requests.get(
            GOOGLE_SEARCH_URL,
            params={"key": api_key, "cx": cse_id, "q": query, "num": limit},
            timeout=15,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = f"Google Search API failed: {exc}"
        try:
            error = response.json().get("error", {})
            if error.get("message"):
                detail = f"Google Search API failed: {error['message']}"
        except ValueError:
            pass
        raise HTTPException(status_code=400, detail=detail) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=400, detail=f"Google Search API failed: {exc}") from exc

    payload = response.json()
    return [
        SearchResult(
            title=item.get("title", ""),
            link=item.get("link", ""),
            snippet=item.get("snippet"),
        )
        for item in payload.get("items", [])
        if item.get("link")
    ]


def extract_article(url: str) -> ArticleResponse:
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=400, detail=f"Could not fetch URL: {exc}") from exc

    soup = BeautifulSoup(response.text, "lxml")
    content = extract_content(soup)
    if not content:
        raise HTTPException(status_code=422, detail="Could not extract readable content from this URL")

    return ArticleResponse(
        author=extract_author(soup),
        title=extract_title(soup),
        content=content,
        website_url=normalize_website_url(response.url),
    )


def scrape_article_json(url: str) -> ArticleJsonResponse:
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=400, detail=f"Could not fetch URL: {exc}") from exc

    soup = BeautifulSoup(response.text, "lxml")
    content = extract_content(soup)
    if not content:
        raise HTTPException(status_code=422, detail="Could not extract readable content from this URL")

    return ArticleJsonResponse(
        url=response.url,
        content=content,
        keyword=extract_keywords(soup),
        author=extract_author(soup),
        published_date=extract_published_date(soup),
        keys=build_key_remaining(),
    )


@app.get("/extract", response_model=ArticleResponse)
def extract_from_query(url: HttpUrl = Query(..., description="Article URL to extract")):
    return extract_article(str(url))


@app.post("/extract", response_model=ArticleResponse)
def extract_from_body(payload: ExtractRequest):
    return extract_article(str(payload.url))


@app.get("/scrape-url", response_model=ArticleJsonResponse)
def scrape_url(url: HttpUrl = Query(..., description="Article URL to scrape")):
    return scrape_article_json(str(url))


@app.get("/search", response_model=SearchResponse)
def search_google(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(5, ge=1, le=10, description="Search results to return"),
    extract: bool = Query(False, description="Extract article JSON from each result link"),
    country: Optional[str] = Query(None, min_length=2, max_length=2, description="Country code, for example eg or us"),
):
    results, cached, provider = search_web(q, limit, country)
    articles = None

    if extract:
        articles = []
        for result in results:
            try:
                articles.append(extract_article(result.link))
            except HTTPException:
                continue

    return SearchResponse(query=q, provider=provider, cached=cached, results=results, articles=articles)


@app.get("/links", response_model=SearchResponse)
def search_links(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=10, description="Search links to return"),
    country: Optional[str] = Query(None, min_length=2, max_length=2, description="Country code, for example eg or us"),
):
    results, cached, provider = search_web(q, limit, country)
    return SearchResponse(query=q, provider=provider, cached=cached, results=results, articles=None)


@app.get("/articles", response_model=SearchResponse)
def search_articles(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=10, description="Articles to extract"),
    country: Optional[str] = Query(None, min_length=2, max_length=2, description="Country code, for example eg or us"),
):
    results, cached, provider = search_web(q, limit, country)
    articles = []

    for result in results:
        try:
            articles.append(extract_article(result.link))
        except HTTPException:
            continue

    return SearchResponse(query=q, provider=provider, cached=cached, results=results, articles=articles)


@app.get("/serper-raw")
def serper_raw(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=10, description="Raw Serper results to return"),
    country: Optional[str] = Query(None, min_length=2, max_length=2, description="Country code, for example eg or us"),
):
    return serper_raw_search(q, limit, country)


@app.get("/search-usage", response_model=SearchUsageResponse)
def search_usage():
    return build_serper_usage_response()


@app.get("/")
def health_check():
    return {
        "message": "Send a URL to /extract or a query to /search",
        "base_url": PUBLIC_BASE_URL,
        "example": f"{PUBLIC_BASE_URL}/extract?url=https://example.com/article",
        "search_example": f"{PUBLIC_BASE_URL}/search?q=bbc world cup&limit=5&extract=true",
        "links_example": f"{PUBLIC_BASE_URL}/links?q=site:bbc.com/sport/football/articles world cup&limit=10",
        "articles_example": f"{PUBLIC_BASE_URL}/articles?q=site:bbc.com/sport/football/articles world cup&limit=10",
        "serper_raw_example": f"{PUBLIC_BASE_URL}/serper-raw?q=iphone 17 pro max&limit=10",
        "scrape_url_example": f"{PUBLIC_BASE_URL}/scrape-url?url=https://www.bbc.com/sport/football/articles/cg74rzx582ko",
        "usage_example": f"{PUBLIC_BASE_URL}/search-usage",
        "serper_requests_per_second": SERPER_REQUESTS_PER_SECOND,
    }
