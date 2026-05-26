"""
Provider-agnostic email sender.

Defaults to Gmail SMTP, but can point at any SMTP relay (e.g. Brevo) via env
vars. Gmail blocks app-password logins from datacenter IPs (GitHub Actions),
so CI should use a transactional provider like Brevo / Resend / SendGrid.

Env vars (all optional; sensible fallbacks for backward compatibility):
  SMTP_HOST       default "smtp.gmail.com"   (Brevo: smtp-relay.brevo.com)
  SMTP_PORT       default "465"              (Brevo: 587)
  SMTP_USER       SMTP login; falls back to GMAIL_ADDRESS
  SMTP_PASSWORD   SMTP key/password; falls back to GMAIL_APP_PASSWORD
  EMAIL_FROM      From address — must be a verified sender on the provider;
                  falls back to SMTP_USER / GMAIL_ADDRESS
  NOTIFY_EMAIL_TO recipient address
"""
import os
import smtplib
from datetime import datetime
from email.utils import parsedate_to_datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# News categories in display order, with the short label used in the counts header.
CATEGORY_ORDER: list[tuple[str, str]] = [
    ("Sales & Acquisitions",   "Sales"),
    ("Disputes & Arbitration", "Disputes"),
    ("Takedowns & Seizures",   "Takedowns"),
    ("Policy & ICANN",         "Policy"),
    ("New gTLDs & Registry",   "gTLDs"),
    ("Security & Theft",       "Security"),
    ("Market & Investing",     "Market"),
    ("Other",                  "Other"),
]
_VALID_CATEGORIES = {name for name, _ in CATEGORY_ORDER}


def _fmt_date(raw: str) -> str:
    """Best-effort pretty date ('26 May 2026') from RFC-2822 or ISO-8601; '' if unparseable."""
    if not raw:
        return ""
    for parser in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            return parser(raw).strftime("%-d %b %Y")
        except Exception:
            continue
    return raw[:16]


def format_by_category(articles: list[dict]) -> str:
    """
    Build a plain-text email body grouping articles by news category.

    Each article is a normalized dict with keys:
      title, url, source, category, summary, sale_price, published
    Produces a counts header followed by fixed-order category sections.
    """
    # Bucket articles, coercing unknown/blank categories to "Other"
    buckets: dict[str, list[dict]] = {name: [] for name, _ in CATEGORY_ORDER}
    for art in articles:
        cat = art.get("category") or "Other"
        if cat not in _VALID_CATEGORIES:
            cat = "Other"
        buckets[cat].append(art)

    # Counts header — only non-zero categories, in fixed order
    counts = [f"{len(buckets[name])} {label}" for name, label in CATEGORY_ORDER if buckets[name]]
    lines: list[str] = []
    if counts:
        lines.append(" · ".join(counts))
        lines.append("")

    for name, _ in CATEGORY_ORDER:
        arts = buckets[name]
        if not arts:
            continue
        lines.append(f"── {name} ({len(arts)}) ──")
        for art in arts:
            title = art.get("title", "Untitled")
            price = (art.get("sale_price") or "").strip()
            title_line = f"  • {title}"
            if price:
                title_line += f"  [💰 {price}]"
            lines.append(title_line)

            meta = " · ".join(p for p in (_fmt_date(art.get("published", "")), art.get("source", "")) if p)
            if meta:
                lines.append(f"    {meta}")

            summary = (art.get("summary") or "").strip()
            if summary and not summary.startswith("[Summary pending"):
                lines.append(f"    {summary}")

            if art.get("url"):
                lines.append(f"    {art['url']}")
            lines.append("")
        lines.append("")

    return "\n".join(lines).rstrip()


def _cfg() -> dict:
    user = (os.environ.get("SMTP_USER") or os.environ.get("GMAIL_ADDRESS") or "").strip()
    pw = (os.environ.get("SMTP_PASSWORD") or os.environ.get("GMAIL_APP_PASSWORD") or "").replace(" ", "").strip()
    port_raw = (os.environ.get("SMTP_PORT") or "465").strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 465
    return {
        "host": (os.environ.get("SMTP_HOST") or "smtp.gmail.com").strip(),
        "port": port,
        "user": user,
        "password": pw,
        "from": (os.environ.get("EMAIL_FROM") or user).strip(),
        "to": (os.environ.get("NOTIFY_EMAIL_TO") or "").strip(),
    }


def is_configured() -> bool:
    """True if enough env vars are set to attempt sending."""
    c = _cfg()
    return bool(c["user"] and c["password"] and c["to"])


def send_email(subject: str, body_text: str) -> bool:
    """
    Send a plain-text email. Returns True on success, False otherwise.
    Picks SSL (port 465) or STARTTLS (any other port, e.g. 587) automatically.
    Never raises — a send failure must not crash the caller.
    """
    c = _cfg()
    if not (c["user"] and c["password"] and c["to"]):
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = c["from"]
    msg["To"] = c["to"]
    msg.attach(MIMEText(body_text, "plain"))

    try:
        if c["port"] == 465:
            with smtplib.SMTP_SSL(c["host"], c["port"], timeout=30) as s:
                s.login(c["user"], c["password"])
                s.sendmail(c["from"], c["to"], msg.as_string())
        else:
            with smtplib.SMTP(c["host"], c["port"], timeout=30) as s:
                s.ehlo()
                s.starttls()
                s.ehlo()
                s.login(c["user"], c["password"])
                s.sendmail(c["from"], c["to"], msg.as_string())
        print(f"  [Email] Sent to {c['to']} via {c['host']}")
        return True
    except Exception as e:
        print(f"  [Email] Failed to send via {c['host']}:{c['port']}: {e}")
        # Safe diagnostic — never prints the password value
        print(f"  [Email] (diagnostic: from={c['from']!r}, user={c['user']!r}, pw_len={len(c['password'])})")
        return False
