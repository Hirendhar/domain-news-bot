"""
AI pipeline — fetches full article text and generates summaries via Gemini.
Processes articles in batches to stay within free-tier rate limits.
"""
import os
import time
from ai.client import generate
from ai.fetcher import fetch_full_text

BATCH_SIZE = 8          # Articles per Gemini API call (fewer calls = less quota burn)
RATE_LIMIT_SEC = 8.0    # Seconds between API calls (free tier: 15 RPM)
FETCH_DELAY = 1.0       # Seconds between article fetches (polite crawling)
RETRY_WAIT = 30         # Seconds to wait before retrying a failed batch


def enrich(items: list[dict], model: str = "gemini-2.5-flash") -> list[dict]:
    """
    For each article:
      1. Fetch full article text from URL
      2. Send to Gemini in batches for summarisation
      3. Retry any batches that returned fewer analyses than expected
      4. Return items enriched with ai_summary, ai_topics, ai_key_points
    """
    print(f"  [Pipeline] Fetching full text for {len(items)} articles...")
    for item in items:
        full_text = fetch_full_text(item["url"])
        # Warn if article text is suspiciously short (possible scraper selector rot)
        if full_text and len(full_text) < 100:
            print(f"  [Pipeline] WARNING: very short text ({len(full_text)} chars) for {item['url']}")
        item["_full_text"] = full_text or item.get("excerpt", "")
        time.sleep(FETCH_DELAY)

    # Optional user context for prompt personalisation (set USER_CONTEXT env var)
    user_context = os.environ.get("USER_CONTEXT", "").strip()

    print(f"  [Pipeline] Summarising in batches of {BATCH_SIZE}...")
    batches = [items[i:i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]

    results: dict[str, dict] = {}   # url → enriched item
    retry_queue: list[dict] = []

    # ── First pass ────────────────────────────────────────────────
    for i, batch in enumerate(batches):
        print(f"  [Pipeline] Batch {i + 1}/{len(batches)}...")
        prompt = _build_prompt(batch, user_context)
        result = generate(prompt, model=model, rate_limit=RATE_LIMIT_SEC)
        analyses = result.get("analyses", [])

        for j, item in enumerate(batch):
            ai = analyses[j] if j < len(analyses) else None
            if ai:
                results[item["url"]] = _merge(item, ai)
            else:
                retry_queue.append(item)

    # ── Retry pass — one more attempt after a wait ────────────────
    if retry_queue:
        print(f"  [Pipeline] {len(retry_queue)} articles missed summaries — retrying in {RETRY_WAIT}s...")
        time.sleep(RETRY_WAIT)
        retry_batches = [retry_queue[i:i + BATCH_SIZE] for i in range(0, len(retry_queue), BATCH_SIZE)]
        for i, batch in enumerate(retry_batches):
            print(f"  [Pipeline] Retry {i + 1}/{len(retry_batches)}...")
            prompt = _build_prompt(batch, user_context)
            result = generate(prompt, model=model, rate_limit=RATE_LIMIT_SEC)
            analyses = result.get("analyses", [])
            for j, item in enumerate(batch):
                ai = analyses[j] if j < len(analyses) else None
                if ai:
                    results[item["url"]] = _merge(item, ai)
                else:
                    # Sentinel: visible in Notion so user knows summary is missing
                    results[item["url"]] = _merge(item, {
                        "summary": "[Summary pending — AI unavailable during fetch. Will appear on next run.]",
                        "topics": [],
                        "key_points": "",
                        "category": "Other",
                        "sale_price": "",
                    })
                    print(f"  [Pipeline] Could not summarise: {item.get('title', '?')[:60]}")

    # Return in original input order
    return [results.get(item["url"], _merge(item, {})) for item in items]


def _merge(item: dict, ai: dict) -> dict:
    """Merge an article dict with its AI analysis fields."""
    return {
        **{k: v for k, v in item.items() if not k.startswith("_")},
        "ai_summary": ai.get("summary", ""),
        "ai_topics": ", ".join(ai.get("topics", [])),
        "ai_key_points": ai.get("key_points", ""),
        "ai_category": ai.get("category", "Other"),
        "ai_sale_price": ai.get("sale_price", ""),
    }


def _build_prompt(batch: list[dict], user_context: str = "") -> str:
    articles_text = ""
    for i, item in enumerate(batch, 1):
        content = item.get("_full_text", item.get("excerpt", "No content available"))
        articles_text += f"""
Article {i}:
Title: {item['title']}
URL: {item['url']}
Source: {item['source']}
Text: {content[:2000]}

---
"""

    context_section = (
        f"\nUser focus: {user_context} — weight summaries toward these interests.\n"
        if user_context else ""
    )

    return f"""You are a domain name industry analyst. Analyse these {len(batch)} domain industry news articles and return a JSON object.
{context_section}
{articles_text}

Return this EXACT JSON:
{{
  "analyses": [
    {{
      "summary": "<3-4 sentence plain-English summary explaining what the article is about and why it matters to the domain industry>",
      "category": "<exactly ONE of the 8 categories below>",
      "sale_price": "<headline dollar amount if this is a domain sale/acquisition, e.g. $25,000; otherwise empty string>",
      "topics": ["<topic1>", "<topic2>"],
      "key_points": "<bullet list of 3-5 key takeaways, each on a new line starting with •>"
    }}
  ]
}}

Rules:
- summary: clear explanation for domain industry professionals. Include specific names, numbers, deals if mentioned.
- category: pick the SINGLE best fit from exactly these 8 — [Sales & Acquisitions, Disputes & Arbitration, Takedowns & Seizures, Policy & ICANN, New gTLDs & Registry, Security & Theft, Market & Investing, Other]. Use "Other" only if none clearly apply.
- sale_price: only for articles reporting a specific domain sale/acquisition price — copy the amount verbatim (with currency symbol). Empty string "" if no price is reported.
- topics: choose from [Domain Sales, New gTLDs, ccTLDs, Domain Policy, Domain Investing, Domain Theft/Security, Industry News, ICANN, Registry/Registrar, Legal/Disputes]
- key_points: concrete facts and figures — no vague statements
- One analysis object per article, in the same order as input
- Never invent information not present in the article text
"""
