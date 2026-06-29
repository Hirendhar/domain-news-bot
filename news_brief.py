"""
news_brief.py — helper for the no-API-key "daily article ideas" Claude routine.

This script is deliberately AI-free: it never calls Gemini. The article-idea
recommendations are produced by Claude itself inside a scheduled Claude Code
routine, so the only credentials required are NOTION_TOKEN / NOTION_DATABASE_ID
and the email (SMTP_* / GMAIL_*) settings — no GEMINI_API_KEY.

A daily routine runs three steps:
  1. `python news_brief.py fetch`          → prints the last-24h news as text
  2. (Claude reads that, writes ideas to ideas.txt)
  3. `python news_brief.py email ideas.txt` → emails the news + Claude's ideas

Env:
  NOTION_TOKEN, NOTION_DATABASE_ID   (required)
  SMTP_* / GMAIL_*, NOTIFY_EMAIL_TO  (required for `email`; see emailer.py)
  DIGEST_DAYS                        lookback window in days (default 1)
"""
import os
import sys
from datetime import date
from dotenv import load_dotenv

load_dotenv()

from digest import fetch_recent_articles, NOTION_DB_URL
from emailer import send_email, is_configured, format_by_category


def _days() -> int:
    """Lookback window in days (default 1 — this is the *daily* helper)."""
    try:
        return max(1, int(os.environ.get("DIGEST_DAYS", "1") or "1"))
    except ValueError:
        return 1


def _load_articles() -> tuple[list[dict], int]:
    db_id = os.environ.get("NOTION_DATABASE_ID", "")
    if not db_id:
        print("ERROR: NOTION_DATABASE_ID not set", file=sys.stderr)
        sys.exit(1)
    days = _days()
    return fetch_recent_articles(db_id, days), days


def cmd_fetch() -> None:
    """Print the recent news as plain text for Claude to read."""
    articles, days = _load_articles()
    if not articles:
        # Sentinel the routine checks for so it can stop without emailing.
        print(f"NO_ARTICLES: nothing found in the last {days} day(s).")
        return

    print(f"# Domain news — last {days} day(s) — {len(articles)} article(s)\n")
    for i, a in enumerate(articles, 1):
        print(f"{i}. [{a['source']}] {a['title']}")
        if a.get("summary"):
            print(f"   {a['summary'][:400]}")
        if a.get("url"):
            print(f"   {a['url']}")
        print()


def cmd_email(ideas_path: str) -> None:
    """Email the news + Claude-written ideas (read from ideas_path)."""
    try:
        with open(ideas_path, encoding="utf-8") as f:
            ideas = f.read().strip()
    except OSError as e:
        print(f"ERROR: cannot read ideas file {ideas_path!r}: {e}", file=sys.stderr)
        sys.exit(1)

    articles, _ = _load_articles()
    today = date.today().strftime("%-d %b %Y")
    subject = f"💡 Domain News — Article ideas for {today} ({len(articles)} stories)"

    lines = [
        f"Domain News — Article Ideas ({today})",
        "",
        "── 💡 ARTICLE IDEAS TO WRITE ──",
        ideas or "(no ideas generated)",
        "",
        format_by_category(articles),
        "",
        "─" * 50,
        f"View in Notion: {NOTION_DB_URL}",
    ]
    body = "\n".join(lines)

    if not is_configured():
        print("[news_brief] Email not configured — printing instead:\n")
        print(body)
        return

    send_email(subject, body)


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] not in ("fetch", "email"):
        print("usage: news_brief.py fetch | email <ideas_file>", file=sys.stderr)
        sys.exit(2)

    if args[0] == "fetch":
        cmd_fetch()
    else:
        if len(args) < 2:
            print("usage: news_brief.py email <ideas_file>", file=sys.stderr)
            sys.exit(2)
        cmd_email(args[1])


if __name__ == "__main__":
    main()
