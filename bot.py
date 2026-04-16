import os
import json
import logging
import base64
import asyncio
import time
import httpx
import yfinance as yf
from collections import defaultdict
import db
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from dotenv import load_dotenv
from prompts import SYSTEM_PROMPT, HOURLY_ANALYSIS_PROMPT

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

pending_sell: dict[int, str] = {}
pending_add: dict[int, dict] = {}
gpt_semaphore = asyncio.Semaphore(1)

RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 60
user_request_times: dict[int, list[float]] = defaultdict(list)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def log_request(user_id: int, request_type: str, extra: str = ""):
    msg = f"user_id={user_id} | type={request_type}"
    if extra:
        msg += f" | {extra}"
    logger.info(msg)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def is_rate_limited(user_id: int) -> bool:
    now = time.monotonic()
    user_request_times[user_id] = [t for t in user_request_times[user_id] if now - t < RATE_LIMIT_WINDOW]
    if len(user_request_times[user_id]) >= RATE_LIMIT_MAX:
        return True
    user_request_times[user_id].append(now)
    return False


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

def get_market_data(ticker: str) -> dict:
    try:
        stock = yf.Ticker(ticker)
        fi = stock.fast_info
        precio_actual = fi.last_price or fi.previous_close
        precio_anterior = fi.previous_close

        cambio_hoy = "N/A"
        if precio_actual and precio_anterior and precio_anterior != 0:
            cambio_pct = ((precio_actual - precio_anterior) / precio_anterior) * 100
            cambio_hoy = f"{cambio_pct:+.2f}%"

        max_52w = fi.year_high
        min_52w = fi.year_low

        hist = stock.history(period="5d")
        tendencia_5d = "N/A"
        if not hist.empty and len(hist) >= 2:
            cambio_5d = ((hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0]) * 100
            tendencia_5d = f"{cambio_5d:+.2f}%"

        if precio_actual is None:
            return {"ok": False}

        return {
            "ok": True,
            "precio_actual": round(precio_actual, 2),
            "cambio_hoy": cambio_hoy,
            "tendencia_5d": tendencia_5d,
            "max_52w": round(max_52w, 2) if max_52w else "N/A",
            "min_52w": round(min_52w, 2) if min_52w else "N/A",
        }
    except Exception as e:
        logger.warning(f"user_id=N/A | type=MARKET_DATA | ticker={ticker} | error={e}")
        return {"ok": False}


def get_company_name(ticker: str) -> str:
    try:
        info = yf.Ticker(ticker).info
        return info.get("longName") or info.get("shortName") or ticker
    except Exception:
        return ticker


def resolve_ticker(ticker: str) -> tuple[str, dict]:
    """Intenta obtener datos para el ticker. Si falla, prueba con sufijo .BA (Bolsa de Buenos Aires)."""
    market = get_market_data(ticker)
    if market["ok"]:
        return ticker, market
    # Fallback para acciones argentinas (ej: YPFD → YPFD.BA)
    if "." not in ticker:
        ticker_ba = f"{ticker}.BA"
        market_ba = get_market_data(ticker_ba)
        if market_ba["ok"]:
            return ticker_ba, market_ba
    return ticker, {"ok": False}


# ---------------------------------------------------------------------------
# GPT analysis helpers
# ---------------------------------------------------------------------------

def build_response_message(data: dict, market: dict) -> str:
    ticker    = data.get("ticker", "")
    señal     = data.get("señal", "").upper()
    tendencia = data.get("tendencia", "").upper()
    riesgo    = data.get("riesgo", "").upper()
    entrada   = data.get("entrada", 0.0)
    sl        = data.get("stop_loss", 0.0)
    tp        = data.get("take_profit", 0.0)
    empresa   = data.get("empresa", ticker)

    señal_emoji    = {"COMPRAR": "🟢", "VENDER": "🔴", "MANTENER": "🟡"}
    tendencia_emoji = {"ALCISTA": "📈", "BAJISTA": "📉", "LATERAL": "➡️"}
    riesgo_emoji   = {"BAJO": "🟢", "MEDIO": "🟡", "ALTO": "🔴"}

    s_emoji = señal_emoji.get(señal, "⚪")
    t_emoji = tendencia_emoji.get(tendencia, "")
    r_emoji = riesgo_emoji.get(riesgo, "⚪")

    msg = f"{s_emoji} *{señal}* — {empresa}\n\n"

    if market.get("ok"):
        msg += (
            f"🌐 *Mercado actual ({ticker}):*\n"
            f"  • Precio: `${market['precio_actual']}`\n"
            f"  • Hoy: `{market['cambio_hoy']}`\n"
            f"  • Últimos 5 días: `{market['tendencia_5d']}`\n"
            f"  • Rango 52 sem: `${market['min_52w']} — ${market['max_52w']}`\n\n"
        )

    msg += (
        f"{t_emoji} Tendencia: *{tendencia}*\n"
        f"💰 Precio en gráfico: `${data.get('precio_detectado', 'N/A')}`\n"
        f"{r_emoji} Riesgo: *{riesgo}*\n"
    )

    if señal == "COMPRAR" and entrada:
        msg += (
            f"\n📌 *Niveles:*\n"
            f"  • Entrada: `${entrada}`\n"
            f"  • Take Profit: `${tp}`\n"
            f"  • Stop Loss: `${sl}`\n"
        )

    msg += (
        f"\n📊 *Análisis:*\n{data.get('analisis', 'N/A')}\n\n"
        f"📋 *Qué hacer:*\n{data.get('instruccion', 'N/A')}"
    )

    return msg


