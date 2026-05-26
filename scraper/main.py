"""
Domain News Bot — Main Orchestrator
Scrape → Enrich (AI summaries) → Store (Notion) → Notify (email)

Run locally:
  python -m scraper.main

Required env vars:
  NOTION_TOKEN          — Notion integration secret
  NOTION_DATABASE_ID    — target Notion database ID
  GEMINI_API_KEY        — Google AI Studio key (free, optional)

Optional env vars:
  GMAIL_ADDRESS         — Gmail address used to send notifications
  GMAIL_APP_PASSWORD    — Gmail App Password (NOT your normal password)
  NOTIFY_EMAIL_TO       — recipient email address
  USER_CONTEXT          — custom focus for AI summaries
                          e.g. "Focus on domain sales above $10,000 and new gTLD policy"
"""
import os
import sys
import smtplib
from datetime import date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

from scraper.sources import domainnamewire, dnjournal, namepros, circleid, icannblog
from storage.notion_sync import sync, normalize_url

SOURCES = [
    ("Domain Name Wire", domainnamewire.fetch),
    ("DN Journal",       dnjournal.fetch),
    ("NamePros",         namepros.fetch),
    ("CircleID",         circleid.fetch),
    ("ICANN Blog",       icannblog.fetch),
]

NOTION_DB_URL = "https://www.notion.so/Domain-News-1b77ea433c6c80e49916cac0f9c8b241"


def _send_email(added_count: int, articles: list[dict]) -> None:
    """Send an email digest of newly added articles via Gmail SMTP."""
    gmail_addr = os.environ.get("GMAIL_ADDRESS", "").strip()
    # Gmail shows app passwords as "abcd efgh ijkl mnop" — strip spaces, SMTP rejects them
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    notify_to  = os.environ.get("NOTIFY_EMAIL_TO", "").strip()

    if not all([gmail_addr, gmail_pass, notify_to]):
        return   # Silently skip if credentials not configured

    today = date.today().strftime("%-d %b %Y")
    subject = f"📰 Domain News — {added_count} new article{'s' if added_count != 1 else ''} ({today})"

    # Group by source
    by_source: dict[str, list[dict]] = {}
    for art in articles:
        src = art.get("source", "Other")
        by_source.setdefault(src, []).append(art)

    lines = [f"Domain News Bot — {added_count} new article(s) found\n"]
    for src, arts in by_source.items():
        lines.append(f"\n── {src} ({len(arts)}) ──")
        for art in arts:
            lines.append(f"  • {art.get('title', 'Untitled')}")
            lines.append(f"    {art.get('url', '')}")
            if art.get("ai_summary") and not art["ai_summary"].startswith("[Summary pending"):
                summary = art["ai_summary"].split(".")[0] + "."
                lines.append(f"    {summary}")
    lines += [
        f"\n{'─' * 50}",
        f"View all in Notion: {NOTION_DB_URL}",
    ]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_addr
    msg["To"]      = notify_to
    msg.attach(MIMEText("\n".join(lines), "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_addr, gmail_pass)
            server.sendmail(gmail_addr, notify_to, msg.as_string())
        print(f"  [Email] Digest sent to {notify_to}")
    except Exception as e:
        # Safe diagnostic — prints address + password LENGTH (never the value)
        # so we can tell a mangled secret from a Gmail datacenter-IP block.
        print(f"  [Email] Failed to send: {e}")
        print(f"  [Email] (diagnostic: from={gmail_addr!r}, pw_len={len(gmail_pass)} chars, to={notify_to!r})")


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

    # ── 2. Deduplicate by normalised URL ───────────────────────────
    seen: set[str] = set()
    unique_items: list[dict] = []
    for item in all_items:
        url = item.get("url", "")
        norm = normalize_url(url)
        if url and norm not in seen:
            seen.add(norm)
            unique_items.append(item)

    print(f"\n[Dedup] {len(all_items)} total → {len(unique_items)} unique articles")

    # ── 3. AI enrichment — fetch full text + Gemini summaries ──────
    if ai_enabled:
        print("\n[AI] Generating summaries with Gemini...")
        from ai.pipeline import enrich
        enriched_items = enrich(unique_items)
    else:
        print("\n[AI] Skipped — GEMINI_API_KEY not set")
        enriched_items = unique_items

    # ── 4. Push to Notion ──────────────────────────────────────────
    print(f"\n[Notion] Syncing {len(enriched_items)} articles...")
    added, skipped = sync(db_id, enriched_items)

    # ── 5. Email notification (only if new articles were added) ────
    if added > 0:
        print(f"\n[Email] Sending digest for {added} new article(s)...")
        _send_email(added, enriched_items)

    print("\n" + "=" * 60)
    print(f"  Done — {added} new, {skipped} already existed")
    print("=" * 60)


if __name__ == "__main__":
    main()
