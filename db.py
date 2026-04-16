import json
import logging
import aiofiles
import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).parent / "trading_bot.db"
_COMPANIES_JSON = Path(__file__).parent / "companies.json"

logger = logging.getLogger(__name__)

_conn: aiosqlite.Connection | None = None


async def init_db() -> None:
    """Inicializa la DB, crea tablas, habilita WAL y migra companies.json si existe."""
    global _conn
    _conn = await aiosqlite.connect(DB_PATH)
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.execute("PRAGMA foreign_keys=ON")

    await _conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlists (
            user_id  INTEGER NOT NULL,
            ticker   TEXT    NOT NULL,
            empresa  TEXT    NOT NULL,
            added_at TEXT    DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, ticker)
        )
    """)

    await _conn.execute("""
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
        )
    """)

    await _conn.commit()

    if _COMPANIES_JSON.exists():
        await _migrate_from_json()


async def _migrate_from_json() -> None:
    """Migra datos de companies.json → watchlists. Renombra a .bak solo tras éxito."""
    try:
        async with aiofiles.open(_COMPANIES_JSON, encoding="utf-8") as f:
            data = json.loads(await f.read())

        rows = [
            (int(user_id), company["ticker"], company["empresa"])
            for user_id, companies in data.items()
            for company in companies
        ]

        await _conn.executemany(
            "INSERT OR IGNORE INTO watchlists(user_id, ticker, empresa) VALUES (?,?,?)",
            rows,
        )
        await _conn.commit()

        bak_path = _COMPANIES_JSON.parent / f"{_COMPANIES_JSON.name}.bak"
        _COMPANIES_JSON.rename(bak_path)
        logger.info(f"type=DB_MIGRATION_OK | rows={len(rows)} | bak={bak_path.name}")

    except Exception as e:
        await _conn.rollback()
        logger.error(f"type=DB_MIGRATION_ERROR | error={e}", exc_info=True)
        raise


async def close_db() -> None:
    """Cierra la conexión. Idempotente."""
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


async def get_user_companies(user_id: int) -> list[dict]:
    """Retorna [{"ticker": str, "empresa": str}, ...]. Lista vacía si no hay."""
    async with _conn.execute(
        "SELECT ticker, empresa FROM watchlists WHERE user_id=? ORDER BY added_at",
        (user_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [{"ticker": r[0], "empresa": r[1]} for r in rows]


async def add_company(user_id: int, ticker: str, empresa: str) -> bool:
    """True si se agregó. False si ya existía (PK violation)."""
    try:
        await _conn.execute(
            "INSERT INTO watchlists(user_id, ticker, empresa) VALUES (?,?,?)",
            (user_id, ticker, empresa),
        )
        await _conn.commit()
        return True
    except aiosqlite.IntegrityError:
        return False


async def remove_company(user_id: int, ticker: str) -> bool:
    """True si existía y fue removido. False si no existía."""
    cursor = await _conn.execute(
        "DELETE FROM watchlists WHERE user_id=? AND ticker=?",
        (user_id, ticker),
    )
    await _conn.commit()
    return cursor.rowcount > 0


async def clear_companies(user_id: int) -> int:
    """Elimina todos los tickers del usuario. Retorna cantidad eliminada."""
    cursor = await _conn.execute(
        "DELETE FROM watchlists WHERE user_id=?",
        (user_id,),
    )
    await _conn.commit()
    return cursor.rowcount