async def run_text_analysis_for_ticker(ticker: str, empresa: str) -> str | None:
    """Análisis basado en datos de precio (sin imagen). Usado por el job horario."""
    loop = asyncio.get_event_loop()
    market = await loop.run_in_executor(None, get_market_data, ticker)
    if not market["ok"]:
        return None

    prompt = HOURLY_ANALYSIS_PROMPT.format(
        ticker=ticker,
        empresa=empresa,
        precio_actual=market["precio_actual"],
        cambio_hoy=market["cambio_hoy"],
        tendencia_5d=market["tendencia_5d"],
        min_52w=market["min_52w"],
        max_52w=market["max_52w"],
    )

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=700,
        temperature=0,
    )
    raw = completion.choices[0].message.content.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    data = json.loads(raw)
    msg = build_response_message(data, market)
    return msg


# ---------------------------------------------------------------------------
# Hourly job
# ---------------------------------------------------------------------------

async def hourly_analysis(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    user_id  = job_data["user_id"]
    chat_id  = job_data["chat_id"]
    companies = await db.get_user_companies(user_id)

    if not companies:
        return

    log_request(user_id, "HOURLY_JOB_START", f"n={len(companies)}")
    await context.bot.send_message(chat_id=chat_id, text="🕐 *Análisis horario automático*", parse_mode="Markdown")

    for company in companies:
        ticker  = company["ticker"]
        empresa = company["empresa"]
        try:
            msg = await run_text_analysis_for_ticker(ticker, empresa)
            if msg:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"⚠️ No se pudo obtener datos para *{empresa}* (`{ticker}`).", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"user_id={user_id} | type=HOURLY_ERROR | ticker={ticker} | error={e}", exc_info=True)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    log_request(user_id, "START")
    await update.message.reply_text(
        "🤖 *Bot de Trading activo.*\n\n"
        "Enviame una foto de cualquier gráfico financiero y te digo si comprar, vender o mantener, "
        "con precios exactos de entrada, take profit y stop loss.\n\n"
        "*Comandos disponibles:*\n"
        "• /lista — ver tus empresas guardadas\n"
        "• /agregar TICKER — agregar empresa (ej: `/agregar AAPL`)\n"
        "• /eliminar TICKER — eliminar empresa (ej: `/eliminar AAPL`)\n"
        "• /limpiar — borrar toda la lista\n"
        "• /iniciar — análisis automático cada hora\n"
        "• /detener — detener el análisis automático",
        parse_mode="Markdown"
    )


async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    log_request(user_id, "LISTA")
    companies = await db.get_user_companies(user_id)

    if not companies:
        await update.message.reply_text(
            "Tu lista está vacía.\n"
            "Usá /agregar TICKER para sumar empresas, o enviá un gráfico y te pregunto si querés agregarla."
        )
        return

    msg = "📋 *Tu lista de empresas:*\n\n"
    for i, c in enumerate(companies, 1):
        msg += f"{i}. *{c['empresa']}* (`{c['ticker']}`)\n"
    msg += "\nUsá /eliminar TICKER para quitar una empresa."
    await update.message.reply_text(msg, parse_mode="Markdown")


