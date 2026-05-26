"""
Weekly Domain News Digest
Queries Notion for articles from the past 7 days, synthesises them with Gemini,
and sends an email summary.

Run manually:  python digest.py
Auto-runs via: .github/workflows/digest.yml (every Monday 08:00 UTC)

Required env vars:
  NOTION_TOKEN, NOTION_DATABASE_ID, GEMINI_API_KEY
  GMAIL_ADDRESS, GMAIL_APP_PASSWORD, NOTIFY_EMAIL_TO
"""
import os
import sys
import smtplib
import requests
from datetime import date, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

NOTION_VERSION = "2022-06-28"
NOTION_BASE    = "https://api.notion.com/v1"
NOTION_DB_URL  = "https://www.notion.so/Domain-News-1b77ea433c6c80e49916cac0f9c8b241"


def _notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def fetch_week_articles(db_id: str) -> list[dict]:
    """Query Notion for articles added in the past 7 days."""
    since = (date.today() - timedelta(days=7)).isoformat()
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
        if title:
            articles.append({"title": title, "url": url, "source": source, "summary": summary})

    return articles


def synthesise(articles: list[dict]) -> str:
    """Ask Gemini to write a concise 'week in review' synthesis."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or not articles:
        return ""

    items_text = "\n\n".join(
        f"- [{a['source']}] {a['title']}\n  {a['summary'][:300]}"
        for a in articles
    )
    prompt = f"""You are a domain name industry analyst writing a weekly newsletter.

Here are the domain industry news articles from the past 7 days:

{items_text}

Write a concise "Week in Review" (200-300 words) that:
1. Identifies the 2-3 biggest themes or stories of the week
2. Highlights any notable domain sales, policy changes, or industry shifts
3. Ends with one sentence on what to watch in the coming week

Plain text only — no markdown, no bullet points, just paragraphs.
"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    try:
        resp = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.5, "maxOutputTokens": 1024}},
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
    except Exception as e:
        print(f"[Digest] Gemini error: {e}")
    return ""


def send_digest(articles: list[dict], synthesis: str) -> None:
    """Email the weekly digest."""
    gmail_addr = os.environ.get("GMAIL_ADDRESS", "").strip()
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    notify_to  = os.environ.get("NOTIFY_EMAIL_TO", "").strip()

    if not all([gmail_addr, gmail_pass, notify_to]):
        print("[Digest] Email credentials not set — printing digest to stdout:\n")
        if synthesis:
            print(synthesis)
        return

    week_ending = date.today().strftime("%-d %b %Y")
    subject = f"🌐 Domain News Weekly — Week ending {week_ending} ({len(articles)} articles)"

    by_source: dict[str, list[dict]] = {}
    for art in articles:
        by_source.setdefault(art["source"], []).append(art)

    lines = [
        f"Domain News Weekly Digest",
        f"Week ending {week_ending} — {len(articles)} articles\n",
    ]
    if synthesis:
        lines += ["── WEEK IN REVIEW ──", synthesis, ""]

    lines.append("── ALL ARTICLES THIS WEEK ──")
    for src, arts in by_source.items():
        lines.append(f"\n{src} ({len(arts)}):")
        for art in arts:
            lines.append(f"  • {art['title']}")
            lines.append(f"    {art['url']}")

    lines += ["", "─" * 50, f"View in Notion: {NOTION_DB_URL}"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_addr
    msg["To"]      = notify_to
    msg.attach(MIMEText("\n".join(lines), "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_addr, gmail_pass)
            server.sendmail(gmail_addr, notify_to, msg.as_string())
        print(f"[Digest] Weekly digest sent to {notify_to} ({len(articles)} articles)")
    except Exception as e:
        print(f"[Digest] Email failed: {e}")


def main() -> None:
    db_id = os.environ.get("NOTION_DATABASE_ID", "")
    if not db_id:
        print("ERROR: NOTION_DATABASE_ID not set")
        sys.exit(1)

    print("[Digest] Fetching last 7 days from Notion...")
    articles = fetch_week_articles(db_id)
    print(f"[Digest] {len(articles)} articles found")

    if not articles:
        print("[Digest] No articles this week — skipping")
        return

    print("[Digest] Generating week-in-review with Gemini...")
    synthesis = synthesise(articles)
    send_digest(articles, synthesis)


if __name__ == "__main__":
    main()
