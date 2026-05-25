"""
One-time setup: creates the Notion database with the correct schema.
Run ONCE before first bot run.

Usage:
  python setup_notion.py <NOTION_PAGE_ID>           # create new database
  python setup_notion.py --patch <NOTION_DB_ID>     # update existing schema

Get your Page ID: open a page in Notion, copy the URL — the ID is the last 32 hex chars.
"""
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"

# All supported sources with colours
SOURCE_OPTIONS = [
    {"name": "Domain Name Wire", "color": "blue"},
    {"name": "DN Journal",       "color": "green"},
    {"name": "NamePros",         "color": "orange"},
    {"name": "CircleID",         "color": "purple"},
    {"name": "Domain Gang",      "color": "red"},
]


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def create_database(parent_page_id: str, token: str) -> str:
    """Creates the Domain News Bot database via raw requests. Returns the new database ID."""
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": "Domain News Bot"}}],
        "icon": {"type": "emoji", "emoji": "🌐"},
        "properties": {
            "Title":     {"title": {}},
            "URL":       {"url": {}},
            "Source":    {"select": {"options": SOURCE_OPTIONS}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "New",   "color": "yellow"},
                        {"name": "Read",  "color": "blue"},
                        {"name": "Saved", "color": "green"},
                        {"name": "Skip",  "color": "gray"},
                    ]
                }
            },
            "Date Found": {"date": {}},
            "Published":  {"date": {}},
            "Topics":     {"multi_select": {"options": []}},
            "Summary":    {"rich_text": {}},
            "Key Points": {"rich_text": {}},
        },
    }
    resp = requests.post(f"{BASE_URL}/databases", headers=_headers(token), json=payload, timeout=15)
    if resp.status_code != 200:
        print(f"ERROR: Notion API returned {resp.status_code}: {resp.text[:400]}")
        sys.exit(1)
    return resp.json()["id"]


def patch_database(db_id: str, token: str) -> None:
    """
    Update an existing database's schema:
    - Topics: rich_text → multi_select
    - Published: rich_text → date
    - Source: add NamePros, CircleID, Domain Gang options
    """
    payload = {
        "properties": {
            "Topics":    {"multi_select": {"options": []}},
            "Published": {"date": {}},
            "Source":    {"select": {"options": SOURCE_OPTIONS}},
        }
    }
    resp = requests.patch(
        f"{BASE_URL}/databases/{db_id}",
        headers=_headers(token),
        json=payload,
        timeout=15,
    )
    if resp.status_code == 200:
        print("✅ Database schema updated successfully!")
        print("   Topics → multi_select  |  Published → date  |  Source options updated")
    else:
        print(f"ERROR: {resp.status_code}: {resp.text[:400]}")
        sys.exit(1)


def main():
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        print("ERROR: NOTION_TOKEN not set in .env")
        sys.exit(1)

    # ── Patch mode ────────────────────────────────────────────────
    if len(sys.argv) >= 3 and sys.argv[1] == "--patch":
        db_id = sys.argv[2].replace("-", "")
        print(f"Patching existing database {db_id}...")
        patch_database(db_id, token)
        return

    # ── Create mode ───────────────────────────────────────────────
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python setup_notion.py <NOTION_PAGE_ID>           # create new database")
        print("  python setup_notion.py --patch <NOTION_DB_ID>     # update existing schema")
        print("")
        print("How to get your Page ID:")
        print("  1. Open a Notion page where you want the database")
        print("  2. Click Share → Copy Link")
        print("  3. The ID is the 32-char hex string at the end of the URL")
        sys.exit(1)

    page_id = sys.argv[1].replace("-", "")
    print("Creating 'Domain News Bot' database...")

    db_id = create_database(page_id, token)

    print("\n✅ Database created successfully!")
    print("\nCopy this into your .env file AND as a GitHub Secret:")
    print(f"\n  NOTION_DATABASE_ID={db_id}\n")


if __name__ == "__main__":
    main()
