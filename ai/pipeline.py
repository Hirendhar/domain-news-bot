"""
AI pipeline — fetches full article text and generates summaries via Gemini.
Processes articles in batches to stay within free-tier rate limits.
"""
import time
from ai.client import generate
from ai.fetcher import fetch_full_text

BATCH_SIZE = 3          # Articles per Gemini API call
RATE_LIMIT_SEC = 8.0    # Seconds between API calls (free tier: 15 RPM)
FETCH_DELAY = 1.0       # Seconds between article fetches (polite crawling)


def enrich(items: list[dict], model: str = "gemini-2.5-flash") -> list[dict]:
    """
    For each article:
      1. Fetch full article text from URL
      2. Send to Gemini in batches for summarisation
      3. Return items enriched with ai_summary, ai_topics, ai_key_points
    """
    print(f"  [Pipeline] Fetching full text for {len(items)} articles...")
    for item in items:
        full_text = fetch_full_text(item["url"])
        item["_full_text"] = full_text or item.get("excerpt", "")
        time.sleep(FETCH_DELAY)

    print(f"  [Pipeline] Summarising in batches of {BATCH_SIZE}...")
    batches = [items[i:i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]
    enriched = []

    for i, batch in enumerate(batches):
        print(f"  [Pipeline] Batch {i + 1}/{len(batches)}...")
        prompt = _build_prompt(batch)
        result = generate(prompt, model=model, rate_limit=RATE_LIMIT_SEC)

        analyses = result.get("analyses", [])
        for j, item in enumerate(batch):
            ai = analyses[j] if j < len(analyses) else {}
            enriched.append({
                **{k: v for k, v in item.items() if not k.startswith("_")},
                "ai_summary": ai.get("summary", ""),
                "ai_topics": ", ".join(ai.get("topics", [])),
                "ai_key_points": ai.get("key_points", ""),
            })

    return enriched


def _build_prompt(batch: list[dict]) -> str:
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

    return f"""You are a domain name industry analyst. Analyse these {len(batch)} domain industry news articles and return a JSON object.

{articles_text}

Return this EXACT JSON:
{{
  "analyses": [
    {{
      "summary": "<3-4 sentence plain-English summary explaining what the article is about and why it matters to the domain industry>",
      "topics": ["<topic1>", "<topic2>"],
      "key_points": "<bullet list of 3-5 key takeaways, each on a new line starting with •>"
    }}
  ]
}}

Rules:
- summary: clear explanation for domain industry professionals. Include specific names, numbers, deals if mentioned.
- topics: choose from [Domain Sales, New gTLDs, ccTLDs, Domain Policy, Domain Investing, Domain Theft/Security, Industry News, ICANN, Registry/Registrar, Legal/Disputes]
- key_points: concrete facts and figures — no vague statements
- One analysis object per article, in the same order as input
- Never invent information not present in the article text
"""
