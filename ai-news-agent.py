"""AI News Agent.

Searches for the past week's top AI news with Tavily, summarizes it with Claude,
and emails the summary via SMTP.

Configuration is read from a .env file in the same directory:

    ANTHROPIC_API_KEY   - Anthropic API key
    TAVILY_API_KEY      - Tavily API key
    EMAIL_SENDER        - "from" address (e.g. you@gmail.com)
    EMAIL_RECIPIENT     - "to" address
    EMAIL_PASSWORD      - SMTP password / app password for the sender account
    SMTP_HOST           - SMTP server host   (optional, default: smtp.gmail.com)
    SMTP_PORT           - SMTP server port    (optional, default: 587)

For Gmail, EMAIL_PASSWORD must be a 16-character App Password
(https://myaccount.google.com/apppasswords), not your normal account password.
"""

import imaplib
import os
import smtplib
import sys
from datetime import date, timedelta
from email.message import EmailMessage
from urllib.parse import urlparse

import anthropic
from dotenv import load_dotenv
from tavily import TavilyClient

# Default to Haiku 4.5 — Anthropic's most capable Haiku-tier model.
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Czech month names in genitive case (used after a day number, e.g. "8. června 2026").
# Defined here so date formatting never relies on the system locale.
_CZECH_MONTHS = (
    "ledna", "února", "března", "dubna", "května", "června",
    "července", "srpna", "září", "října", "listopadu", "prosince",
)


def _fmt_date_cs(d: date) -> str:
    """Return *d* formatted in Czech, e.g. '8. června 2026'."""
    return f"{d.day}. {_CZECH_MONTHS[d.month - 1]} {d.year}"


def _is_article_url(url: str) -> bool:
    """Return True if the URL looks like a specific article rather than a listing page.

    Category/section pages (e.g. site.com/ai/ or site.com/) have very short URL
    paths and tend to link out to many articles instead of containing one story.
    Requiring at least 2 non-empty path segments filters most of them out.
    """
    try:
        segments = [s for s in urlparse(url).path.strip("/").split("/") if s]
        return len(segments) >= 2
    except Exception:
        return True  # keep the result if URL parsing fails


# Domains known to require a paid subscription for full article access.
_PAYWALLED_DOMAINS = {
    "wsj.com",
    "ft.com",
    "nytimes.com",
    "bloomberg.com",
    "thetimes.co.uk",
    "thetimes.com",
    "economist.com",
    "hbr.org",
    "wired.com",
    "theatlantic.com",
    "newyorker.com",
    "businessinsider.com",
    "forbes.com",
    "washingtonpost.com",
    "telegraph.co.uk",
    "spectator.co.uk",
    "seekingalpha.com",
    "barrons.com",
    "marketwatch.com",
}

# Minimum scraped content length (characters). Tavily returns only a short teaser
# when it hits a paywall, so anything below this threshold is likely gated.
_MIN_CONTENT_LENGTH = 200


def _is_freely_readable(result: dict) -> bool:
    """Return True if the article appears to be freely accessible."""
    url = result.get("url", "")
    try:
        host = urlparse(url).hostname or ""
        # Strip 'www.' prefix for comparison.
        domain = host.removeprefix("www.")
        # Check the domain itself and any parent domain (e.g. sub.wsj.com → wsj.com).
        parts = domain.split(".")
        for i in range(len(parts) - 1):
            if ".".join(parts[i:]) in _PAYWALLED_DOMAINS:
                return False
    except Exception:
        pass
    content = result.get("content", "")
    return len(content) >= _MIN_CONTENT_LENGTH


def search_ai_news(tavily: TavilyClient) -> tuple[list[dict], list[dict]]:
    """Run two Tavily searches and return (general_news, science_news)."""
    def _search(query: str, label: str) -> list[dict]:
        response = tavily.search(
            query=query,
            topic="news",
            days=7,
            max_results=10,
            search_depth="advanced",
            include_answer=False,
        )
        results = response.get("results", [])
        results = [
            r for r in results
            if _is_article_url(r.get("url", "")) and _is_freely_readable(r)
        ]
        if not results:
            print(f"No results returned for '{label}'.", file=sys.stderr)
        return results

    general = _search("top artificial intelligence news this week", "general AI news")
    science = _search(
        "artificial intelligence science research breakthroughs this week",
        "AI science & research",
    )
    return general, science



