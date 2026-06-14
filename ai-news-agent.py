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
from datetime import date
from email.message import EmailMessage

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
    week_start = today.replace(day=today.day - 6)
    week_start_cs = _fmt_date_cs(week_start)
    today_cs = _fmt_date_cs(today)
    date_range_cs = f"{week_start_cs} – {today_cs}"

    general_sources = _build_sources(general_articles)
    science_sources = _build_sources(science_articles)

    # Reusable card template description for the prompt.
    card_template = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:16px;width:100%;">'
        "<tr>"
        '<td width="4" bgcolor="ACCENT_COLOR" style="background-color:ACCENT_COLOR;width:4px;">&nbsp;</td>'
        '<td bgcolor="#f8f9fa" style="background-color:#f8f9fa;padding:16px 20px;">'
        '<h3 style="margin:0 0 8px;color:HEADING_COLOR;font-size:17px;font-family:Arial,Helvetica,sans-serif;">NADPIS V ČEŠTINĚ</h3>'
        '<p style="margin:0 0 12px;color:#374151;font-size:14px;line-height:1.5;font-family:Arial,Helvetica,sans-serif;">'
        "POPIS 1 AŽ 2 VĚTY V ČEŠTINĚ</p>"
        '<a href="URL_ZDROJE" style="color:ACCENT_COLOR;text-decoration:none;font-size:13px;font-weight:600;font-family:Arial,Helvetica,sans-serif;">Číst více &rarr;</a>'
        "</td></tr></table>"
    )
    general_card = card_template.replace("ACCENT_COLOR", "#2563eb").replace(
        "HEADING_COLOR", "#1e3a8a"
    )
    science_card = card_template.replace("ACCENT_COLOR", "#059669").replace(
        "HEADING_COLOR", "#064e3b"
    )

    prompt = (
        f"Zde jsou výsledky dvou vyhledávání zpráv o umělé inteligenci za posledních 7 dní ({date_range_cs}).\n\n"
        "Napiš týdenní přehled CELÝ V ČEŠTINĚ jako obsah HTML e-mailu se DVĚMA oddíly.\n\n"
        "Vrať POUZE HTML fragment — žádné značky <html>, <head> nebo <body>, "
        "žádné ohraničení ```html a žádný text navíc před nebo za HTML.\n\n"
        "DŮLEŽITÉ: Pokud uvádíš jakékoli datum v textu, piš názvy měsíců VÝHRADNĚ v češtině "
        "(ledna, února, března, dubna, května, června, července, srpna, září, října, listopadu, prosince). "
        "Nepoužívej slovenské ani maďarské názvy měsíců.\n\n"
        "════════════════════════════════════════\n"
        "ODDÍL 1 – Obecné AI novinky\n"
        "════════════════════════════════════════\n"
        f"{general_sources}\n\n"
        "Pro tento oddíl vytvoř:\n"
        "1. Nadpis oddílu PŘESNĚ v tomto formátu:\n"
        '<h2 style="margin:0 0 12px;color:#1e3a8a;font-size:19px;font-family:Arial,Helvetica,sans-serif;">&#129302; AI Novinky</h2>\n'
        "2. Jeden shrnující odstavec ve formátu:\n"
        '<p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;font-family:Arial,Helvetica,sans-serif;">JEDNA VĚTA SHRNUTÍ</p>\n'
        "3. Poté 3 až 5 nejdůležitějších karet PŘESNĚ v tomto formátu (vynech duplicitní zprávy):\n"
        f"{general_card}\n\n"
        "════════════════════════════════════════\n"
        "ODDÍL 2 – AI ve vědě a výzkumu\n"
        "════════════════════════════════════════\n"
        f"{science_sources}\n\n"
        "Před tímto oddílem vlož oddělovač PŘESNĚ v tomto formátu:\n"
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0;">'
        '<tr><td style="border-top:2px solid #e5e7eb;font-size:0;">&nbsp;</td></tr></table>\n'
        "Pro tento oddíl vytvoř:\n"
        "1. Nadpis oddílu PŘESNĚ v tomto formátu:\n"
        '<h2 style="margin:0 0 12px;color:#064e3b;font-size:19px;font-family:Arial,Helvetica,sans-serif;">&#128300; AI ve v&#283;d&#283; a v&#253;zkumu</h2>\n'
        "2. Jeden shrnující odstavec ve formátu:\n"
        '<p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;font-family:Arial,Helvetica,sans-serif;">JEDNA VĚTA SHRNUTÍ</p>\n'
        "3. Poté 3 až 5 nejdůležitějších karet PŘESNĚ v tomto formátu (vynech duplicitní zprávy):\n"
        f"{science_card}\n\n"
        "Nadpisy a popisy přelož a napiš v češtině; URL ponech beze změny."
    )

    # Stream the response so a long digest can't hit a request timeout.
    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    body = "".join(
        block.text for block in message.content if block.type == "text"
    ).strip()

    # Defensively strip a stray ```html ... ``` fence if the model adds one.
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

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
    week_start_cs = _fmt_date_cs(today.replace(day=today.day - 6))
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

    print(
        f"Summarizing {len(general_articles)} general + "
        f"{len(science_articles)} science articles with Claude..."
    )
    summary = summarize_with_claude(claude, general_articles, science_articles)

    print("Sending email...")
    send_email(summary)


if __name__ == "__main__":
    main()
