# AI News Agent

A fully automated weekly AI news digest. Every Sunday evening it runs two searches
for the past week's top AI stories, summarises them in Czech using Claude, and
delivers a two-section styled HTML email to your inbox — then moves the sent copy
to Trash automatically.

---

## What it does

1. **Searches for AI news (×2)** — queries Tavily for the last 7 days across two topics:
   - 🤖 General AI news (`top artificial intelligence news this week`)
   - 🔬 AI in science & research (`artificial intelligence science research breakthroughs this week`)
   
   Results are automatically filtered — listing/category pages and articles behind a paywall (WSJ, FT, Bloomberg, NYT, and others) are excluded. A section is silently skipped if no freely accessible articles are found for it.
2. **Summarises in Czech** — sends both result sets to Claude (Haiku 4.5), which writes
   a two-section weekly digest as a styled HTML email compatible with Gmail and Yahoo Mail.
3. **Sends the email** — delivers the digest via Gmail SMTP to the configured recipient.
4. **Cleans up** — connects to Gmail via IMAP and moves the sent message to Trash so
   your Sent folder stays clean.
5. **Runs automatically** — scheduled via Windows Task Scheduler to fire every Sunday
   evening without any manual intervention.

---

## Email sections

| Section | Colour | Content |
|---|---|---|
| 🤖 AI Novinky | Blue | 4–5 top general AI news stories |
| 🔬 AI ve vědě a výzkumu | Green | 4–5 AI science & research breakthroughs |

Each section contains an intro summary paragraph followed by article cards with a
title, 1–2 sentence description, and a "Číst více →" link.

---

## Project structure

```
ai-news-agent/
├── ai-news-agent.py        # Main script
├── run-ai-news-agent.bat   # Launcher used by Task Scheduler
├── .env                    # Secrets (not committed to Git)
├── .gitignore              # Excludes .env and venv/
└── venv/                   # Python virtual environment (not committed to Git)
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

### 1. Create and activate the virtual environment

```bat
cd C:\Users\radim\AI_Engineer\ai-news-agent
python -m venv venv
venv\Scripts\activate
```

### 2. Install dependencies

```bat
pip install anthropic tavily-python python-dotenv
```

### 3. Create the `.env` file

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
run-ai-news-agent.bat
```

### 5. Schedule with Windows Task Scheduler

1. Open **Task Scheduler** → *Create Basic Task*
2. Set the trigger: **Weekly → Sunday** at your preferred time (e.g. 21:00)
3. Set the action: **Start a program**
   - Program: `C:\Users\radim\AI_Engineer\ai-news-agent\run-ai-news-agent.bat`
4. Finish and enable the task

---

## Configuration reference

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `TAVILY_API_KEY` | Yes | Tavily search API key |
| `EMAIL_SENDER` | Yes | Gmail address used to send |
| `EMAIL_RECIPIENT` | Yes | Address that receives the digest |
| `EMAIL_PASSWORD` | Yes | Gmail App Password (16 characters) |
| `SMTP_HOST` | No | SMTP host (default: `smtp.gmail.com`) |
| `SMTP_PORT` | No | SMTP port (default: `587`) |

---

## How it works — flow

```
Tavily search #1 — general AI news (last 7 days)
Tavily search #2 — AI science & research (last 7 days)
                  ↓
         Claude Haiku 4.5
    (two-section Czech HTML digest)
                  ↓
         Gmail SMTP send
                  ↓
       Gmail IMAP cleanup
   (move sent copy to Trash)
```
