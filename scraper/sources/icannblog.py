"""
Domain Gang — https://domaingang.com
Domain industry commentary, sales, and news.
Method: RSS feed

Note: Originally planned for ICANN Blog but their site requires JavaScript rendering.
Domain Gang is a well-established domain news site with a reliable RSS feed.
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; domain-news-bot/1.0)"}
RSS_URL = "https://domaingang.com/feed/"
SOURCE_NAME = "Domain Gang"


def fetch() -> list[dict]:
    """Returns list of articles from Domain Gang."""
    try:
        resp = requests.get(RSS_URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  [Domain Gang] RSS returned {resp.status_code}")
            return []

        root = ET.fromstring(resp.text)
        results = []

        for item in root.findall(".//item"):
            title = item.findtext("title", "").strip()
            link  = item.findtext("link", "").strip()
            pub   = item.findtext("pubDate", "").strip()
            desc  = item.findtext("description", "").strip()

            if desc and "<" in desc:
                desc = BeautifulSoup(desc, "lxml").get_text(separator=" ", strip=True)[:600]
            elif desc:
                desc = desc[:600]

            if title and link:
                results.append({
                    "title":      title,
                    "url":        link,
                    "source":     SOURCE_NAME,
                    "date_found": datetime.now(timezone.utc).date().isoformat(),
                    "pub_date":   pub,
                    "excerpt":    desc,
                })

        print(f"  [Domain Gang] {len(results)} articles")
        return results

    except Exception as e:
        print(f"  [Domain Gang] Error: {e}")
        return []
