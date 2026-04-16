# Design: db-migration

## Technical Approach

Módulo `db.py` que encapsula toda la lógica de acceso a SQLite via `aiosqlite`.
Conexión única persistente gestionada por el ciclo de vida del `Application` de PTB.
Migración automática integrada en `init_db()` — sin scripts externos.
`bot.py` pasa a ser puro orquestador: importa y `await`-ea funciones de `db.py`.

---

## Architecture Decisions

### Decision: Conexión persistente única vs pool vs per-operation

**Choice**: Una sola `aiosqlite.Connection` persistente a nivel de módulo.

**Alternatives considered**:

| Opción | Tradeoff | Descartada porque |
|--------|----------|-------------------|
| Per-operation (`async with aiosqlite.connect()`) | Simple, sin estado | Crea/destruye un thread OS por cada operación; overhead innecesario |
| Connection pool (asyncio.Queue de conexiones) | Máxima concurrencia | SQLite serializa writers a nivel de archivo igual; pool agrega complejidad sin beneficio real |
| **Conexión persistente única** ✅ | Un thread OS total, cero overhead por op | — |

**Rationale**: `aiosqlite` lanza un thread OS dedicado por conexión y despacha operaciones async via una cola interna. Con WAL mode, SQLite ya maneja múltiples lectores + un escritor sin contención. Múltiples conexiones no agregan throughput de escritura — solo multiplican threads. Una sola conexión es lo óptimo para este workload.

### Decision: Migración integrada en init_db() vs script externo

**Choice**: La migración ocurre dentro de `init_db()` al detectar `companies.json`.

**Alternatives considered**: `migrate.py` standalone que se corre manualmente antes del bot.

**Rationale**: El spec requiere que la migración ocurra _antes de aceptar cualquier operación_. Integrarlo en `init_db()` garantiza esa precondición sin depender de que el operador recuerde correr un script. Reduce superficie de error en deploy.

### Decision: Ciclo de vida via PTB post_init / post_stop

**Choice**: Conectar `init_db()` y `close_db()` a los hooks del `Application`.

**Rationale**: PTB expone `post_init` y `post_stop` exactamente para gestionar recursos async con el mismo event loop. Evita `asyncio.run()` anidado o `get_event_loop()` deprecado.

---

## Data Flow

```
Bot startup
    │
    ├─ Application.post_init ──→ db.init_db()
    │       │
    │       ├─ CREATE TABLE IF NOT EXISTS watchlists
    │       ├─ CREATE TABLE IF NOT EXISTS signals
    │       ├─ PRAGMA journal_mode=WAL
    │       └─ companies.json existe?
    │               ├─ SÍ → INSERT INTO watchlists (transacción)
    │               │         ├─ OK  → rename → companies.json.bak
    │               │         └─ ERR → ROLLBACK → raise → bot no arranca
    │               └─ NO → continúa
    │
Handler async (ej: /agregar)
    │
    ├─ await db.add_company(user_id, ticker, empresa)
    │       │
    │       └─ INSERT INTO watchlists  ←── _conn (módulo-nivel)
    │               ├─ OK             → return True
    │               └─ IntegrityError → return False (PK duplicada)
    │
Bot shutdown
    └─ Application.post_stop ──→ db.close_db() → _conn.close()
```

---

## File Changes

| Archivo | Acción | Descripción |
|---------|--------|-------------|
| `db.py` | Crear | Módulo de acceso a datos: init, migración, CRUD async |
| `bot.py` | Modificar | Reemplazar 5 funciones sync; agregar `await` en 7 call sites; hooks PTB |
| `requirements.txt` | Modificar | Agregar `aiosqlite>=0.20.0` |
| `companies.json` | → `.bak` | Renombrado automáticamente en runtime, no en deploy |

---

## Interfaces / Contracts

```python
# db.py — API pública

DB_PATH: Path  # Path(__file__).parent / "trading_bot.db"
_conn: aiosqlite.Connection | None  # módulo-nivel, privado

async def init_db() -> None:
    """Crea tablas, habilita WAL, migra companies.json si existe. Raise en fallo."""

async def close_db() -> None:
    """Cierra la conexión. Idempotente."""

async def get_user_companies(user_id: int) -> list[dict]:
    """Retorna [{"ticker": str, "empresa": str}, ...]. Lista vacía si no hay."""

async def add_company(user_id: int, ticker: str, empresa: str) -> bool:
    """True si se agregó. False si ya existía (PK violation)."""

async def remove_company(user_id: int, ticker: str) -> bool:
    """True si existía y fue removido. False si no existía."""

async def clear_companies(user_id: int) -> int:
    """Elimina todos los tickers del usuario. Retorna cantidad eliminada."""
```

```python
# bot.py — integración PTB

async def _on_startup(app: Application) -> None:
    await db.init_db()

async def _on_shutdown(app: Application) -> None:
    await db.close_db()

def main():
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(_on_startup)
        .post_stop(_on_shutdown)
        .build()
    )
```

---

## Testing Strategy

| Capa | Qué testear | Approach |
|------|-------------|----------|
| Unit | `add_company` duplicado → False; `remove_company` inexistente → False | DB en memoria (`:memory:`) |
| Integration | Migración completa: JSON → DB → .bak | Fixture con JSON temporal |
| Manual | `/agregar`, `/eliminar`, `/lista`, `/limpiar`, job horario | Bot en local con `.env` real |

> No hay test runner configurado. Las pruebas Unit/Integration son opcionales — el criterio de aceptación es manual per spec.

---

## Migration / Rollout

1. `pip install aiosqlite` (o `pip install -r requirements.txt`)
2. Arrancar el bot normalmente — la migración es automática
3. Verificar log: `type=DB_MIGRATION_OK | rows=N`
4. Verificar que `companies.json.bak` existe y `companies.json` no

**Rollback**: Ver `proposal.md` — sección Rollback Plan.

---

## Open Questions

- Ninguna. El diseño está completo y unambiguo.
