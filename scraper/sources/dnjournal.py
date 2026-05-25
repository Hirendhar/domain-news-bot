"""
DN Journal — https://www.dnjournal.com
Scrapes latest articles from the domain name journal.
Method: RSS feed (HTML fallback)
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; domain-news-bot/1.0)",
}

SITE_URL = "https://www.dnjournal.com"
RSS_URL = "https://www.dnjournal.com/feed"


def fetch() -> list[dict]:
    """Returns list of articles from DN Journal."""
    articles = _fetch_rss()
    if not articles:
        articles = _fetch_html()
    return articles


def _fetch_rss() -> list[dict]:
    """Try RSS feed first."""
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

            if description:
                soup = BeautifulSoup(description, "lxml")
                description = soup.get_text(separator=" ", strip=True)[:600]

            if title and link:
                results.append({
                    "title": title,
                    "url": link,
                    "source": "DN Journal",
                    "date_found": datetime.now(timezone.utc).date().isoformat(),
                    "pub_date": pub_date,
                    "excerpt": description,
                })

        print(f"  [DNJ RSS] {len(results)} articles")
        return results

    except Exception as e:
        print(f"  [DNJ RSS] Error: {e}")
        return []


def _fetch_html() -> list[dict]:
    """
    Fallback: scrape the homepage and news page.
    DN Journal uses relative paths like 'articles/2026/...' and 'cover/2026/...'
    """
    results = []
    # Pages known to list articles
    pages = [SITE_URL, f"{SITE_URL}/news.htm"]

    # Paths that indicate a real article (not a nav/index page)
    ARTICLE_PATH_PREFIXES = ("articles/", "cover/", "lowdown/", "archive/2")

    # Nav/utility pages to skip
    SKIP_HREFS = {
        "domainsales.htm", "news.htm", "archive.htm", "aboutus.htm",
        "lowdown.htm", "ytd-sales-charts.htm", "newsletter-signup.htm",
        "classified.htm",
    }

    for page_url in pages:
        try:
            resp = requests.get(page_url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "lxml")

            for link_el in soup.select("a[href]"):
                href = link_el.get("href", "").strip()
                text = " ".join(link_el.get_text().split())  # normalise whitespace

                # Skip utility / nav / protection links
                if not href or href in SKIP_HREFS:
                    continue
                if "cdn-cgi" in href or "email-protection" in href:
                    continue
                if href.startswith(("mailto:", "#", "javascript:")):
                    continue
                if len(text) < 15:
                    continue

                # Build absolute URL
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    full_url = f"{SITE_URL}{href}"
                else:
                    # Relative path like "articles/2026/..." — resolve from site root
                    full_url = f"{SITE_URL}/{href}"

                # Only accept dnjournal.com URLs
                if "dnjournal.com" not in full_url:
                    continue

                # Only accept paths that look like articles
                path = full_url.replace(SITE_URL, "").lstrip("/")
                if not any(path.startswith(p) for p in ARTICLE_PATH_PREFIXES):
                    continue

                # Skip duplicated "Full Story" links (keep the descriptive title)
                if text.lower().startswith("full story"):
                    continue

                results.append({
                    "title": text[:200],
                    "url": full_url,
                    "source": "DN Journal",
                    "date_found": datetime.now(timezone.utc).date().isoformat(),
                    "pub_date": "",
                    "excerpt": "",
                })

        except Exception as e:
            print(f"  [DNJ HTML] Error on {page_url}: {e}")

    # Deduplicate by URL
    seen, unique = set(), []
    for item in results:
        if item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)

    print(f"  [DNJ HTML] {len(unique)} articles")
    return unique[:30]
