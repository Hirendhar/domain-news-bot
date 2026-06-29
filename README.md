# 🌐 Domain News Bot

Automatically scrapes new articles from **Domain Name Wire** and **DN Journal** every 6 hours, reads the full article, summarises it with AI, **writes an original full-length article** from the retrieved information, and saves everything to a **Notion database** — with links.

## What you get in Notion

Each article row has:
| Field | Description |
|---|---|
| **Title** | Article headline |
| **URL** | Direct link to the article |
| **Source** | Domain Name Wire / DN Journal |
| **Summary** | 3-4 sentence AI summary |
| **Key Points** | Bullet-point takeaways (3-5 points) |
| **Topics** | Auto-tagged: Domain Sales, ICANN, New gTLDs, etc. |
| **Date Found** | When the bot found it |
| **Status** | New → Read → Saved / Skip |

Each new row's **page body** also contains a full ~400-600 word original article
written by the AI from the retrieved source text, and a copy is saved locally
under `articles/<date>/` (gitignored).

### Article writing

After summarising, the bot writes a publishable, original news article for each
*new* item (one it hasn't stored before), grounded strictly in the fetched
source text — no invented facts. Controlled via env vars:

| Var | Default | Purpose |
|---|---|---|
| `WRITE_ARTICLES` | `1` | Set `0` to disable full-article generation |
| `MAX_ARTICLES` | `20` | Max articles written per run (protects Gemini quota) |
| `ARTICLES_DIR` | `articles` | Local folder for generated `.md` files |

---

## Setup (15 minutes, one-time)

### Step 1 — Get a free Gemini API key
1. Go to [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Click **Create API Key** → copy the key

### Step 2 — Create a Notion Integration
1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click **+ New integration**, name it `Domain News Bot`
3. Copy the **Internal Integration Token** (starts with `secret_`)

### Step 3 — Set up the Notion database
1. Create a new Notion page where you want the database to live
2. Share it with your integration: click `...` → **Connections** → add `Domain News Bot`
3. Copy the page URL — the Page ID is the last 32 characters:
   ```
   https://notion.so/My-Page-abc123def456abc123def456abc123de
                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
   ```

### Step 4 — Install & configure
```bash
cd domain-news-bot
pip install -r requirements.txt
cp .env.example .env
# Edit .env — fill in NOTION_TOKEN
python setup_notion.py <YOUR_PAGE_ID>
# → prints your NOTION_DATABASE_ID — add to .env
```

Your `.env` should have all three:
```
NOTION_TOKEN=secret_...
NOTION_DATABASE_ID=...
GEMINI_API_KEY=AIzaSy...
```

### Step 5 — Test locally
```bash
python -m scraper.main
```
Articles will appear in your Notion database within 1-2 minutes.

---

## Deploy to GitHub Actions (free, runs every 6 hours)

### Step 6 — Push to GitHub
```bash
git init && git add . && git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/domain-news-bot.git
git push -u origin main
```

### Step 7 — Add GitHub Secrets
**Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|---|---|
| `NOTION_TOKEN` | Your Notion integration token |
| `NOTION_DATABASE_ID` | Database ID from Step 4 |
| `GEMINI_API_KEY` | Your Gemini API key |

### Step 8 — Enable Actions
Go to the **Actions** tab → enable workflows.

The bot runs automatically at 00:00, 06:00, 12:00, 18:00 UTC.
You can also trigger it manually: **Actions → Domain News Bot → Run workflow**.

---

## Project structure

```
domain-news-bot/
├── scraper/
│   ├── main.py                  # Orchestrator: scrape → AI → Notion
│   └── sources/
│       ├── domainnamewire.py    # Domain Name Wire scraper
│       └── dnjournal.py         # DN Journal scraper
├── ai/
│   ├── client.py                # Gemini API client (auto model fallback)
│   ├── fetcher.py               # Full article text fetcher
│   ├── pipeline.py              # Batch AI summarisation
│   └── writer.py                # Full original article generation
├── storage/
│   └── notion_sync.py           # Notion push + deduplication
├── .github/workflows/
│   └── scraper.yml              # GitHub Actions (every 6 hours)
├── setup_notion.py              # One-time DB creation
├── requirements.txt
├── .env.example
└── .gitignore
```
