# Watchlist Persistence Specification

## Purpose

Define el comportamiento de la capa de persistencia de watchlists de usuario,
incluyendo inicialización de la base de datos, operaciones CRUD y migración
desde el formato legacy `companies.json`.

---

## Requirements

### Requirement: Database Initialization

El sistema MUST inicializar la base de datos SQLite al arrancar, creando ambas
tablas si no existen. El sistema MUST habilitar WAL mode para permitir lecturas
concurrentes sin bloqueo durante escrituras.

#### Scenario: Primera vez que arranca el bot

- GIVEN que no existe `trading_bot.db` en el directorio del bot
- WHEN el bot inicia
- THEN se crea `trading_bot.db` con las tablas `watchlists` y `signals`
- AND ambas tablas están vacías
- AND `PRAGMA journal_mode=WAL` está activo

#### Scenario: El bot reinicia con DB existente

- GIVEN que `trading_bot.db` ya existe con datos
- WHEN el bot inicia
- THEN las tablas NO son recreadas
- AND los datos existentes se preservan intactos

---

### Requirement: Legacy Migration

Si `companies.json` existe al momento de inicialización, el sistema MUST migrar
todos sus datos a `watchlists` antes de aceptar cualquier operación. El sistema
MUST renombrar `companies.json` a `companies.json.bak` solo tras migración exitosa.
El sistema MUST NOT renombrar el archivo si la migración falla.

#### Scenario: Migración exitosa desde JSON existente

- GIVEN que existe `companies.json` con N usuarios y sus tickers
- AND que NO existe `companies.json.bak`
- WHEN el bot inicia
- THEN todos los registros del JSON se insertan en `watchlists`
- AND el conteo de filas en `watchlists` es igual al total de pares (user_id, ticker) del JSON
- AND `companies.json` es renombrado a `companies.json.bak`
- AND `companies.json` ya no existe

#### Scenario: JSON vacío o sin usuarios

- GIVEN que existe `companies.json` con `{}` o sin entradas de usuarios
- WHEN el bot inicia
- THEN la migración concluye sin error
- AND `watchlists` permanece vacía
- AND `companies.json` es renombrado a `companies.json.bak`

#### Scenario: Falla durante la migración

- GIVEN que existe `companies.json` con datos válidos
- WHEN ocurre un error durante la inserción en SQLite
- THEN la transacción se revierte (rollback)
- AND `companies.json` NO es renombrado
- AND el bot loga el error y termina con código de salida no-cero

#### Scenario: Bot reinicia después de migración exitosa

- GIVEN que NO existe `companies.json` (ya fue renombrado a `.bak`)
- WHEN el bot inicia
- THEN la fase de migración se saltea sin error
- AND los datos en `watchlists` se preservan

---

### Requirement: Watchlist CRUD

El sistema MUST proveer operaciones atómicas para agregar, eliminar, listar y
limpiar la watchlist de un usuario. El sistema MUST NOT permitir duplicados de
ticker por usuario.

#### Scenario: Agregar ticker nuevo

- GIVEN que el usuario U no tiene el ticker T en su watchlist
- WHEN se agrega (U, T, empresa)
- THEN el registro aparece en `watchlists`
- AND la función retorna `True`

#### Scenario: Agregar ticker duplicado

- GIVEN que el usuario U ya tiene el ticker T en su watchlist
- WHEN se intenta agregar (U, T, cualquier empresa)
- THEN NO se inserta ningún registro adicional
- AND la función retorna `False`

#### Scenario: Eliminar ticker existente

- GIVEN que el usuario U tiene el ticker T en su watchlist
- WHEN se elimina T para U
- THEN el registro desaparece de `watchlists`
- AND la función retorna `True`

#### Scenario: Eliminar ticker inexistente

- GIVEN que el usuario U NO tiene el ticker T en su watchlist
- WHEN se intenta eliminar T para U
- THEN `watchlists` no cambia
- AND la función retorna `False`

#### Scenario: Listar watchlist vacía

- GIVEN que el usuario U no tiene ningún ticker
- WHEN se consulta la watchlist de U
- THEN se retorna una lista vacía `[]`

---

### Requirement: Future Signal History Readiness

El sistema MUST crear la tabla `signals` durante la inicialización aunque no sea
poblada por este change. La tabla MUST contener los campos necesarios para
registrar señales de ambos flows (IMAGE y HOURLY).

#### Scenario: Tabla signals disponible tras init

- GIVEN que el bot acaba de inicializarse
- WHEN se consulta el schema de `trading_bot.db`
- THEN existe la tabla `signals` con columnas: id, user_id, ticker, empresa,
  señal, tendencia, riesgo, precio_detectado, entrada, stop_loss, take_profit,
  analisis, instruccion, source, created_at
- AND la tabla está vacía
