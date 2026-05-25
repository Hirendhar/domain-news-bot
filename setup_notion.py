"""
One-time setup: creates the Notion database with the correct schema.
Run ONCE before first bot run.

Usage:
  python setup_notion.py <NOTION_PAGE_ID>

Get your Page ID: open a page in Notion, copy the URL — the ID is the last 32 hex chars.
"""
import os
import sys
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()


def create_database(parent_page_id: str) -> str:
    """Creates the Domain News Bot database. Returns the new database ID."""
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        print("ERROR: NOTION_TOKEN not set in .env")
        sys.exit(1)

    client = Client(auth=token)

    db = client.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": "Domain News Bot"}}],
        icon={"type": "emoji", "emoji": "🌐"},
        properties={
            "Title":      {"title": {}},
            "URL":        {"url": {}},
            "Source": {
                "select": {
                    "options": [
                        {"name": "Domain Name Wire", "color": "blue"},
                        {"name": "DN Journal",       "color": "green"},
                    ]
                }
            },
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
            "Date Found":  {"date": {}},
            "Published":   {"rich_text": {}},
            "Topics":      {"rich_text": {}},
            "Summary":     {"rich_text": {}},
            "Key Points":  {"rich_text": {}},
        },
    )

    return db["id"]


def main():
    if len(sys.argv) < 2:
        print("Usage: python setup_notion.py <NOTION_PAGE_ID>")
        print("")
        print("How to get your Page ID:")
        print("  1. Open a Notion page where you want the database")
        print("  2. Click Share → Copy Link")
        print("  3. The ID is the 32-char hex string at the end of the URL")
        sys.exit(1)

    page_id = sys.argv[1].replace("-", "")
    print(f"Creating 'Domain News Bot' database...")

    db_id = create_database(page_id)

    print(f"\n✅ Database created successfully!")
    print(f"\nCopy this into your .env file AND as a GitHub Secret:")
    print(f"\n  NOTION_DATABASE_ID={db_id}\n")


if __name__ == "__main__":
    main()
