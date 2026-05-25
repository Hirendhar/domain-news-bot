"""
Article full-text fetcher.
Fetches the full body of an article URL so the AI can summarise actual content
rather than just the RSS excerpt.
"""
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; domain-news-bot/1.0)",
}

MAX_CHARS = 3000  # Enough for a thorough summary without burning tokens


def fetch_full_text(url: str) -> str:
    """
    Fetches and returns the main readable text of an article URL.
    Falls back to empty string on any error.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, "lxml")

        # Remove noisy elements
        for tag in soup(["script", "style", "nav", "footer", "header",
                          "aside", "form", "iframe", "noscript"]):
            tag.decompose()

        # Try common article body selectors (ordered by specificity)
        selectors = [
            "article .entry-content",
            "article .post-content",
            ".entry-content",
            ".post-content",
            ".article-body",
            ".story-body",
            "article",
            "main",
        ]
        for selector in selectors:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 200:
                    return text[:MAX_CHARS]

        # Final fallback: body text
        body = soup.find("body")
        if body:
            return body.get_text(separator=" ", strip=True)[:MAX_CHARS]

        return ""

    except Exception as e:
        print(f"  [Fetcher] Error on {url}: {e}")
        return ""
