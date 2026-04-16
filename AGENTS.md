# Code Review Rules - Axel's Trading Bot

## Python & Async
- Siempre usar 'async/await' para operaciones de I/O (especialmente con la DB).
- Seguir estándares PEP 8 para legibilidad.
- Manejar excepciones de forma explícita en los handlers de Telegram.

## Database (SQLite)
- Todas las consultas deben pasar por el módulo 'db.py'.
- Asegurar que las transacciones se cierren correctamente.
- Mantener el modo WAL activo para concurrencia.

## Tech Ops & Security
- No hardcodear API Keys (usar .env).
- Mantener el archivo openspec/ actualizado con cada cambio.
