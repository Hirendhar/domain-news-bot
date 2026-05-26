"""
Notion storage layer — uses requests directly (works with any notion-client version).
Pushes domain news articles with AI summaries to a Notion database.
Deduplicates by normalised URL so re-runs never create duplicate entries.

Required env vars:
  NOTION_TOKEN         — your Notion integration token
  NOTION_DATABASE_ID   — the ID of the target Notion database
"""
import os
import time
import requests
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"

# Query params stripped before URL comparison (tracking params ≠ article identity)
_STRIP_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "src"}

# Rate limiting and retry config
_PUSH_DELAY = 0.4        # seconds between pushes (keeps under Notion's 3 req/s limit)
_PUSH_RETRIES = 3        # attempts per article
_PUSH_BACKOFF = 2.0      # seconds between retries
_TIMEOUT = 30            # per-request timeout (Notion can be slow under load)
_TRANSIENT_CODES = {429, 500, 502, 503, 504}


def _headers() -> dict:
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        raise RuntimeError("NOTION_TOKEN environment variable not set")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _request_with_retry(url: str, payload: dict, label: str) -> requests.Response | None:
    """
    POST to Notion with retry on network errors (timeout/connection) and
    transient HTTP codes. Returns the Response, or None if all attempts failed.
    Never raises — a transient Notion blip must not crash the whole run.
    """
    for attempt in range(1, _PUSH_RETRIES + 1):
        try:
            resp = requests.post(url, headers=_headers(), json=payload, timeout=_TIMEOUT)
        except requests.exceptions.RequestException as e:
            if attempt < _PUSH_RETRIES:
                print(f"  [Notion] {label}: network error (attempt {attempt}/{_PUSH_RETRIES}) — retrying in {_PUSH_BACKOFF}s: {e}")
                time.sleep(_PUSH_BACKOFF)
                continue
            print(f"  [Notion] {label}: network error, giving up after {_PUSH_RETRIES} attempts: {e}")
            return None

        if resp.status_code in _TRANSIENT_CODES and attempt < _PUSH_RETRIES:
            print(f"  [Notion] {label}: {resp.status_code} (attempt {attempt}/{_PUSH_RETRIES}) — retrying in {_PUSH_BACKOFF}s")
            time.sleep(_PUSH_BACKOFF)
            continue
        return resp

    return None


def normalize_url(url: str) -> str:
    """
    Canonicalise a URL for deduplication:
    - Lowercase scheme + host
    - Strip trailing slash from path
    - Remove tracking query params (utm_*, ref, src)
    - Strip fragment
    """
    try:
        p = urlparse(url)
        clean_params = {
            k: v for k, v in parse_qs(p.query, keep_blank_values=True).items()
            if k.lower() not in _STRIP_PARAMS
        }
        clean_query = urlencode({k: v[0] for k, v in clean_params.items()})
        return urlunparse((
            p.scheme.lower(),
            p.netloc.lower(),
            p.path.rstrip("/"),
            p.params,
            clean_query,
            "",   # strip fragment
        ))
    except Exception:
        return url


def _parse_pub_date(raw: str) -> str:
    """
    Convert RFC-2822 pub_date from RSS feeds to ISO-8601 for Notion's date property.
    Returns '' if parsing fails (field will be omitted rather than sending null).
    """
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).isoformat()
    except Exception:
        return ""


def get_existing_urls(db_id: str) -> set[str] | None:
    """
    Fetch all article URLs already in the database (for deduplication).
    Returns normalised URLs, or None if the query failed (so the caller can
    skip syncing instead of re-pushing everything as new). Handles pagination.
    """
    seen: set[str] = set()
    cursor = None

    while True:
        payload: dict = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor

        resp = _request_with_retry(
            f"{BASE_URL}/databases/{db_id}/query",
            payload,
            "Query existing URLs",
        )

        if resp is None or resp.status_code != 200:
            code = resp.status_code if resp is not None else "no response"
            print(f"  [Notion] Query failed: {code} — cannot verify duplicates this cycle")
            return None   # Signal failure so sync() can skip rather than re-push dupes

        data = resp.json()
        for page in data.get("results", []):
            url = page.get("properties", {}).get("URL", {}).get("url", "")
            if url:
                seen.add(normalize_url(url))

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return seen


def push_article(db_id: str, item: dict) -> bool:
    """
    Push a single article to Notion with retry on transient errors.
    Returns True on success.
    """
    iso_pub_date = _parse_pub_date(item.get("pub_date", ""))

    # Topics as multi_select — filterable in Notion UI
    topics_list = [
        {"name": t.strip()}
        for t in item.get("ai_topics", "").split(",")
        if t.strip()
    ]

    properties: dict = {
        "Title": {
            "title": [{"text": {"content": item.get("title", "Untitled")[:200]}}]
        },
        "URL": {
            "url": item.get("url") or None
        },
        "Source": {
            "select": {"name": item.get("source", "Unknown")}
        },
        "Category": {
            "select": {"name": item.get("ai_category") or "Other"}
        },
        "Sale Price": {
            "rich_text": [{"text": {"content": item.get("ai_sale_price", "")[:100]}}]
        },
        "Date Found": {
            "date": {"start": item.get("date_found", "")}
        },
        "Topics": {
            "multi_select": topics_list
        },
        "Summary": {
            "rich_text": [{"text": {"content": item.get("ai_summary", "")[:2000]}}]
        },
        "Key Points": {
            "rich_text": [{"text": {"content": item.get("ai_key_points", "")[:2000]}}]
        },
        "Status": {
            "select": {"name": "New"}
        },
    }

    # Only include Published if we have a valid date — Notion rejects null dates
    if iso_pub_date:
        properties["Published"] = {"date": {"start": iso_pub_date}}

    payload = {"parent": {"database_id": db_id}, "properties": properties}

    resp = _request_with_retry(f"{BASE_URL}/pages", payload, f"Push '{item.get('title', '?')[:40]}'")
    if resp is None:
        return False
    if resp.status_code == 200:
        return True
    print(f"  [Notion] Push failed ({resp.status_code}) for '{item.get('title', '?')[:50]}': {resp.text[:200]}")
    return False


def sync(db_id: str, items: list[dict]) -> tuple[int, int]:
    """
    Sync articles to Notion. Skips duplicates (by normalised URL).
    Returns (added_count, skipped_count).
    """
    print(f"  [Notion] Fetching existing URLs...")
    existing = get_existing_urls(db_id)
    if existing is None:
        # Query failed (e.g. Notion 503). Skip this cycle entirely rather than
        # re-push every article as new and create duplicates. Syncs next run.
        print("  [Notion] Skipping sync — could not confirm existing articles (will retry next cycle)")
        return 0, len(items)
    print(f"  [Notion] {len(existing)} articles already in DB")

    added = 0
    skipped = 0

    for item in items:
        url = item.get("url", "")
        if not url or normalize_url(url) in existing:
            skipped += 1
            continue

        if push_article(db_id, item):
            added += 1
            existing.add(normalize_url(url))
            print(f"  [Notion] ✓ {item.get('title', 'Untitled')[:70]}")
        else:
            skipped += 1

        time.sleep(_PUSH_DELAY)   # stay under Notion's 3 req/s rate limit

    return added, skipped
