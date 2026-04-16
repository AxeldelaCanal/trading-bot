# Proposal: db-migration

## Intent

Reemplazar `companies.json` con SQLite para eliminar race conditions en escrituras concurrentes, habilitar queries atómicas, y preparar el esquema para historial de señales futuro — sin agregar complejidad innecesaria.

## Scope

### In Scope
- Nuevo módulo `db.py` con toda la lógica de acceso a datos (async via `aiosqlite`)
- Schema SQLite con dos tablas: `watchlists` (activa) y `signals` (creada, vacía — future-ready)
- Migración one-time de `companies.json` → `trading_bot.db` via `migrate.py`
- Refactor de los 5 handlers en `bot.py` que llaman funciones de companies para usar `await db.*`
- WAL mode habilitado en init para lecturas concurrentes sin bloqueo

### Out of Scope
- Poblar la tabla `signals` (eso es el change `signal-history`)
- Comandos de usuario para ver historial
- Cualquier cambio a `prompts.py` o a los flows de GPT

## Capabilities

### New Capabilities
- `watchlist-persistence`: Persistencia de watchlists de usuario vía SQLite (reemplaza JSON file)

### Modified Capabilities
- None

## Approach

`aiosqlite` sobre `sqlite3` stdlib. Una dependencia nueva, interface async nativa, sin ORM overhead. Toda la lógica de DB se aísla en `db.py` — `bot.py` solo orquesta. El schema define `signals` ahora (vacía) para que el change `signal-history` no requiera schema migration.

### Schema

```sql
-- Watchlists (scope activo de este change)
CREATE TABLE IF NOT EXISTS watchlists (
    user_id  INTEGER NOT NULL,
    ticker   TEXT    NOT NULL,
    empresa  TEXT    NOT NULL,
    added_at TEXT    DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, ticker)
);

-- Signals (creada ahora, poblada por change futuro signal-history)
CREATE TABLE IF NOT EXISTS signals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL,
    ticker           TEXT    NOT NULL,
    empresa          TEXT    NOT NULL,
    señal            TEXT    NOT NULL CHECK(señal IN ('COMPRAR','VENDER','MANTENER')),
    tendencia        TEXT    CHECK(tendencia IN ('ALCISTA','BAJISTA','LATERAL')),
    riesgo           TEXT    CHECK(riesgo IN ('BAJO','MEDIO','ALTO')),
    precio_detectado REAL,
    entrada          REAL,
    stop_loss        REAL,
    take_profit      REAL,
    analisis         TEXT,
    instruccion      TEXT,
    source           TEXT    NOT NULL CHECK(source IN ('IMAGE','HOURLY')),
    created_at       TEXT    DEFAULT (datetime('now'))
);
```

## Affected Areas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `bot.py:70–107` | Modificado | 5 funciones sync → imports async de `db.py` |
| `bot.py` (callers) | Modificado | Agregar `await` en 7 call sites |
| `requirements.txt` | Modificado | Agregar `aiosqlite>=0.20.0` |
| `db.py` | Nuevo | Init DB, CRUD async, WAL pragma |
| `migrate.py` | Nuevo | Script one-time: JSON → SQLite con validación |
| `companies.json` | Renombrado | → `companies.json.bak` post-migración |

## Risks

| Riesgo | Prob | Mitigación |
|--------|------|------------|
| Data loss en migración | Baja | `migrate.py` valida row count antes de renombrar JSON |
| Call site sin `await` | Media | Revisar todos los callers explícitamente en tasks |
| `aiosqlite` incompatible con PTB thread pool | Baja | aiosqlite usa asyncio nativo, compatible |

## Rollback Plan

1. Renombrar `companies.json.bak` → `companies.json`
2. Revertir `bot.py` al commit anterior (`git checkout HEAD~1 bot.py`)
3. Remover `aiosqlite` de `requirements.txt`
4. Eliminar `db.py`, `migrate.py`, `trading_bot.db`

## Dependencies

- `aiosqlite>=0.20.0` (PyPI)

## Success Criteria

- [ ] `python migrate.py` importa todos los usuarios/tickers de `companies.json` sin pérdida
- [ ] `/agregar`, `/eliminar`, `/lista`, `/limpiar` funcionan igual que antes
- [ ] `/iniciar` lanza el job horario y lee watchlist desde SQLite correctamente
- [ ] Dos llamadas concurrentes a `/agregar` no corrompen datos
- [ ] `trading_bot.db` contiene tabla `signals` vacía (lista para signal-history)
