# Exploration: db-migration

**Change**: Replace `companies.json` flat file with SQLite for user watchlist persistence.
**Date**: 2026-04-16

---

## Current State

### Data Layer (bot.py:70–107)

Five synchronous functions manage all persistence:

```
load_companies()         → reads entire JSON file every call
save_companies(data)     → writes entire JSON file every call
get_user_companies(id)   → load_companies().get(str(user_id), [])
add_company(id, t, e)    → load + modify + save (3 I/O ops per add)
remove_company(id, t)    → load + modify + save (3 I/O ops per remove)
```

**Data shape** (`companies.json`):
```json
{
  "123456789": [
    {"ticker": "AAPL", "empresa": "Apple Inc."},
    {"ticker": "YPFD.BA", "empresa": "YPF S.A."}
  ]
}
```

### Where these functions are called

| Caller | Function | Context |
|--------|----------|---------|
| `agregar` handler | `resolve_ticker` → `add_company` | async, via `run_in_executor` for blocking yfinance |
| `eliminar` handler | `remove_company` | async (direct call — currently BLOCKING in async context) |
| `limpiar` handler | `load_companies` + `save_companies` | async (direct call — currently BLOCKING) |
| `lista` handler | `get_user_companies` | async (direct call — BLOCKING) |
| `iniciar` handler | `get_user_companies` | async (direct call — BLOCKING) |
| `hourly_analysis` job | `get_user_companies` | async (direct call — BLOCKING) |
| `run_analysis` | `get_user_companies` + `add_company` | async (direct call — BLOCKING) |

**Discovery**: Most company function calls are currently blocking I/O inside async handlers without `run_in_executor`. This works in practice only because python-telegram-bot runs handlers in a thread pool, but it's architecturally incorrect and will cause issues at scale.

---

## Pain Points

### 1. Race conditions (HIGH RISK)
`load → modify → save` is not atomic. If two users trigger writes concurrently (e.g., two `/agregar` commands arriving at the same time), the second write will silently overwrite the first. The current architecture has no locking mechanism.

### 2. Full file I/O on every operation
Every read or write loads/dumps the entire JSON file. With 10 users and 10 companies each, this is fine. With 1000 users, this degrades linearly.

### 3. No query capability
Can't query "which users are watching AAPL" without loading and iterating everything. This blocks future features like "notify all watchers of AAPL when it moves 5%".

### 4. No persistence for future features
The README roadmap includes signal history persistence — this is impossible with the current flat-file structure without a major schema change.

### 5. No schema validation
Nothing prevents malformed data from entering `companies.json`. A corrupt file crashes the entire bot on next read.

---

## Migration Options

### Option A: sqlite3 (stdlib, sync)
- No new dependencies
- Same blocking pattern as today — still needs `run_in_executor`
- Transactions are native (atomic reads/writes)
- Simplest migration path

**Verdict**: Solves race conditions and atomicity. Doesn't improve async architecture.

### Option B: aiosqlite (async SQLite) ← RECOMMENDED
- One new dependency: `aiosqlite>=0.20.0` (wraps stdlib sqlite3 with async interface)
- Coroutine-based — fits naturally into existing async handlers
- Eliminates all `run_in_executor` calls for DB operations
- WAL mode can be enabled for concurrent reads + single-writer
- Lightweight: no ORM overhead

**Verdict**: Best fit for this codebase. Low dependency cost, native async, solves all identified issues.

### Option C: SQLAlchemy async
- Heavy ORM overhead
- Overkill for a bot with one table
- Adds complexity without proportional benefit

**Verdict**: Rejected. Over-engineered for this scope.

---

## Recommended Schema

```sql
CREATE TABLE IF NOT EXISTS watchlists (
    user_id  INTEGER NOT NULL,
    ticker   TEXT    NOT NULL,
    empresa  TEXT    NOT NULL,
    added_at TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, ticker)
);
```

- `PRIMARY KEY (user_id, ticker)` — enforces uniqueness, replaces the manual `any(c["ticker"] == ticker ...)` check
- `added_at` — free timestamp for future signal history queries
- No separate `users` table needed — user identity is implicit via `user_id`

---

## Files Affected

| File | Change |
|------|--------|
| `bot.py` | Replace 5 company functions with async equivalents; update all callers to `await` |
| `requirements.txt` | Add `aiosqlite>=0.20.0` |
| `db.py` (NEW) | Isolate all DB logic: init, CRUD functions |
| `migrate.py` (NEW) | One-time script to import existing `companies.json` into SQLite |
| `companies.json` | Kept as backup; renamed to `companies.json.bak` post-migration |

---

## Key Design Decisions

### Isolate DB in db.py
All database logic should live in a new `db.py` module, not in `bot.py`. This makes `bot.py` the orchestration layer and `db.py` the data layer — aligns with single responsibility. `bot.py` imports async functions from `db.py`.

### DB file path
`trading_bot.db` in the same directory as `bot.py` (consistent with how `companies.json` is located via `Path(__file__).parent`).

### WAL mode
Enable WAL (Write-Ahead Logging) on DB init: `PRAGMA journal_mode=WAL`. This allows concurrent reads while a write is in progress — critical for the hourly job reading while a user is modifying their list.

### Connection strategy
Use `aiosqlite.connect()` as an async context manager per operation (simple, no connection pooling needed at this scale). Can be upgraded to a persistent connection if needed.

---

## Migration Risk

**LOW** — the data model is simple (one logical table, small dataset). The main risk is the one-time data migration from JSON to SQLite. A migration script with validation and a JSON backup eliminates this risk.

**Rollback plan**: Keep `companies.json.bak`. If SQLite migration fails, rename back to `companies.json` and revert `bot.py`.

---

## Next Steps

→ `sdd-propose`: Define the proposal with scope, approach, and rollback plan.
