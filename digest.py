"""
Domain News Digest
Queries Notion for recent articles, synthesises them with Gemini, suggests
original article ideas to write, and sends an email.

Window is configurable via DIGEST_DAYS (default 7):
  DIGEST_DAYS=1  → daily digest (last 24h)  — see .github/workflows/digest-daily.yml
  DIGEST_DAYS=7  → weekly digest            — see .github/workflows/digest.yml

Run manually:  python digest.py            (weekly)
               DIGEST_DAYS=1 python digest.py   (daily)

Required env vars:
  NOTION_TOKEN, NOTION_DATABASE_ID, GEMINI_API_KEY
  SMTP_* / GMAIL_*, NOTIFY_EMAIL_TO  (see emailer.py)

Optional env vars:
  DIGEST_DAYS    lookback window in days (default 7)
  USER_CONTEXT   focus hint to bias the suggested article ideas
"""
import os
import sys
import requests
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

from emailer import send_email, is_configured, format_by_category

NOTION_VERSION = "2022-06-28"
NOTION_BASE    = "https://api.notion.com/v1"
NOTION_DB_URL  = "https://www.notion.so/Domain-News-1b77ea433c6c80e49916cac0f9c8b241"


def _window() -> tuple[int, str]:
    """Return (days, label) from DIGEST_DAYS. 1 day → 'Daily', else 'Weekly'."""
    try:
        days = max(1, int(os.environ.get("DIGEST_DAYS", "7") or "7"))
    except ValueError:
        days = 7
    return days, ("Daily" if days == 1 else "Weekly")


def _notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def fetch_recent_articles(db_id: str, days: int = 7) -> list[dict]:
    """Query Notion for articles added in the past ``days`` days."""
    since = (date.today() - timedelta(days=days)).isoformat()
    payload = {
        "filter": {"property": "Date Found", "date": {"on_or_after": since}},
        "sorts": [{"property": "Date Found", "direction": "descending"}],
        "page_size": 100,
    }
    resp = requests.post(
        f"{NOTION_BASE}/databases/{db_id}/query",
        headers=_notion_headers(),
        json=payload,
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"[Digest] Notion query failed: {resp.status_code}")
        return []

    articles = []
    for page in resp.json().get("results", []):
        props   = page.get("properties", {})
        title   = (props.get("Title", {}).get("title", [{}])[0].get("text", {}).get("content", ""))
        url     = props.get("URL", {}).get("url", "")
        source  = props.get("Source", {}).get("select", {}).get("name", "")
        summary = "".join(
            t.get("text", {}).get("content", "")
            for t in props.get("Summary", {}).get("rich_text", [])
        )
        category = (props.get("Category", {}).get("select") or {}).get("name", "") or "Other"
        sale_price = "".join(
            t.get("text", {}).get("content", "")
            for t in props.get("Sale Price", {}).get("rich_text", [])
        )
        published = (props.get("Published", {}).get("date") or {}).get("start", "") or ""
        if title:
            articles.append({
                "title": title, "url": url, "source": source, "summary": summary,
                "category": category, "sale_price": sale_price, "published": published,
            })

    return articles


def _gemini(prompt: str, max_tokens: int = 1024, temperature: float = 0.5) -> str:
    """Single Gemini call returning plain text, or '' on any failure."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return ""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    try:
        resp = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}},
            timeout=30,
        )
        if resp.status_code == 200:
            return (
                resp.json()
                .get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )
        print(f"[Digest] Gemini returned {resp.status_code}")
    except Exception as e:
        print(f"[Digest] Gemini error: {e}")
    return ""


def _articles_block(articles: list[dict], limit: int = 40) -> str:
    """Compact bullet list of articles for prompting."""
    return "\n\n".join(
        f"- [{a['source']}] {a['title']}\n  {a['summary'][:300]}"
        for a in articles[:limit]
    )


def synthesise(articles: list[dict], label: str = "Weekly") -> str:
    """Ask Gemini to write a concise period-in-review synthesis."""
    if not articles:
        return ""
    period = "day" if label == "Daily" else "week"
    prompt = f"""You are a domain name industry analyst writing a {label.lower()} newsletter.

