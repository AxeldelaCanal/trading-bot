# Tasks: db-migration

## Phase 1: Foundation — db.py + dependencia

- [x] 1.1 Agregar `aiosqlite>=0.20.0` a `requirements.txt`
- [x] 1.2 Crear `db.py`: definir `DB_PATH = Path(__file__).parent / "trading_bot.db"` y `_conn: aiosqlite.Connection | None = None`
- [x] 1.3 Implementar `init_db()`: CREATE TABLE IF NOT EXISTS `watchlists(user_id, ticker, empresa, added_at)` con PRIMARY KEY (user_id, ticker)
- [x] 1.4 Dentro de `init_db()`: CREATE TABLE IF NOT EXISTS `signals(id, user_id, ticker, empresa, señal, tendencia, riesgo, precio_detectado, entrada, stop_loss, take_profit, analisis, instruccion, source, created_at)` con CHECKs
- [x] 1.5 Dentro de `init_db()`: ejecutar `PRAGMA journal_mode=WAL` y `PRAGMA foreign_keys=ON`
- [x] 1.6 Dentro de `init_db()`: detectar `companies.json` → si existe, insertar todos los registros en `watchlists` en una transacción; en éxito renombrar a `.bak`; en error hacer ROLLBACK y raise
- [x] 1.7 Implementar `close_db()`: cerrar `_conn` si no es None; idempotente
- [x] 1.8 Implementar `get_user_companies(user_id: int) -> list[dict]`: SELECT ticker, empresa WHERE user_id=? ORDER BY added_at
- [x] 1.9 Implementar `add_company(user_id, ticker, empresa) -> bool`: INSERT; capturar `aiosqlite.IntegrityError` → return False; éxito → return True
- [x] 1.10 Implementar `remove_company(user_id, ticker) -> bool`: DELETE; return `cursor.rowcount > 0`
- [x] 1.11 Implementar `clear_companies(user_id: int) -> int`: DELETE WHERE user_id=?; return rowcount

## Phase 2: Wiring — bot.py

- [x] 2.1 Eliminar las 5 funciones sync de `bot.py`: `load_companies`, `save_companies`, `get_user_companies`, `add_company`, `remove_company`
- [x] 2.2 Agregar `import db` en los imports de `bot.py`
- [x] 2.3 Agregar `_on_startup(app)` y `_on_shutdown(app)` que llamen `await db.init_db()` / `await db.close_db()`
- [x] 2.4 Encadenar `.post_init(_on_startup).post_stop(_on_shutdown)` en `Application.builder()` en `main()`
- [x] 2.5 Handler `lista`: cambiar a `companies = await db.get_user_companies(user_id)`
- [x] 2.6 Handler `agregar`: cambiar a `await db.add_company(user_id, ticker, empresa)`
- [x] 2.7 Handler `eliminar`: cambiar a `removed = await db.remove_company(user_id, ticker)`
- [x] 2.8 Handler `limpiar`: reemplazar load/save por `count = await db.clear_companies(user_id)`
- [x] 2.9 Handler `iniciar`: cambiar a `companies = await db.get_user_companies(user_id)`
- [x] 2.10 Job `hourly_analysis`: cambiar a `companies = await db.get_user_companies(user_id)`
- [x] 2.11 Función `run_analysis`: `await db.get_user_companies(user_id)` — más `handle_text` pending_add: `await db.add_company(...)`

## Phase 3: Verificación manual (spec scenarios)

- [ ] 3.1 Spec: *Primera vez* — correr el bot sin `companies.json` ni `trading_bot.db`; verificar que la DB se crea con ambas tablas vacías
- [ ] 3.2 Spec: *Migración exitosa* — crear `companies.json` con al menos 2 usuarios y 3 tickers; arrancar bot; verificar `.bak` creado, `companies.json` eliminado, datos en `watchlists`
- [ ] 3.3 Spec: *Migración falla* — corromper el JSON antes del inicio; verificar que `companies.json` no se renombra y el bot no arranca
- [ ] 3.4 Spec: *Duplicate add* — `/agregar AAPL` dos veces; verificar que la segunda operación retorna el mensaje "ya tenías"
- [ ] 3.5 Spec: *Remove inexistente* — `/eliminar TICKER_NO_EXISTENTE`; verificar mensaje correcto sin excepción
- [ ] 3.6 Spec: *signals table* — inspeccionar `trading_bot.db` con `sqlite3 trading_bot.db ".schema"`; verificar que la tabla `signals` existe vacía con todos los campos
