"""
Domain News Bot — Main Orchestrator
Scrape → Enrich (AI summaries) → Store (Notion)

Run locally:
  python -m scraper.main

Required env vars (set in .env or GitHub Secrets):
  NOTION_TOKEN          — Notion integration secret
  NOTION_DATABASE_ID    — target Notion database ID
  GEMINI_API_KEY        — Google AI Studio key (free)
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from scraper.sources import domainnamewire, dnjournal
from storage.notion_sync import sync

SOURCES = [
    ("Domain Name Wire", domainnamewire.fetch),
    ("DN Journal",       dnjournal.fetch),
]


def main() -> None:
    db_id = os.environ.get("NOTION_DATABASE_ID", "")
    if not db_id:
        print("ERROR: NOTION_DATABASE_ID not set in .env / environment")
        sys.exit(1)

    ai_enabled = bool(os.environ.get("GEMINI_API_KEY", ""))

    print("=" * 60)
    print("  Domain News Bot")
    print("=" * 60)

    # ── 1. Scrape all sources ──────────────────────────────────────
    all_items: list[dict] = []
    for name, fetch_fn in SOURCES:
        print(f"\n[Scraper] {name}...")
        try:
            items = fetch_fn()
            print(f"  → {len(items)} articles fetched")
            all_items.extend(items)
        except Exception as e:
            print(f"  [ERROR] {name} failed: {e}")

    if not all_items:
        print("\nNo articles found — exiting")
        sys.exit(0)

    # ── 2. Deduplicate by URL ──────────────────────────────────────
    seen: set[str] = set()
    unique_items: list[dict] = []
    for item in all_items:
        url = item.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique_items.append(item)

    print(f"\n[Dedup] {len(all_items)} total → {len(unique_items)} unique articles")

    # ── 3. AI enrichment — fetch full text + Gemini summaries ──────
    if ai_enabled:
        print("\n[AI] Generating summaries with Gemini...")
        from ai.pipeline import enrich
        enriched_items = enrich(unique_items)
    else:
        print("\n[AI] Skipped — GEMINI_API_KEY not set")
        print("     Articles will be stored without summaries")
        enriched_items = unique_items

    # ── 4. Push to Notion ──────────────────────────────────────────
    print(f"\n[Notion] Syncing {len(enriched_items)} articles...")
    added, skipped = sync(db_id, enriched_items)

    print("\n" + "=" * 60)
    print(f"  Done — {added} new, {skipped} already existed")
    print("=" * 60)


if __name__ == "__main__":
    main()