async def agregar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Usá: `/agregar TICKER`\nEjemplo: `/agregar AAPL`", parse_mode="Markdown")
        return

    ticker = context.args[0].upper()
    log_request(user_id, "AGREGAR", f"ticker={ticker}")

    await update.message.reply_text(f"🔍 Buscando datos para `{ticker}`...", parse_mode="Markdown")

    loop = asyncio.get_event_loop()
    ticker, market = await loop.run_in_executor(None, resolve_ticker, ticker)

    if not market["ok"]:
        await update.message.reply_text(
            f"❌ No encontré datos para `{ticker}`. Verificá que el ticker sea correcto (ej: AAPL, GOOGL, YPFD.BA, BTC-USD).",
            parse_mode="Markdown"
        )
        return

    empresa = await loop.run_in_executor(None, get_company_name, ticker)
    added = await db.add_company(user_id, ticker, empresa)

    if added:
        logger.info(f"user_id={user_id} | type=COMPANY_ADDED | ticker={ticker} | empresa={empresa}")
        await update.message.reply_text(
            f"✅ *{empresa}* (`{ticker}`) agregada a tu lista.\nPrecio actual: `${market['precio_actual']}`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"Ya tenías *{empresa}* (`{ticker}`) en tu lista.",
            parse_mode="Markdown"
        )