def summarize_with_claude(
    client: anthropic.Anthropic,
    general_articles: list[dict],
    science_articles: list[dict],
) -> str:
    """Summarize both article sets into a two-section styled HTML email digest (in Czech)."""

    def _build_sources(articles: list[dict]) -> str:
        return "\n\n".join(
            f"[{i}] {a.get('title', 'Untitled')}\n"
            f"URL: {a.get('url', '')}\n"
            f"Published: {a.get('published_date', 'n/a')}\n"
            f"Content: {a.get('content', '')}"
            for i, a in enumerate(articles, start=1)
        )

    today = date.today()
    week_start = today - timedelta(days=6)
    week_start_cs = _fmt_date_cs(week_start)
    today_cs = _fmt_date_cs(today)
    date_range_cs = f"{week_start_cs} – {today_cs}"

    # Build sources only for non-empty lists.
    general_sources = _build_sources(general_articles) if general_articles else None
    science_sources = _build_sources(science_articles) if science_articles else None

    # Reusable card template description for the prompt.
    card_template = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:16px;width:100%;">'
        "<tr>"
        '<td width="4" bgcolor="ACCENT_COLOR" style="background-color:ACCENT_COLOR;width:4px;">&nbsp;</td>'
        '<td bgcolor="#f8f9fa" style="background-color:#f8f9fa;padding:16px 20px;">'
        '<h3 style="margin:0 0 8px;color:HEADING_COLOR;font-size:17px;font-family:Arial,Helvetica,sans-serif;">HEADLINE IN CZECH</h3>'
        '<p style="margin:0 0 8px;color:#374151;font-size:14px;line-height:1.5;font-family:Arial,Helvetica,sans-serif;">'
        "DESCRIPTION 1 TO 2 SENTENCES IN CZECH</p>"
        '<p style="margin:0 0 4px;color:#374151;font-size:13px;font-weight:600;font-family:Arial,Helvetica,sans-serif;">Hlavní poznatky:</p>'
        '<ul style="margin:0 0 12px;padding-left:18px;color:#374151;font-size:13px;line-height:1.6;font-family:Arial,Helvetica,sans-serif;">'
        '<li style="margin-bottom:3px;">BULLET POINT 1 IN CZECH</li>'
        '<li style="margin-bottom:3px;">BULLET POINT 2 IN CZECH</li>'
        '<li style="margin-bottom:3px;">BULLET POINT 3 IN CZECH (OPTIONAL)</li>'
        "</ul>"
        '<p style="margin:0 0 4px;color:#374151;font-size:13px;font-weight:600;font-family:Arial,Helvetica,sans-serif;">&#128161; Pro AI Engineera:</p>'
        '<ul style="margin:0 0 12px;padding-left:18px;color:#374151;font-size:13px;line-height:1.6;font-family:Arial,Helvetica,sans-serif;">'
        '<li style="margin-bottom:3px;">PRACTICAL BULLET POINT 1 FOR AI ENGINEER IN CZECH</li>'
        '<li style="margin-bottom:3px;">PRACTICAL BULLET POINT 2 FOR AI ENGINEER IN CZECH (OPTIONAL)</li>'
        "</ul>"
        '<a href="SOURCE_URL" style="color:ACCENT_COLOR;text-decoration:none;font-size:13px;font-weight:600;font-family:Arial,Helvetica,sans-serif;">Číst více &rarr;</a>'
        "</td></tr></table>"
    )
    general_card = card_template.replace("ACCENT_COLOR", "#2563eb").replace(
        "HEADING_COLOR", "#1e3a8a"
    )
    science_card = card_template.replace("ACCENT_COLOR", "#059669").replace(
        "HEADING_COLOR", "#064e3b"
    )

    section_count = "TWO sections" if (general_articles and science_articles) else "one section"
    base_prompt = (
        f"Here are the results of AI news searches covering the past 7 days ({date_range_cs}).\n\n"
        f"Write a weekly digest ENTIRELY IN CZECH as the content of an HTML email with {section_count}.\n\n"
        "Return ONLY an HTML fragment — no <html>, <head>, or <body> tags, "
        "no ```html fences, and no extra text before or after the HTML.\n\n"
        "IMPORTANT: When mentioning any date in the text, write month names EXCLUSIVELY in Czech "
        "(ledna, února, března, dubna, května, června, července, srpna, září, října, listopadu, prosince). "
        "Do not use Slovak or Hungarian month names.\n\n"
        "CZECH LANGUAGE RULES:\n"
        "- Write simply and naturally so that a non-technical reader can understand the text.\n"
        "- For technical terms that do not translate well (e.g. inference, token, benchmark, "
        "fine-tuning, model), keep them in English and add a brief Czech explanation in brackets, "
        "for example: 'inference (generování odpovědi AI)'.\n"
        "- Avoid unusual or archaic Czech words — if unsure, use a simpler alternative.\n"
        "- Headlines should be clear and descriptive, not literal translations.\n\n"
        "- In each story card, include two separate blocks below the description:\n"
        "  1) 'Hlavní poznatky:' with 2 to 3 factual bullet points (what happened, why it matters, what was found).\n"
        "  2) '&#128161; Pro AI Engineera:' with 1 to 2 practical bullet points for an AI Engineer (what to watch, what to learn, and how it could be applied in practice).\n\n"
    )

    divider_html = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0;">'
        '<tr><td style="border-top:2px solid #e5e7eb;font-size:0;">&nbsp;</td></tr></table>'
    )

    def _call_claude(prompt: str) -> str:
        with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = stream.get_final_message()
        fragment = "".join(
            block.text for block in message.content if block.type == "text"
        ).strip()
        # Defensively strip a stray ```html ... ``` fence if the model adds one.
        if fragment.startswith("```"):
            fragment = fragment.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        # Strip prompt-separator lines if the model accidentally echoes them.
        fragment = "\n".join(
            line for line in fragment.splitlines() if not line.lstrip().startswith("═")
        ).strip()
        return fragment

    general_fragment = ""
    if general_articles:
        general_prompt = (
            base_prompt
            + "════════════════════════════════════════\n"
            + "SECTION 1 – General AI news\n"
            + "════════════════════════════════════════\n"
            + f"{general_sources}\n\n"
            + "For this section create:\n"
            + "1. Section heading EXACTLY in this format:\n"
            + '<h2 style="margin:0 0 12px;color:#1e3a8a;font-size:19px;font-family:Arial,Helvetica,sans-serif;">&#129302; AI Novinky</h2>\n'
            + "2. One summary paragraph in this format:\n"
            + '<p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;font-family:Arial,Helvetica,sans-serif;">ONE SENTENCE SUMMARY IN CZECH</p>\n'
            + "3. Then 6 to 8 of the most important and distinct cards EXACTLY in this format (skip duplicate stories):\n"
            + f"{general_card}\n\n"
            + "Translate all headlines and descriptions into Czech; leave URLs unchanged."
        )
        general_fragment = _call_claude(general_prompt)

    science_fragment = ""
    if science_articles:
        divider_instruction = (
            "Before this section insert a divider EXACTLY in this format:\n"
            + divider_html
            + "\n"
        ) if general_articles else ""
        science_prompt = (
            base_prompt
            + "════════════════════════════════════════\n"
            + "SECTION 2 – AI in science and research\n"
            + "════════════════════════════════════════\n"
            + f"{science_sources}\n\n"
            + divider_instruction
            + "For this section create:\n"
            + "1. Section heading EXACTLY in this format:\n"
            + '<h2 style="margin:0 0 12px;color:#064e3b;font-size:19px;font-family:Arial,Helvetica,sans-serif;">&#128300; AI ve v&#283;d&#283; a v&#253;zkumu</h2>\n'
            + "2. One summary paragraph in this format:\n"
            + '<p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;font-family:Arial,Helvetica,sans-serif;">ONE SENTENCE SUMMARY IN CZECH</p>\n'
            + "3. Then 6 to 8 of the most important and distinct cards EXACTLY in this format (skip duplicate stories):\n"
            + f"{science_card}\n\n"
            + "Translate all headlines and descriptions into Czech; leave URLs unchanged."
        )
        science_fragment = _call_claude(science_prompt)
        # We insert the divider ourselves between fragments below.
        if science_fragment.startswith(divider_html):
            science_fragment = science_fragment[len(divider_html):].lstrip()

    if general_fragment and science_fragment:
        body = f"{general_fragment}\n\n{divider_html}\n{science_fragment}"
    elif general_fragment:
        body = general_fragment
    else:
        body = science_fragment

    # Wrap the model's content in a Yahoo Mail-compatible table-based email shell.
    # - Table layout instead of divs (Yahoo strips unsupported block elements)
    # - bgcolor attributes alongside background-color styles (Yahoo ignores CSS-only bg)
    # - No CSS gradients (Yahoo strips them); solid #1e3a8a header instead
    # - font-family on every element (Yahoo resets inherited fonts)
    # - No opacity shorthand; explicit colour values instead
    return f"""\
<!DOCTYPE html>
<html lang="cs">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#eef2f7;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#eef2f7" style="background-color:#eef2f7;">
    <tr>
      <td align="center" style="padding:24px;">
        <table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;width:100%;">
          <tr>
            <td bgcolor="#1e3a8a" style="background-color:#1e3a8a;padding:24px 28px;border-radius:8px 8px 0 0;">
              <h1 style="margin:0;font-size:22px;color:#ffffff;font-family:Arial,Helvetica,sans-serif;">&#129302; T&#253;denn&#237; p&#345;ehled AI novinek</h1>
              <p style="margin:6px 0 0;font-size:14px;color:#d1d5db;font-family:Arial,Helvetica,sans-serif;">{date_range_cs}</p>
            </td>
          </tr>
          <tr>
            <td bgcolor="#ffffff" style="background-color:#ffffff;padding:24px 28px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;border-bottom:1px solid #e5e7eb;font-family:Arial,Helvetica,sans-serif;">
              {body}
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:16px 0;">
              <p style="margin:0;color:#9ca3af;font-size:12px;font-family:Arial,Helvetica,sans-serif;">Automaticky vygenerov&#225;no pomoc&#237; Tavily a Claude.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_email(summary: str) -> None:
    """Send the HTML summary to the configured recipient via SMTP."""
    sender = os.environ["EMAIL_SENDER"]
    recipient = os.environ["EMAIL_RECIPIENT"]
    password = os.environ["EMAIL_PASSWORD"]
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))

    today = date.today()
    week_start_cs = _fmt_date_cs(today - timedelta(days=6))
    today_cs = _fmt_date_cs(today)
    msg = EmailMessage()
    msg["Subject"] = f"Týdenní přehled AI novinek – {week_start_cs} až {today_cs}"
    msg["From"] = sender
    msg["To"] = recipient
    # Plain-text fallback for clients that can't render HTML, then the HTML body.
    msg.set_content(
        "Tento e-mail obsahuje týdenní přehled AI novinek ve formátu HTML. "
        "Zobrazte jej prosím v e-mailovém klientovi s podporou HTML."
    )
    msg.add_alternative(summary, subtype="html")

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)

    print(f"Summary emailed to {recipient}.")
    _trash_sent_email(sender, password, msg["Subject"])


def _trash_sent_email(sender: str, password: str, subject: str) -> None:
    """Move the just-sent message from Gmail's Sent folder to Trash via IMAP."""
    with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
        imap.login(sender, password)

        # # List and print all available IMAP folders for diagnostics.
        # status, folder_list = imap.list()
        # if status == "OK":
        #     print("Available IMAP folders:")
        #     for folder in folder_list:
        #         print(" ", folder.decode() if isinstance(folder, bytes) else folder)

        # Gmail exposes the Sent folder under the Czech-locale UTF-7 encoded name.
        status, _ = imap.select('"[Gmail]/Odeslan&AOE- po&AWE-ta"', readonly=False)
        if status != "OK":
            print("Could not open Gmail Sent folder; skipping trash step.", file=sys.stderr)
            return

        # Search for messages sent today to avoid trashing an unrelated old message.
        status, data = imap.search(None, "ON", date.today().strftime("%d-%b-%Y"))
        if status != "OK" or not data or not data[0]:
            print("No messages sent today found in Sent folder; skipping trash step.", file=sys.stderr)
            return

        # data[0] is a space-separated list of message sequence numbers in order.
        target_id = data[0].split()[-1]

        # Copy to Trash, then mark the original as deleted and expunge.
        imap.copy(target_id, '"[Gmail]/Ko&AWE-"')
        imap.store(target_id, "+FLAGS", "\\Deleted")
        imap.expunge()

    print("Sent message moved to Trash.")


def main() -> None:
    load_dotenv()

    # Fail early with a clear message if any required variable is missing.
    required = [
        "ANTHROPIC_API_KEY",
        "TAVILY_API_KEY",
        "EMAIL_SENDER",
        "EMAIL_RECIPIENT",
        "EMAIL_PASSWORD",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        sys.exit(f"Missing required .env variables: {', '.join(missing)}")

    tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    claude = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    print("Searching for this week's AI news...")
    general_articles, science_articles = search_ai_news(tavily)
    if not general_articles and not science_articles:
        sys.exit("No articles found; nothing to summarize.")
    if not general_articles:
        print("Warning: no general AI news articles found; that section will be skipped.", file=sys.stderr)
    if not science_articles:
        print("Warning: no AI science/research articles found; that section will be skipped.", file=sys.stderr)

    print(
        f"Summarizing {len(general_articles)} general + "
        f"{len(science_articles)} science articles with Claude..."
    )
    summary = summarize_with_claude(claude, general_articles, science_articles)

    print("Sending email...")
    send_email(summary)


if __name__ == "__main__":
    main()
