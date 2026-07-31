# AI News Agent

A fully automated weekly AI news digest. Every Sunday evening it runs two searches
for the past week's top AI stories, summarizes both sections in a single Claude
call in Czech, and delivers a two-section styled HTML email to your inbox — then
moves the sent copy to Trash automatically.

---

## What it does

1. **Searches for AI news (×2)** — queries Tavily once (no retry) for the last 7 days across two topics:

   - 🤖 General AI news (`top artificial intelligence news this week`)
   - 🔬 AI in science & research (`artificial intelligence science research breakthroughs this week`)

   Results are automatically filtered — listing/category pages and articles behind a paywall (WSJ, FT, Bloomberg, NYT, and others) are excluded. A section is silently skipped if no freely accessible articles are found for it.
2. **Summarizes in Czech (1 Claude call)** — sends both sections to Claude (Haiku 4.5)
   in a single request and receives one combined HTML fragment compatible with Gmail
   and Yahoo Mail.
3. **Sends the email** — delivers the digest via Gmail SMTP to the configured recipient.
4. **Cleans up** — connects to Gmail via IMAP and moves the sent message to Trash so
   your Sent folder stays clean.
5. **Runs automatically** — scheduled via GitHub Actions to fire every Sunday at
   21:00 Prague time, with no local machine or manual intervention required.

---

## AI disclosure (EU AI Act, Article 50)

This project emails AI-generated content (Claude) to a real recipient with no human
review before sending. The email itself carries a visible disclosure banner in the
body stating it was AI-generated and recommending readers verify against the original
source — see `ai-news-agent.py`.

---

## Email sections

| Section                    | Colour | Content                               |
| -------------------------- | ------ | ------------------------------------- |
| 🤖 AI Novinky              | Blue   | 3 top general AI news stories         |
| 🔬 AI ve vědě a výzkumu | Green  | 3 AI science & research breakthroughs |

Each section contains an intro summary paragraph followed by article cards with:

- title
- 2–3 sentence description
- **Hlavní poznatky:** 2–3 factual bullets
- **💡 Pro AI Engineera:** 1–2 practical bullets
- "Číst více →" link

---

## Project structure

```
ai-news-agent/
├── ai-news-agent.py                    # Main script
├── requirements.txt                    # Python dependencies
├── .github/workflows/ai-news-agent.yml # GitHub Actions schedule + workflow
├── .env                                # Secrets for local runs (not committed to Git)
├── .gitignore                          # Excludes .env and venv/
└── venv/                               # Python virtual environment (not committed to Git)
```

---

## Requirements

- Python 3.10+
- A [Tavily](https://tavily.com) API key
- An [Anthropic](https://console.anthropic.com) API key
- A Gmail account with:
  - IMAP enabled (*Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP*)
  - Auto-Expunge on (*same page — "Immediately update the server"*)
  - A 16-character [App Password](https://myaccount.google.com/apppasswords) (not your normal password)

---

## Setup

### 1. Create and activate the virtual environment (for local runs)

```bat
cd C:\Users\radim\AI_Engineer\ai-news-agent
python -m venv venv
venv\Scripts\activate
```

### 2. Install dependencies

```bat
pip install -r requirements.txt
```

### 3. Create the `.env` file (for local runs)

```
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
EMAIL_SENDER=you@gmail.com
EMAIL_RECIPIENT=you@gmail.com
EMAIL_PASSWORD=xxxx xxxx xxxx xxxx
```

Optional overrides (defaults shown):

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
```

### 4. Run manually to test

```bat
python ai-news-agent.py
```

### 5. Automatic scheduling via GitHub Actions

The workflow at [.github/workflows/ai-news-agent.yml](.github/workflows/ai-news-agent.yml)
runs the script automatically — no local machine needs to be on.

1. Add each `.env` variable as a **repository secret**
   (*Settings → Secrets and variables → Actions → New repository secret*):
   `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `EMAIL_SENDER`, `EMAIL_RECIPIENT`,
   `EMAIL_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`
2. The workflow triggers:
   - **On schedule** — Sundays at 19:00 UTC (21:00 Prague time during CEST/summer;
     20:00 during CET/winter, since GitHub Actions cron is fixed UTC and does not
     shift with local DST)
   - **On demand** — via the **Run workflow** button under the *Actions* tab
     (`workflow_dispatch`), useful for testing changes without waiting for Sunday

---

## Configuration reference

| Variable              | Required | Description                            |
| --------------------- | -------- | -------------------------------------- |
| `ANTHROPIC_API_KEY` | Yes      | Anthropic API key                      |
| `TAVILY_API_KEY`    | Yes      | Tavily search API key                  |
| `EMAIL_SENDER`      | Yes      | Gmail address used to send             |
| `EMAIL_RECIPIENT`   | Yes      | Address that receives the digest       |
| `EMAIL_PASSWORD`    | Yes      | Gmail App Password (16 characters)     |
| `SMTP_HOST`         | No       | SMTP host (default:`smtp.gmail.com`) |
| `SMTP_PORT`         | No       | SMTP port (default:`587`)            |

---

## Notes & troubleshooting

- **Gmail locale / IMAP folders:** The script moves the sent message to Trash using Gmail's Czech-localised IMAP folder names. If your Gmail account uses a different language, the cleanup step may fail. Either set your Gmail language to **Čeština (Czech)** or edit the `_trash_sent_email` function in `ai-news-agent.py` to use the correct IMAP folder names for your locale.
- **Anthropic model:** The script defaults to Anthropic's Haiku-tier model (Haiku 4.5). If you need to change the model, update the `CLAUDE_MODEL` constant at the top of `ai-news-agent.py`.
- **No-results behavior:** Each Tavily search is intentionally single-pass. If a section returns no freely accessible articles, that section is silently skipped and the digest will contain only the available section(s).
- **Checking scheduled runs:** Open the *Actions* tab on GitHub and select the "AI News Agent" workflow to see run history, logs, and any failures — no local log files are used.

## How it works — flow

```
Tavily search #1 — general AI news (last 7 days)
Tavily search #2 — AI science & research (last 7 days)
                  ↓
 Claude Haiku 4.5 call #1 (general + science in one request)
                  ↓
         Gmail SMTP send
                  ↓
       Gmail IMAP cleanup
   (move sent copy to Trash)
```
