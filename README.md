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
| HTTP client | httpx |
| Variables de entorno | python-dotenv |
| Concurrencia | asyncio |

---

## Estructura del proyecto

```
trading-bot/
├── bot.py            # Lógica principal del bot
├── prompts.py        # System prompt para GPT-4o
├── requirements.txt  # Dependencias
├── .env.example      # Variables de entorno requeridas
├── Procfile          # Configuración de worker (Heroku/Render)
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

> **Límite:** 5 análisis por minuto por usuario.

---

## Disclaimer financiero

> Este bot es una herramienta educativa y experimental. Las recomendaciones generadas por inteligencia artificial **no constituyen asesoramiento financiero profesional**. Los mercados financieros implican riesgo de pérdida de capital. Siempre realizá tu propio análisis antes de operar y consultá a un asesor financiero habilitado si es necesario. El autor no se responsabiliza por decisiones de inversión tomadas en base a las señales de este bot.

---

## Próximos pasos

- [ ] **Migración a webhooks** — reemplazar el modo polling por un webhook HTTPS para mayor eficiencia y menor latencia.
- [ ] **Deploy en Render** — configurar el servicio web en [render.com](https://render.com) con variables de entorno gestionadas desde el dashboard.
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
| HTTP client | httpx |
| Environment variables | python-dotenv |
| Concurrency | asyncio |

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

- [ ] **Webhook migration** — replace polling with an HTTPS webhook for efficiency.
- [ ] **Deploy on Render** — configure a web service on [render.com](https://render.com).
- [ ] Signal history persistence per user.
- [ ] Multi-language support.
- [ ] Web dashboard with signal statistics.
