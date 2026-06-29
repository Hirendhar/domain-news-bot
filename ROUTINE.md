# Daily "Article Ideas" Claude Routine (no Gemini API key)

This sets up a **Claude Code Routine** that emails you, every day at **8:00am IST**,
a brief of the last 24h of domain news plus **5–7 original article ideas to write**.
The ideas are written by **Claude inside the routine session** — no `GEMINI_API_KEY`
is used. The only credentials needed are your Notion token and email (SMTP) settings.

How it works each morning:

1. `python news_brief.py fetch` prints the last-24h news from your Notion DB.
2. Claude reads it and writes 5–7 grounded article ideas to `ideas.txt`.
3. `python news_brief.py email ideas.txt` emails you the news + ideas.

---

## One-time setup

Routines are created at **[claude.ai/code/routines](https://claude.ai/code/routines)**
(or with `/schedule` from your **local** terminal — the command is hidden inside
web sessions). Routines clone your repo's **default branch**, so first **merge this
PR into `main`** (or add a `git checkout` step to the prompt — see note below).

### 1. Create the routine

- **New routine** → name it `Daily domain article ideas`.
- **Repository**: `hirendhar/domain-news-bot`.
- **Prompt**: paste the prompt from the next section.
- **Schedule trigger**: `Daily`, time `8:00 AM` (entered in your local zone — IST —
  and converted automatically; runs may start a few minutes late due to stagger).
- **Connectors**: remove any you don't need (this routine needs none).

### 2. Environment (network + secrets)

Edit the routine's environment:

- **Environment variables** (NOT `GEMINI_API_KEY`):
  - `NOTION_TOKEN`, `NOTION_DATABASE_ID`
  - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `NOTIFY_EMAIL_TO`
    (or the `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` fallbacks)
- **Setup script**: `pip install -r requirements.txt`
- **Network access**: the **Default (Trusted)** policy blocks Notion and SMTP, so set
  **Network access → Custom** and allow:
  - `api.notion.com`
  - your SMTP host, e.g. `smtp-relay.brevo.com`

  (or use **Full** access if you prefer not to maintain an allowlist).

### 3. Test it

Click **Run now** on the routine and open the run session to confirm the email
arrives. Then it will run automatically every day at 8am IST.

---

## The routine prompt

```
Generate today's domain-name-industry "article ideas to write" brief and email it to me.

Steps:
1. Run: python news_brief.py fetch
   This prints the domain-industry news found in the last 24 hours (from the Notion DB).
2. If the output begins with "NO_ARTICLES", stop now — send nothing and end the run.
3. Otherwise, read the news and write 5-7 ORIGINAL article ideas a domain-industry
   writer could publish — fresh angles, not rewrites of the stories. For each idea,
   one line formatted as:
     <number>. <working title> — <one sentence on the angle and why it's timely>
   Ground every idea strictly in the news above. Do NOT invent facts, names, prices,
   or figures that aren't in the source. Favour cross-story trends, explainers,
   "what it means for investors/registrars", and follow-up questions raised.
4. Write those numbered ideas (and nothing else) to ideas.txt in the repo root.
5. Run: python news_brief.py email ideas.txt
   This emails me the news plus your ideas.

Do not push any branches or open any pull requests.
```

> **Note — before merging to `main`:** the routine clones `main`, which won't have
> `news_brief.py` until this PR is merged. To trial it on the branch first, add this
> as step 0 in the prompt:
> `Run: git checkout claude/news-bot-article-generation-1b9ss3`

---

## Managing it

- Pause/resume: toggle **Repeats** on the routine's detail page.
- Change time or prompt: the pencil (**Edit routine**) icon.
- From your local CLI: `/schedule list`, `/schedule update`, `/schedule run`.
