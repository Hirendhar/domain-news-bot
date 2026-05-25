"""
Notion storage layer — uses requests directly (works with any notion-client version).
Pushes domain news articles with AI summaries to a Notion database.
Deduplicates by URL so re-runs never create duplicate entries.

Required env vars:
  NOTION_TOKEN         — your Notion integration token
  NOTION_DATABASE_ID   — the ID of the target Notion database
"""
import os
import requests

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"


def _headers() -> dict:
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        raise RuntimeError("NOTION_TOKEN environment variable not set")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def get_existing_urls(db_id: str) -> set[str]:
    """
    Fetch all article URLs already in the database (for deduplication).
    Handles pagination automatically.
    """
    seen: set[str] = set()
    cursor = None

    while True:
        payload: dict = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor

        resp = requests.post(
            f"{BASE_URL}/databases/{db_id}/query",
            headers=_headers(),
            json=payload,
            timeout=15,
        )

        if resp.status_code != 200:
            print(f"  [Notion] Query failed: {resp.status_code} {resp.text[:200]}")
            break

        data = resp.json()
        for page in data.get("results", []):
            url_prop = page.get("properties", {}).get("URL", {})
            url = url_prop.get("url", "")
            if url:
                seen.add(url)

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return seen


def push_article(db_id: str, item: dict) -> bool:
    """Push a single article to Notion. Returns True on success."""
    properties = {
        "Title": {
            "title": [{"text": {"content": item.get("title", "Untitled")[:200]}}]
        },
        "URL": {
            "url": item.get("url") or None
        },
        "Source": {
            "select": {"name": item.get("source", "Unknown")}
        },
        "Date Found": {
            "date": {"start": item.get("date_found", "")}
        },
        "Published": {
            "rich_text": [{"text": {"content": item.get("pub_date", "")[:100]}}]
        },
        "Topics": {
            "rich_text": [{"text": {"content": item.get("ai_topics", "")[:500]}}]
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

    payload = {
        "parent": {"database_id": db_id},
        "properties": properties,
    }

    resp = requests.post(
        f"{BASE_URL}/pages",
        headers=_headers(),
        json=payload,
        timeout=15,
    )

    if resp.status_code == 200:
        return True

    print(f"  [Notion] Push failed ({resp.status_code}) for '{item.get('title', '?')[:50]}': {resp.text[:200]}")
    return False


def sync(db_id: str, items: list[dict]) -> tuple[int, int]:
    """
    Sync articles to Notion. Skips duplicates (by URL).
    Returns (added_count, skipped_count).
    """
    print(f"  [Notion] Fetching existing URLs...")
    existing = get_existing_urls(db_id)
    print(f"  [Notion] {len(existing)} articles already in DB")

    added = 0
    skipped = 0

    for item in items:
        url = item.get("url", "")
        if not url or url in existing:
            skipped += 1
            continue

        if push_article(db_id, item):
            added += 1
            existing.add(url)
            print(f"  [Notion] ✓ {item.get('title', 'Untitled')[:70]}")
        else:
            skipped += 1

    return added, skipped
