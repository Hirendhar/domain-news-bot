"""
AI article writer — generates original, full-length news articles from the
information retrieved for each scraped item.

Where ai/pipeline.py produces a short summary + metadata, this module produces
a publishable ~400-600 word article, rewritten in the bot's own words and
grounded strictly in the fetched source text (no invented facts). It is run
after enrichment so each new item can carry a full ``ai_article`` body, which
is saved to the Notion page and to local markdown files.

Generation is per-article (one Gemini call each) so long bodies never get
truncated by a shared batch token budget, and is capped per run to protect the
free-tier quota.
"""
import os
import re
import time

from ai.client import generate
from ai.fetcher import fetch_full_text

RATE_LIMIT_SEC = 8.0     # seconds between Gemini calls (free tier ~15 RPM)
WORD_TARGET = "400-600"  # target article length


def _max_articles() -> int:
    """Per-run cap on generated articles (protects the free-tier quota)."""
    try:
        return max(0, int(os.environ.get("MAX_ARTICLES", "20") or "20"))
    except ValueError:
        return 20


def write_articles(items: list[dict], model: str = "gemini-2.5-flash") -> list[dict]:
    """
    Generate a full original article for each item, in order, up to MAX_ARTICLES.

    Adds ``ai_headline`` and ``ai_article`` (markdown body) to each processed
    item and returns the same list. Items beyond the cap are left untouched so
    they still sync with their summary only.
    """
    if not items:
        return items

    cap = _max_articles()
    if cap == 0:
        print("  [Writer] MAX_ARTICLES=0 — article generation disabled")
        return items

    user_context = os.environ.get("USER_CONTEXT", "").strip()
    to_write = items[:cap]
    if len(items) > cap:
        print(f"  [Writer] {len(items)} new items — writing first {cap} (MAX_ARTICLES cap)")

    for n, item in enumerate(to_write, 1):
        title = item.get("title", "Untitled")
        print(f"  [Writer] {n}/{len(to_write)} — {title[:60]}")

        source_text = _source_text(item)
        prompt = _build_prompt(item, source_text, user_context)
        result = generate(prompt, model=model, rate_limit=RATE_LIMIT_SEC)

        headline = (result.get("headline") or title).strip()
        article = (result.get("article") or "").strip()
        if not article:
            print(f"  [Writer] No article returned for: {title[:60]}")

        item["ai_headline"] = headline
        item["ai_article"] = article

    return items


def _source_text(item: dict) -> str:
    """
    Best available grounding text for the article. Prefers full text still
    attached from enrichment, then re-fetches the page, then falls back to the
    AI summary / key points / RSS excerpt so we never prompt with nothing.
    """
    full = item.get("_full_text") or ""
    if not full and item.get("url"):
        full = fetch_full_text(item["url"]) or ""

    parts = [full]
    if item.get("ai_summary"):
        parts.append("Summary: " + item["ai_summary"])
    if item.get("ai_key_points"):
        parts.append("Key points:\n" + item["ai_key_points"])
    if not full and item.get("excerpt"):
        parts.append(item["excerpt"])

    return "\n\n".join(p for p in parts if p).strip()


def _build_prompt(item: dict, source_text: str, user_context: str = "") -> str:
    context_section = (
        f"\nReader focus: {user_context} — emphasise angles relevant to this.\n"
        if user_context else ""
    )

    return f"""You are a domain name industry journalist writing for an
informed trade-news audience. Using ONLY the source material below, write an
original news article. Rewrite in your own words — do not copy sentences
verbatim — and never invent facts, names, quotes, or figures that are not in
the source.
{context_section}
Original title: {item.get('title', 'Untitled')}
Source publication: {item.get('source', 'Unknown')}
Source URL: {item.get('url', '')}

SOURCE MATERIAL:
\"\"\"
{source_text[:4000]}
\"\"\"

Return this EXACT JSON (no markdown fences):
{{
  "headline": "<original, specific headline (max ~90 chars) — not clickbait>",
  "article": "<a {WORD_TARGET} word article in markdown. Use a short lead paragraph, then 2-4 body paragraphs. You may use '##' subheadings and '-' bullet points for facts/figures. Attribute reporting to the source publication. End with a one-line note linking back to the original.>"
}}

Rules:
- Ground every claim in the source material; if a detail is not present, omit it.
- Keep numbers, prices, dates, and names exactly as they appear in the source.
- Plain, professional trade-news tone. No fluff, no invented quotes.
- Output valid JSON only.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Local persistence
# ─────────────────────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    """Filesystem-safe slug from a title."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return (s or "article")[:60]


def save_articles(items: list[dict], out_dir: str = "") -> int:
    """
    Write each item's generated article to ``<out_dir>/<YYYY-MM-DD>/<slug>.md``.
    Returns the number of files written. Items without an ``ai_article`` are
    skipped. Never raises — local persistence is best-effort.
    """
    out_dir = out_dir or os.environ.get("ARTICLES_DIR", "articles")
    written = 0
    day = time.strftime("%Y-%m-%d")
    folder = os.path.join(out_dir, day)

    for item in items:
        article = (item.get("ai_article") or "").strip()
        if not article:
            continue
        try:
            os.makedirs(folder, exist_ok=True)
            headline = item.get("ai_headline") or item.get("title", "Untitled")
            path = os.path.join(folder, f"{_slug(item.get('title', headline))}.md")
            front = (
                f"# {headline}\n\n"
                f"*Source: {item.get('source', 'Unknown')} — {item.get('url', '')}*\n\n"
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(front + article + "\n")
            written += 1
        except OSError as e:
            print(f"  [Writer] Could not save article for {item.get('title', '?')[:40]}: {e}")

    if written:
        print(f"  [Writer] Saved {written} article(s) to {folder}/")
    return written