async def eliminar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Usá: `/eliminar TICKER`\nEjemplo: `/eliminar AAPL`", parse_mode="Markdown")
        return

    ticker = context.args[0].upper()
    log_request(user_id, "ELIMINAR", f"ticker={ticker}")
    removed = await db.remove_company(user_id, ticker)

    if removed:
        await update.message.reply_text(f"🗑️ `{ticker}` eliminado de tu lista.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"No tenías `{ticker}` en tu lista.", parse_mode="Markdown")


async def limpiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    log_request(user_id, "LIMPIAR")
    count = await db.clear_companies(user_id)

    if count == 0:
        await update.message.reply_text("Tu lista ya está vacía.")
        return

    await update.message.reply_text(f"🗑️ Lista limpiada. Se eliminaron {count} empresa(s).")


async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    log_request(user_id, "INICIAR")
    companies = await db.get_user_companies(user_id)

    if not companies:
        await update.message.reply_text(
            "Tu lista está vacía. Agregá empresas con /agregar TICKER antes de iniciar el análisis automático."
        )
        return

    # Cancelar job anterior si existe
    jobs = context.job_queue.get_jobs_by_name(f"hourly_{user_id}")
    for job in jobs:
        job.schedule_removal()

    context.job_queue.run_repeating(
        hourly_analysis,
        interval=3600,
        first=10,
        name=f"hourly_{user_id}",
        data={"user_id": user_id, "chat_id": update.effective_chat.id},
    )

    nombres = ", ".join(f"*{c['empresa']}*" for c in companies)
    await update.message.reply_text(
        f"✅ *Análisis automático iniciado.*\n\n"
        f"Recibirás un análisis cada hora para {len(companies)} empresa(s):\n{nombres}\n\n"
        f"El primer análisis llega en ~10 segundos.\n"
        f"Usá /detener para cancelarlo.",
        parse_mode="Markdown"
    )


async def detener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    log_request(user_id, "DETENER")

    jobs = context.job_queue.get_jobs_by_name(f"hourly_{user_id}")
    if not jobs:
        await update.message.reply_text("No tenés ningún análisis automático activo.")
        return

    for job in jobs:
        job.schedule_removal()

    await update.message.reply_text("🛑 Análisis automático detenido.")


# ---------------------------------------------------------------------------
# Image analysis
# ---------------------------------------------------------------------------

async def download_image(bot, photo) -> str:
    file = await bot.get_file(photo.file_id)
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.get(file.file_path)
        response.raise_for_status()
        return base64.b64encode(response.content).decode("utf-8")


async def run_analysis(bot, photo, update: Update):
    user_id = update.effective_user.id
    async with gpt_semaphore:
        raw = ""
        try:
            log_request(user_id, "ANALYSIS_START")
            img_b64 = await download_image(bot, photo)

            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": SYSTEM_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                    ]
                }],
                max_tokens=700,
                temperature=0,
            )

            raw = completion.choices[0].message.content.strip()
            logger.info(f"user_id={user_id} | type=GPT_RESPONSE | raw={raw}")

            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            data = json.loads(raw)

            ticker  = data.get("ticker", "")
            señal   = data.get("señal", "").upper()
            empresa = data.get("empresa", ticker)
            riesgo  = data.get("riesgo", "").upper()

            log_request(user_id, "ANALYSIS_RESULT", f"ticker={ticker} señal={señal} riesgo={riesgo}")

            loop = asyncio.get_event_loop()
            market = await loop.run_in_executor(None, get_market_data, ticker) if ticker else {"ok": False}

            msg = build_response_message(data, market)

            # ¿Tiene posición abierta? (solo para VENDER con requiere_posicion)
            if señal == "VENDER" and data.get("requiere_posicion"):
                pending_sell[user_id] = msg
                await update.message.reply_text(
                    msg + "\n\n❓ *¿Tenés posición abierta en este activo?* (respondé Sí o No)",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(msg, parse_mode="Markdown")

                # Preguntar si quiere agregar a la lista (si no está ya)
                if ticker:
                    companies = await db.get_user_companies(user_id)
                    already_in_list = any(c["ticker"] == ticker for c in companies)
                    if not already_in_list:
                        pending_add[user_id] = {"ticker": ticker, "empresa": empresa}
                        await update.message.reply_text(
                            f"➕ ¿Querés agregar *{empresa}* (`{ticker}`) a tu lista de seguimiento? (Sí / No)",
                            parse_mode="Markdown"
                        )

        except json.JSONDecodeError:
            logger.error(f"user_id={user_id} | type=JSON_DECODE_ERROR | raw={raw}")
            await update.message.reply_text(
                "No pude interpretar el gráfico. Asegurate de que la imagen muestre claramente el precio y el nombre del activo."
            )
        except Exception as e:
            logger.error(f"user_id={user_id} | type=ANALYSIS_ERROR | error={e}", exc_info=True)
            await update.message.reply_text(f"Error procesando la imagen ({type(e).__name__}). Intentá de nuevo.")


async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_rate_limited(user_id):
        logger.warning(f"user_id={user_id} | type=RATE_LIMITED")
        await update.message.reply_text(
            f"⏳ Límite alcanzado: máximo {RATE_LIMIT_MAX} análisis por minuto. Esperá unos segundos."
        )
        return

    await update.message.reply_text("📊 Analizando gráfico, un momento...")
    asyncio.create_task(run_analysis(context.bot, update.message.photo[-1], update))


# ---------------------------------------------------------------------------
# Text handler
# ---------------------------------------------------------------------------

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()

    if user_id in pending_sell:
        log_request(user_id, "SELL_CONFIRM", f"respuesta={text}")
        if text in ["sí", "si", "s", "yes", "y"]:
            await update.message.reply_text("✅ Confirmado. Procedé a vender según la instrucción indicada.", parse_mode="Markdown")
        else:
            await update.message.reply_text(
                "📌 Entendido. No tenés posición — la señal es solo informativa.\nEvitá abrir compras nuevas por ahora.",
                parse_mode="Markdown"
            )
        del pending_sell[user_id]

    elif user_id in pending_add:
        log_request(user_id, "ADD_CONFIRM", f"respuesta={text}")
        data = pending_add.pop(user_id)
        if text in ["sí", "si", "s", "yes", "y"]:
            added = await db.add_company(user_id, data["ticker"], data["empresa"])
            if added:
                await update.message.reply_text(
                    f"✅ *{data['empresa']}* agregada a tu lista.\nUsá /iniciar para recibir análisis automáticos.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"Ya tenías *{data['empresa']}* en tu lista.", parse_mode="Markdown")
        else:
            await update.message.reply_text("Ok, no se agregó.")

    else:
        log_request(user_id, "TEXT_NO_CONTEXT")
        await update.message.reply_text("Enviame una captura del gráfico para analizarla.")


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"type=GLOBAL_ERROR | error={context.error}", exc_info=context.error)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _on_startup(app: Application) -> None:
    await db.init_db()


async def _on_shutdown(app: Application) -> None:
    await db.close_db()


def main():
    asyncio.set_event_loop(asyncio.new_event_loop())

    webhook_url = os.getenv("WEBHOOK_URL")
    port = int(os.getenv("PORT", 8443))

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(_on_startup)
        .post_stop(_on_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("lista",    lista))
    app.add_handler(CommandHandler("agregar",  agregar))
    app.add_handler(CommandHandler("eliminar", eliminar))
    app.add_handler(CommandHandler("limpiar",  limpiar))
    app.add_handler(CommandHandler("iniciar",  iniciar))
    app.add_handler(CommandHandler("detener",  detener))
    app.add_handler(MessageHandler(filters.PHOTO, analyze_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    if webhook_url:
        logger.info(f"type=BOT_START | mode=webhook | url={webhook_url} | port={port}")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=TELEGRAM_TOKEN,
            webhook_url=f"{webhook_url}/{TELEGRAM_TOKEN}",
        )
    else:
        logger.info("type=BOT_START | mode=polling")
        app.run_polling()


if __name__ == "__main__":
    main()
