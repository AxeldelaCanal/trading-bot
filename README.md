# Trading Bot — Análisis de Gráficos con IA

> **Español** | [English below](#english-version)

---

## Descripción

Bot de Telegram que analiza gráficos financieros usando **GPT-4o Vision** y devuelve recomendaciones de trading con niveles concretos de entrada, stop loss y take profit. Consulta precios en tiempo real a través de Yahoo Finance.

Soporta acciones, CEDEARs, índices y criptomonedas. Basta con enviar una captura de pantalla del gráfico.

---

## Stack técnico

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Bot framework | python-telegram-bot 21.x |
| Análisis de imagen | OpenAI GPT-4o Vision |
| Precios en tiempo real | yfinance |
| Base de datos | SQLite + aiosqlite (WAL mode) |
| HTTP client | httpx |
| I/O asíncrono de archivos | aiofiles |
| Variables de entorno | python-dotenv |
| Concurrencia | asyncio |
| Deploy | Render (webhook mode) |

---

## Estructura del proyecto

```
trading-bot/
├── bot.py            # Lógica principal: handlers, rate limiting, job queue
├── db.py             # Capa de base de datos (aiosqlite, WAL mode)
├── prompts.py        # Prompts de GPT-4o (imagen y análisis horario)
├── requirements.txt  # Dependencias
├── .env.example      # Variables de entorno requeridas
├── Procfile          # Configuración web para Render
└── README.md
```

---

## Variables de entorno

Copiá `.env.example` a `.env` y completá los valores:

```bash
cp .env.example .env
```

| Variable | Descripción |
|---|---|
| `TELEGRAM_TOKEN` | Token del bot obtenido desde [@BotFather](https://t.me/BotFather) |
| `OPENAI_API_KEY` | API key de OpenAI con acceso a GPT-4o |
| `WEBHOOK_URL` | URL pública del servidor (ej: `https://tu-app.onrender.com`). Si no está seteada, el bot corre en modo polling (útil para desarrollo local). |
| `PORT` | Puerto de escucha. Render lo setea automáticamente; no hace falta definirlo localmente. |

---

## Cómo correr localmente

### 1. Clonar el repositorio

```bash
git clone https://github.com/AxeldelaCanal/trading-bot.git
cd trading-bot
```

### 2. Crear entorno virtual e instalar dependencias

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Editá .env con tu editor preferido y completá los tokens
```

### 4. Ejecutar el bot

```bash
python bot.py
```

El bot quedará en modo polling. Abrí Telegram, buscá tu bot y enviá `/start`.

---

## Uso

1. Abrí el chat con el bot y enviá `/start`.
2. Enviá una captura de pantalla de cualquier gráfico financiero.
3. El bot responde con:
   - Señal: **COMPRAR / VENDER / MANTENER**
   - Precio actual de mercado (Yahoo Finance)
   - Niveles de entrada, take profit y stop loss
   - Análisis técnico resumido

**Comandos disponibles:**

| Comando | Descripción |
|---|---|
| `/start` | Inicia el bot y muestra la ayuda |
| `/agregar TICKER` | Agrega un activo a tu lista (ej: `/agregar AAPL`) |
| `/eliminar TICKER` | Elimina un activo de tu lista |
| `/lista` | Muestra tus activos guardados |
| `/limpiar` | Borra toda la lista |
| `/iniciar` | Activa el análisis automático cada hora |
| `/detener` | Detiene el análisis automático |

> **Límite:** 5 análisis por minuto por usuario.

---

## Disclaimer financiero

> Este bot es una herramienta educativa y experimental. Las recomendaciones generadas por inteligencia artificial **no constituyen asesoramiento financiero profesional**. Los mercados financieros implican riesgo de pérdida de capital. Siempre realizá tu propio análisis antes de operar y consultá a un asesor financiero habilitado si es necesario. El autor no se responsabiliza por decisiones de inversión tomadas en base a las señales de este bot.

---

## Roadmap

- [x] **Migración a SQLite** — reemplazar `companies.json` por base de datos con WAL mode y operaciones atómicas.
- [x] **Webhooks** — modo polling reemplazado por webhook HTTPS; polling disponible como fallback para desarrollo local.
- [x] **Deploy en Render** — servicio web configurado vía `Procfile` y variables de entorno.
- [ ] Persistencia de historial de señales por usuario.
- [ ] Soporte multi-idioma (inglés/español).
- [ ] Dashboard web con estadísticas de señales.

---

---

# English Version

## Description

A Telegram bot that analyzes financial charts using **GPT-4o Vision** and returns trading recommendations with concrete entry, stop loss, and take profit levels. It fetches real-time prices via Yahoo Finance.

Supports stocks, CEDEARs, indices, and cryptocurrencies. Just send a screenshot of any chart.

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Bot framework | python-telegram-bot 21.x |
| Image analysis | OpenAI GPT-4o Vision |
| Real-time prices | yfinance |
| Database | SQLite + aiosqlite (WAL mode) |
| HTTP client | httpx |
| Async file I/O | aiofiles |
| Environment variables | python-dotenv |
| Concurrency | asyncio |
| Deployment | Render (webhook mode) |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `OPENAI_API_KEY` | OpenAI API key with GPT-4o access |

---

## How to Run Locally

```bash
git clone https://github.com/AxeldelaCanal/trading-bot.git
cd trading-bot
python -m venv venv && source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # then edit .env with your tokens
python bot.py
```

---

## Financial Disclaimer

> This bot is an educational and experimental tool. AI-generated recommendations **do not constitute professional financial advice**. Financial markets involve risk of capital loss. Always do your own research before trading and consult a licensed financial advisor if needed. The author is not responsible for investment decisions made based on this bot's signals.

---

## Roadmap

- [x] **SQLite migration** — replaced `companies.json` with a proper database (WAL mode, atomic operations).
- [x] **Webhook support** — polling replaced by HTTPS webhook; polling available as local dev fallback.
- [x] **Render deployment** — web service configured via `Procfile` and environment variables.
- [ ] Signal history persistence per user.
- [ ] Multi-language support.
- [ ] Web dashboard with signal statistics.
