"""
Domain Name Wire — https://domainnamewire.com
Scrapes latest articles from the domain industry news site.
Method: RSS feed (HTML fallback)
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; domain-news-bot/1.0)",
}

RSS_URL = "https://domainnamewire.com/feed/"
SITE_URL = "https://domainnamewire.com"


def fetch() -> list[dict]:
    """Returns list of articles from Domain Name Wire."""
    articles = _fetch_rss()
    if not articles:
        articles = _fetch_html()
    return articles


def _fetch_rss() -> list[dict]:
    """Primary method: parse RSS feed."""
    try:
        resp = requests.get(RSS_URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []

        root = ET.fromstring(resp.text)
        results = []

        for item in root.findall(".//item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            description = item.findtext("description", "").strip()

            # Strip HTML tags from description/excerpt
            if description:
                soup = BeautifulSoup(description, "lxml")
                description = soup.get_text(separator=" ", strip=True)[:600]

            if title and link:
                results.append({
                    "title": title,
                    "url": link,
                    "source": "Domain Name Wire",
                    "date_found": datetime.now(timezone.utc).date().isoformat(),
                    "pub_date": pub_date,
                    "excerpt": description,
                })

        print(f"  [DNW RSS] {len(results)} articles")
        return results

    except Exception as e:
        print(f"  [DNW RSS] Error: {e}")
        return []


def _fetch_html() -> list[dict]:
    """Fallback: scrape HTML homepage."""
    try:
        resp = requests.get(SITE_URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        results = []

        for article in soup.select("article")[:20]:
            title_el = article.select_one("h2.entry-title a, h1.entry-title a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link = title_el.get("href", "")

            excerpt_el = article.select_one(".entry-summary, .entry-content p")
            excerpt = excerpt_el.get_text(strip=True)[:600] if excerpt_el else ""

            date_el = article.select_one("time.entry-date")
            pub_date = date_el.get("datetime", "") if date_el else ""

            if title and link:
                results.append({
                    "title": title,
                    "url": link,
                    "source": "Domain Name Wire",
                    "date_found": datetime.now(timezone.utc).date().isoformat(),
                    "pub_date": pub_date,
                    "excerpt": excerpt,
                })

        print(f"  [DNW HTML] {len(results)} articles")
        return results

    except Exception as e:
        print(f"  [DNW HTML] Error: {e}")
        return []
