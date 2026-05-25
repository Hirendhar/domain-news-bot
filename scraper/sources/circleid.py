"""
CircleID — https://www.circleid.com
Domain policy, ICANN news, and internet infrastructure commentary.
Method: RSS feed
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; domain-news-bot/1.0)"}
RSS_URL = "http://feeds.circleid.com/cid_master/"


def fetch() -> list[dict]:
    """Returns list of articles from CircleID."""
    try:
        resp = requests.get(RSS_URL, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  [CircleID] RSS returned {resp.status_code}")
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
                    "source":     "CircleID",
                    "date_found": datetime.now(timezone.utc).date().isoformat(),
                    "pub_date":   pub,
                    "excerpt":    desc,
                })

        print(f"  [CircleID] {len(results)} articles")
        return results

    except Exception as e:
        print(f"  [CircleID] Error: {e}")
        return []
