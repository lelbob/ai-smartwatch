# Athena — AI Personal Butler Bot

A personal AI assistant that runs as a Telegram bot. Understands natural language to manage tasks, set reminders, take notes, search the web, and deliver daily briefings — all timezone-aware.

## Features

- **Smart Reminders** — "Remind me next Friday at 5pm to read a book" stores the correct UTC time
- **Task Management** — Add, list, complete, and delete tasks with natural language ("delete the dog task", "clear everything")
- **Notes & Memory** — Save quick notes and long-term personal facts
- **Daily Briefing** — Summary of upcoming tasks, reminders, and weather
- **Web Search** — Live lookups via SearXNG for current events, weather, news
- **Voice Replies** — Optional TTS via Piper
- **Proactive Nudges** — Bot messages you when reminders are due

## Tech Stack

- Python 3.12
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- Google Gemini (Flash) for intent classification and chat
- [dateparser](https://dateparser.readthedocs.io/) for timezone-aware date parsing
- SQLite for persistent storage
- SearXNG for private web search

## Setup

> [!NOTE]
> If you need to install Python, configure local LLMs (Ollama/Gemma), set up FFmpeg, or download Text-to-Speech (Piper) voice models, please refer to the detailed [SETUP.md](file:///c:/Users/PC/Documents/the%20one%20that%20got%20away/SETUP.md) guide first.

### 1. Clone & create virtual environment
```bash
git clone https://github.com/lelbob/ai-smartwatch.git
cd ai-smartwatch
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 2. Configure environment
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GEMINI_API_KEY=your_gemini_api_key
ATHENA_LOCATION=Your City, Country
```

### 3. Run the bot
```bash
python -m athena.main
```

## Troubleshooting / Diagnostics

A built-in diagnostic tool lets you test any prompt directly without using Telegram:

```bash
# Test a single prompt
python -m scripts.troubleshoot "remind me next Friday at 5pm to read a book"

# List all active saved items
python -m scripts.troubleshoot --tasks

# Interactive REPL
python -m scripts.troubleshoot --interactive
```

## Running Tests

```bash
python -m pytest
```

## Project Structure

```
athena/
  main.py              — Entry point
  telegram_bot.py      — Telegram handler & bot setup
  tool_router.py       — Routes user messages to the right tool
  intent_classifier.py — LLM-based intent detection (Gemini Flash)
  reminders.py         — Reminder parsing, storage & scheduling
  tasks.py             — Task management
  briefing.py          — Daily briefing builder
  context_service.py   — User timezone & location resolution
  model_router.py      — LLM fallback chain (Flash → local)
  search_service.py    — SearXNG web search
  saved_items.py       — Unified saved items store
  database.py          — SQLite persistence layer
scripts/
  troubleshoot.py      — On-demand diagnostic CLI
tests/                 — Full pytest suite (79 tests)
```

## License

MIT
