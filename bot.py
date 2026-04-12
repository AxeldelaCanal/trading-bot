import os
import json
import logging
import base64
import asyncio
import httpx
import yfinance as yf
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

pending_sell = {}
gpt_semaphore = asyncio.Semaphore(1)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Sos un Senior Quant Trader. Analizá la imagen del gráfico financiero e identificá la empresa y su señal de trading.

IMPORTANTE: Aceptás cualquier imagen que contenga un gráfico financiero o información de precio de una acción, CEDEAR, índice o criptomoneda. No importa de qué plataforma venga.

Qué extraer de la imagen:
1. Nombre de la empresa o activo visible en el gráfico.
2. Ticker/símbolo (ej: GOOGL, AAPL, MSFT, MELI). Si es un CEDEAR argentino, devolvé el ticker en formato de Yahoo Finance (ej: GOOGL para Google).
3. Precio actual visible en el gráfico.
4. Tendencia: ALCISTA, BAJISTA o LATERAL según velas y medias móviles visibles.
5. RSI si está visible.
6. Soportes y resistencias clave.

Cómo decidir la señal:
- COMPRAR: tendencia alcista, RSI no sobrecomprado (<70), precio en soporte o sobre EMAs.
- VENDER: tendencia bajista, RSI sobrecomprado (>70) o precio rompiendo soporte importante.
- MANTENER: señales mixtas o mercado sin dirección clara.

Formato de instrucción (MUY IMPORTANTE — usá precios concretos leídos del gráfico):
- COMPRAR: "Colocá una orden de compra límite a $[entrada]. Si sube a $[take_profit], cerrá con ganancia. Si cae a $[stop_loss], cerrá para limitar pérdidas."
- VENDER: "Vendé a $[precio] o a mercado. [Motivo técnico concreto con el nivel que rompió]."
- MANTENER: "No operes aún. Esperá que llegue a $[nivel_entrada] para comprar, o que caiga a $[nivel_alerta] para evaluar salida."

Output JSON estricto:
{
  "ticker": "SÍMBOLO_YAHOO_FINANCE",
  "empresa": "Nombre completo de la empresa",
  "señal": "COMPRAR/VENDER/MANTENER",
  "tendencia": "ALCISTA/BAJISTA/LATERAL",
  "precio_detectado": 0.0,
  "entrada": 0.0,
  "stop_loss": 0.0,
  "take_profit": 0.0,
  "riesgo": "BAJO/MEDIO/ALTO",
  "analisis": "Máximo 2 líneas con el motivo técnico",
  "instruccion": "Instrucción completa con precios concretos",
  "requiere_posicion": true/false
}

"requiere_posicion" es true SOLO si la señal es VENDER.
Respondé SOLO con el JSON. Sin texto extra. Sin bloques de código."""


def get_market_data(ticker: str) -> dict:
    """Obtiene datos en tiempo real de Yahoo Finance."""
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

        # Tendencia reciente: últimos 5 días
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
        logger.warning(f"No se pudo obtener datos de mercado para {ticker}: {e}")
        return {"ok": False}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot de Trading activo.\n\n"
        "Enviame una foto de cualquier gráfico financiero y te digo si comprar, vender o mantener, "
        "con precios exactos de entrada, take profit y stop loss."
    )


async def download_image(bot, photo) -> str:
    file = await bot.get_file(photo.file_id)
    async with httpx.AsyncClient(timeout=30) as http:
        response = await http.get(file.file_path)
        response.raise_for_status()
        return base64.b64encode(response.content).decode("utf-8")


async def run_analysis(bot, photo, update: Update):
    async with gpt_semaphore:
        raw = ""
        try:
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
                max_tokens=700
            )

            raw = completion.choices[0].message.content.strip()
            logger.info(f"GPT raw: {raw}")

            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            data = json.loads(raw)

            ticker   = data.get("ticker", "")
            señal    = data.get("señal", "").upper()
            tendencia = data.get("tendencia", "").upper()
            riesgo   = data.get("riesgo", "").upper()
            entrada  = data.get("entrada", 0.0)
            sl       = data.get("stop_loss", 0.0)
            tp       = data.get("take_profit", 0.0)
            empresa  = data.get("empresa", ticker)

            señal_emoji    = {"COMPRAR": "🟢", "VENDER": "🔴", "MANTENER": "🟡"}
            tendencia_emoji = {"ALCISTA": "📈", "BAJISTA": "📉", "LATERAL": "➡️"}
            riesgo_emoji   = {"BAJO": "🟢", "MEDIO": "🟡", "ALTO": "🔴"}

            s_emoji = señal_emoji.get(señal, "⚪")
            t_emoji = tendencia_emoji.get(tendencia, "")
            r_emoji = riesgo_emoji.get(riesgo, "⚪")

            # Datos de mercado en tiempo real (en thread para no bloquear el loop)
            loop = asyncio.get_event_loop()
            market = await loop.run_in_executor(None, get_market_data, ticker) if ticker else {"ok": False}

            msg = f"{s_emoji} *{señal}* — {empresa}\n\n"

            # Datos de mercado reales
            if market["ok"]:
                msg += (
                    f"🌐 *Mercado actual ({ticker}):*\n"
                    f"  • Precio: `${market['precio_actual']}`\n"
                    f"  • Hoy: `{market['cambio_hoy']}`\n"
                    f"  • Últimos 5 días: `{market['tendencia_5d']}`\n"
                    f"  • Rango 52 sem: `${market['min_52w']} — ${market['max_52w']}`\n\n"
                )

            msg += (
                f"{t_emoji} Tendencia en gráfico: *{tendencia}*\n"
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

            if señal == "VENDER" and data.get("requiere_posicion"):
                pending_sell[update.effective_user.id] = msg
                await update.message.reply_text(
                    msg + "\n\n❓ *¿Tenés posición abierta en este activo?* (respondé Sí o No)",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(msg, parse_mode="Markdown")

        except json.JSONDecodeError:
            logger.error(f"JSONDecodeError. Raw: {raw}")
            await update.message.reply_text(
                "No pude interpretar el gráfico. Asegurate de que la imagen muestre claramente el precio y el nombre del activo."
            )
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            await update.message.reply_text(f"Error procesando la imagen ({type(e).__name__}). Intentá de nuevo.")


async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Analizando gráfico, un momento...")
    asyncio.create_task(run_analysis(context.bot, update.message.photo[-1], update))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()

    if user_id in pending_sell:
        if text in ["sí", "si", "s", "yes", "y"]:
            await update.message.reply_text(
                "✅ Confirmado. Procedé a vender según la instrucción indicada.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "📌 Entendido. No tenés posición — la señal es solo informativa.\n"
                "Evitá abrir compras nuevas por ahora.",
                parse_mode="Markdown"
            )
        del pending_sell[user_id]
    else:
        await update.message.reply_text(
            "Enviame una captura del gráfico para analizarla."
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error global: {context.error}", exc_info=context.error)


def main():
    asyncio.set_event_loop(asyncio.new_event_loop())
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, analyze_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)
    logger.info("Bot iniciado...")
    app.run_polling()


if __name__ == "__main__":
    main()