Here are the domain industry news articles from the past {period}:

{_articles_block(articles)}

Write a concise "{label} in Review" (150-300 words) that:
1. Identifies the 2-3 biggest themes or stories
2. Highlights any notable domain sales, policy changes, or industry shifts
3. Ends with one sentence on what to watch next

Plain text only — no markdown, no bullet points, just paragraphs.
"""
    return _gemini(prompt, max_tokens=1024, temperature=0.5)


def suggest_ideas(articles: list[dict]) -> str:
    """
    Ask Gemini to suggest original article ideas to write, grounded in the
    day's/week's news. Returns a numbered plain-text list, or '' on failure.
    """
    if not articles:
        return ""

    user_context = os.environ.get("USER_CONTEXT", "").strip()
    context_section = (
        f"\nWriter focus: {user_context} — bias ideas toward this where relevant.\n"
        if user_context else ""
    )

    prompt = f"""You are a content strategist for a domain name industry publication.
Based ONLY on the news below, suggest 5-7 original article ideas the writer could
publish — angles worth covering, not just rewrites of these stories.
{context_section}
NEWS:
{_articles_block(articles)}

For each idea, output on its own line:
  <number>. <working title> — <one sentence on the angle and why it's timely>

Rules:
- Ground every idea in the news above; do not invent facts, names, or figures.
- Favour fresh angles: trends across stories, explainers, contrarian takes,
  "what it means for investors/registrars", follow-up questions raised.
- Plain text only. No preamble, no closing remarks — just the numbered list.
"""
    return _gemini(prompt, max_tokens=1024, temperature=0.7)


def send_digest(articles: list[dict], synthesis: str, ideas: str, label: str = "Weekly") -> None:
    """Email the digest (review + article ideas + articles) via configured SMTP."""
    today = date.today().strftime("%-d %b %Y")
    when = "today" if label == "Daily" else "ending"
    subject = f"🌐 Domain News {label} — {when} {today} ({len(articles)} articles)"

    lines = [
        f"Domain News {label} Digest",
        f"{label} digest — {today} — {len(articles)} articles\n",
    ]
    if synthesis:
        lines += [f"── {label.upper()} IN REVIEW ──", synthesis, ""]
    if ideas:
        lines += ["── 💡 ARTICLE IDEAS TO WRITE ──", ideas, ""]

    lines.append(format_by_category(articles))
    lines += ["", "─" * 50, f"View in Notion: {NOTION_DB_URL}"]

    if not is_configured():
        print("[Digest] Email not configured — printing digest to stdout:\n")
        print("\n".join(lines))
        return

    if send_email(subject, "\n".join(lines)):
        print(f"[Digest] {label} digest sent ({len(articles)} articles)")


def main() -> None:
    db_id = os.environ.get("NOTION_DATABASE_ID", "")
    if not db_id:
        print("ERROR: NOTION_DATABASE_ID not set")
        sys.exit(1)

    days, label = _window()
    print(f"[Digest] Fetching last {days} day(s) from Notion ({label})...")
    articles = fetch_recent_articles(db_id, days)
    print(f"[Digest] {len(articles)} articles found")

    if not articles:
        print(f"[Digest] No articles in the last {days} day(s) — skipping")
        return

    print("[Digest] Generating review with Gemini...")
    synthesis = synthesise(articles, label)
    print("[Digest] Suggesting article ideas with Gemini...")
    ideas = suggest_ideas(articles)
    if ideas:
        print(f"[Digest] {ideas.count(chr(10)) + 1} idea line(s) generated")

    send_digest(articles, synthesis, ideas, label)


if __name__ == "__main__":
    main()
