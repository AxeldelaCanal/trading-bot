# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the bot

```bash
pip install -r requirements.txt
python bot.py
```

Requires a `.env` file with `TELEGRAM_TOKEN` and `OPENAI_API_KEY`.

To stop a running instance on Windows: `powershell -Command "Get-Process python | Stop-Process -Force"`

There are no tests or linting configured.

## Architecture

Single-process async Telegram bot with two entry points into GPT-4o:

**Image analysis flow** (`analyze_image` → `run_analysis`): photo → base64 → GPT-4o Vision with `SYSTEM_PROMPT` → strict JSON → `build_response_message`. Serialized by `gpt_semaphore = asyncio.Semaphore(1)`.

**Hourly text flow** (`hourly_analysis` job → `run_text_analysis_for_ticker`): triggered by `job_queue.run_repeating` per user → yfinance market data → `HOURLY_ANALYSIS_PROMPT` → same JSON schema → `build_response_message`.

Both flows share the same JSON response schema and formatter.

## Key design details

- **`prompts.py`** — edit prompts here, not in `bot.py`. Contains `SYSTEM_PROMPT` (image) and `HOURLY_ANALYSIS_PROMPT` (text).
- **`db.py`** — all database logic. Exposes async functions: `init_db`, `close_db`, `get_user_companies`, `add_company`, `remove_company`, `clear_companies`. Uses a single persistent `aiosqlite` connection (`_conn`) with WAL mode. Do not access SQLite anywhere else.
- **`trading_bot.db`** — SQLite database with two tables: `watchlists(user_id, ticker, empresa, added_at)` and `signals` (empty, reserved for future signal history). Created automatically on first run.
- **Legacy migration** — if `companies.json` is present at startup, `init_db()` migrates it to `watchlists` and renames it to `companies.json.bak`. This is automatic and one-time.
- **`resolve_ticker(ticker)`** — tries ticker as-is, then appends `.BA` for Buenos Aires Stock Exchange fallback (e.g. `YPFD` → `YPFD.BA`). Blocking — call via `run_in_executor`.
- **Pending state dicts** — `pending_sell` and `pending_add` are in-memory dicts keyed by `user_id`, reset on restart. `handle_text` checks `pending_sell` first.
- **Rate limiting** — sliding window via `user_request_times` (5 req/60s per user, in-memory).
- **Job queue** — jobs named `hourly_{user_id}` for lookup/cancellation. Requires `python-telegram-bot[job-queue]`.
- **DB lifecycle** — `init_db()` runs via `Application.post_init`, `close_db()` via `Application.post_stop`. Never call these manually.

## Deployment

`Procfile`: `worker: python bot.py`. Polling mode. Planned next step: migrate to webhooks for Render.
