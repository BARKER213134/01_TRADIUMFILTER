#!/usr/bin/env python3
"""
Tradium Signal Monitor
Reads trade setups from Tradium [WORKSPACE] topic 3204
Analyzes text + chart images with GPT-5.2 vision
"""

import asyncio
import os
import re
import json
import logging
import base64
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telegram import Bot

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Config
API_ID = int(os.environ.get('TELEGRAM_API_ID', 0))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '')
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
SESSION_FILE = ROOT_DIR / 'telethon_session'
TRADIUM_CHANNEL_ID = -1002423680272
TRADIUM_TOPIC_ID = 3204

# MongoDB
mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[db_name]

# Telegram Bot for sending results
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

# Temporary storage for photos (msg_id -> photo_msg)
pending_photos = {}


def parse_tradium_signal(text: str) -> dict | None:
    """Parse Tradium Setup Screener signal format"""
    if '#сетап' not in text:
        return None

    # Symbol: $BNB or $1000BONK etc
    symbol_match = re.search(r'\$([A-Z0-9]+)', text)
    if not symbol_match:
        return None
    symbol = symbol_match.group(1)
    if not symbol.endswith('USDT'):
        symbol = symbol + 'USDT'

    # Timeframe: 4h, 1h, etc
    tf_match = re.search(r'\$[A-Z0-9]+\s+(\d+[hHdDmM])', text)
    timeframe = tf_match.group(1) if tf_match else '4h'

    # Direction: Short 📉 or Long 📈
    direction = None
    if re.search(r'Short\s*📉', text):
        direction = 'SELL'
    elif re.search(r'Long\s*📈', text):
        direction = 'BUY'
    if not direction:
        return None

    # Entry price
    entry_match = re.search(r'Entry:\s*([\d.]+)', text)
    if not entry_match:
        return None
    entry_price = float(entry_match.group(1))

    # Take Profit
    tp_match = re.search(r'TP:\s*([\d.]+)', text)
    if not tp_match:
        return None
    take_profit = float(tp_match.group(1))

    # Stop Loss
    sl_match = re.search(r'SL:\s*([\d.]+)', text)
    if not sl_match:
        return None
    stop_loss = float(sl_match.group(1))

    # Risk-Reward
    rr_match = re.search(r'Risk-reward:\s*([\d.]+)', text)
    rr_ratio = float(rr_match.group(1)) if rr_match else 0

    # Risk %
    risk_match = re.search(r'Risk:\s*([\d.]+)%', text)
    risk_pct = float(risk_match.group(1)) if risk_match else 0

    # Amount
    amount_match = re.search(r'Amount:\s*([\d.]+)', text)
    amount = float(amount_match.group(1)) if amount_match else 0

    # Trend indicators
    trend_match = re.search(r'TREND\s+((?:[🟢🔴🟠⚪]+\s*)+)', text)
    trend_raw = trend_match.group(1).strip() if trend_match else ''
    green = trend_raw.count('🟢')
    red = trend_raw.count('🔴')
    orange = trend_raw.count('🟠')

    # MA and RSI
    ma_match = re.search(r'MA\s+(🟢|🔴|🟠)', text)
    rsi_match = re.search(r'RSI\s+(🟢|🔴|🟠)', text)
    ma_status = ma_match.group(1) if ma_match else ''
    rsi_status = rsi_match.group(1) if rsi_match else ''

    # Volume
    vol_match = re.search(r'Volume\s+\w+\s+([\d.]+)\s*M', text)
    volume = float(vol_match.group(1)) if vol_match else 0

    # Key levels from comment
    key_levels = {}
    res_match = re.search(r'RESISTANCE\s+([\d.]+)\s*-\s*([\d.]+)', text)
    sup_match = re.search(r'SUPPORT\s+([\d.]+)\s*-\s*([\d.]+)', text)
    if res_match:
        key_levels['resistance'] = [float(res_match.group(1)), float(res_match.group(2))]
    if sup_match:
        key_levels['support'] = [float(sup_match.group(1)), float(sup_match.group(2))]

    # Current price from comment
    current_match = re.search(r'Current:\s*([\d.]+)', text)
    current_price = float(current_match.group(1)) if current_match else 0

    # Comment
    comment_match = re.search(r'Comment:\s*(.+?)(?:\n|$)', text)
    comment = comment_match.group(1).strip() if comment_match else ''

    # Author/screener number
    author_match = re.search(r'Setup Screener\s*🏆№(\d+)', text)
    screener_num = int(author_match.group(1)) if author_match else 0

    return {
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "rr_ratio": rr_ratio,
        "risk_pct": risk_pct,
        "amount": amount,
        "timeframe": timeframe,
        "trend": {"green": green, "red": red, "orange": orange, "raw": trend_raw},
        "ma_status": ma_status,
        "rsi_status": rsi_status,
        "volume_1d": volume,
        "key_levels": key_levels,
        "current_price": current_price,
        "comment": comment,
        "screener_num": screener_num,
        "source": "tradium"
    }


async def analyze_with_ai(signal: dict, chart_path: str = None) -> dict:
    """Analyze signal with GPT-5.2 vision (text + chart image)"""
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    if not api_key:
        return {"decision": "SKIP", "reasoning": "API ключ не настроен", "confidence": 0}

    chat = LlmChat(
        api_key=api_key,
        session_id=f"tradium-{signal['symbol']}-{datetime.now().timestamp()}",
        system_message="""Ты — лучший криптотрейдер мира с 15-летним опытом. Анализируй торговые сетапы комплексно.

Если прикреплён график — внимательно изучи его: уровни, тренд, свечные паттерны, объёмы, индикаторы.

Отвечай на русском в формате JSON:
{
    "decision": "ACCEPT" или "REJECT",
    "confidence": 0-100,
    "summary": "Краткий вердикт 1-2 предложения",
    "technical_analysis": "Анализ графика и индикаторов 2-3 предложения",
    "chart_analysis": "Что видно на графике (если прикреплён) 1-2 предложения",
    "risk_assessment": "Оценка рисков 1-2 предложения",
    "recommendation": "Финальная рекомендация"
}"""
    ).with_model("openai", "gpt-5.2")

    dir_text = "ШОРТ (SHORT)" if signal['direction'] == 'SELL' else "ЛОНГ (LONG)"
    trend_desc = f"🟢x{signal['trend']['green']} 🔴x{signal['trend']['red']} 🟠x{signal['trend']['orange']}"

    prompt = f"""=== ТОРГОВЫЙ СЕТАП ===
Монета: {signal['symbol']}
Направление: {dir_text}
Таймфрейм: {signal['timeframe']}
Вход: {signal['entry_price']}
Take Profit: {signal['take_profit']}
Stop Loss: {signal['stop_loss']}
Risk-Reward: {signal['rr_ratio']}
Риск: {signal['risk_pct']}%
Объём: {signal['amount']}$

=== ИНДИКАТОРЫ ===
TREND: {trend_desc}
MA: {signal['ma_status']} | RSI: {signal['rsi_status']}
Volume 1D: {signal['volume_1d']}M
Текущая цена: {signal['current_price']}

=== УРОВНИ ===
{json.dumps(signal['key_levels'], indent=2) if signal['key_levels'] else 'Не указаны'}

=== КОММЕНТАРИЙ ===
{signal['comment']}

{"На графике прикреплён торговый чарт — проанализируй его внимательно." if chart_path else "График не прикреплён."}

Проанализируй этот сетап и дай рекомендацию. JSON:"""

    try:
        file_contents = []
        if chart_path and os.path.exists(chart_path):
            with open(chart_path, 'rb') as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')
            file_contents.append(ImageContent(image_base64=img_b64))
            logger.info(f"📸 Отправляю график на AI анализ: {chart_path}")

        msg = UserMessage(text=prompt, file_contents=file_contents if file_contents else None)
        response = await chat.send_message(msg)

        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        logger.error(f"AI analysis error: {e}")

    return {"decision": "SKIP", "reasoning": "Ошибка анализа", "confidence": 0}


def format_analysis_message(signal: dict, analysis: dict) -> str:
    """Format analysis result for Telegram"""
    import html

    decision = analysis.get('decision', 'SKIP')
    confidence = analysis.get('confidence', 0)

    if decision == 'ACCEPT':
        emoji, status = "✅", "ПРИНЯТ"
    elif decision == 'REJECT':
        emoji, status = "❌", "ОТКЛОНЁН"
    else:
        emoji, status = "⏸️", "ПРОПУЩЕН"

    dir_emoji = "🟢 LONG" if signal['direction'] == 'BUY' else "🔴 SHORT"
    trend_desc = f"🟢x{signal['trend']['green']} 🔴x{signal['trend']['red']}"

    summary = html.escape(str(analysis.get('summary', 'N/A')))
    tech = html.escape(str(analysis.get('technical_analysis', 'N/A')))
    chart = html.escape(str(analysis.get('chart_analysis', '')))
    risk = html.escape(str(analysis.get('risk_assessment', 'N/A')))
    rec = html.escape(str(analysis.get('recommendation', 'N/A')))

    msg = f"""{emoji} <b>{status} | {confidence}%</b>

{dir_emoji} <b>{signal['symbol']}</b> ({signal['timeframe']})

💰 <b>Сделка:</b>
├ Вход: <code>{signal['entry_price']}</code>
├ TP: <code>{signal['take_profit']}</code>
├ SL: <code>{signal['stop_loss']}</code>
└ R:R: <code>{signal['rr_ratio']}</code>

📊 <b>Индикаторы:</b>
├ Тренд: {trend_desc}
├ MA: {signal['ma_status']} | RSI: {signal['rsi_status']}
└ Volume: <code>{signal['volume_1d']}M</code>

📝 <b>Вердикт:</b>
{summary}

📈 <b>Технический анализ:</b>
{tech}"""

    if chart:
        msg += f"\n\n📸 <b>Анализ графика:</b>\n{chart}"

    msg += f"""

⚠️ <b>Риски:</b>
{risk}

🎯 <b>Рекомендация:</b>
{rec}"""

    return msg.strip()


async def send_to_users(text: str, photo_path: str = None):
    """Send analysis to all registered bot users"""
    if not bot:
        return

    users = await db.bot_users.find({}, {"_id": 0, "chat_id": 1}).to_list(100)

    for user in users:
        try:
            if photo_path and os.path.exists(photo_path):
                with open(photo_path, 'rb') as photo:
                    await bot.send_photo(
                        chat_id=user['chat_id'],
                        photo=photo,
                        caption=text[:1024],
                        parse_mode='HTML'
                    )
            else:
                await bot.send_message(
                    chat_id=user['chat_id'],
                    text=text,
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Send error to {user['chat_id']}: {e}")


async def process_signal(text: str, chart_path: str = None):
    """Process incoming Tradium signal"""
    signal = parse_tradium_signal(text)
    if not signal:
        logger.debug(f"Not a setup message, skipping")
        return

    logger.info(f"📊 New Tradium signal: {signal['direction']} {signal['symbol']} ({signal['timeframe']})")

    # AI analysis with chart
    analysis = await analyze_with_ai(signal, chart_path)

    # Save to database
    doc = {
        "id": f"tradium-{datetime.now().timestamp()}",
        "original_text": text[:1000],
        "symbol": signal['symbol'],
        "direction": signal['direction'],
        "entry_price": signal['entry_price'],
        "take_profit": signal['take_profit'],
        "stop_loss": signal['stop_loss'],
        "rr_ratio": signal['rr_ratio'],
        "risk_pct": signal['risk_pct'],
        "timeframe": signal['timeframe'],
        "trend": signal['trend'],
        "ma_status": signal['ma_status'],
        "rsi_status": signal['rsi_status'],
        "volume_1d": signal['volume_1d'],
        "key_levels": signal['key_levels'],
        "current_price": signal['current_price'],
        "status": "accepted" if analysis.get('decision') == 'ACCEPT' else "rejected",
        "ai_analysis": analysis,
        "has_chart": chart_path is not None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "tradium"
    }
    await db.signals.insert_one(doc)

    # Format and send
    result_text = format_analysis_message(signal, analysis)
    await send_to_users(result_text, chart_path)

    logger.info(f"{'✅' if analysis.get('decision') == 'ACCEPT' else '❌'} {signal['symbol']}: {analysis.get('decision')} ({analysis.get('confidence', 0)}%)")


async def main():
    logger.info("🚀 Starting Tradium Signal Monitor...")

    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    logger.info(f"✅ Logged in as: {me.first_name} (@{me.username})")

    # Get channel entity
    try:
        entity = await client.get_entity(TRADIUM_CHANNEL_ID)
        logger.info(f"✅ Connected to: {entity.title}")
    except Exception as e:
        logger.error(f"❌ Cannot access Tradium channel: {e}")
        return

    # Handler for new messages in topic 3204
    @client.on(events.NewMessage(chats=TRADIUM_CHANNEL_ID))
    async def handler(event):
        msg = event.message

        # Check if message is in our topic
        reply_to = getattr(msg, 'reply_to', None)
        if not reply_to:
            return

        topic_id = getattr(reply_to, 'reply_to_top_id', None) or getattr(reply_to, 'reply_to_msg_id', None)
        if topic_id != TRADIUM_TOPIC_ID:
            return

        # Photo message → store for pairing
        if msg.photo and not msg.text:
            pending_photos[msg.id] = msg
            logger.info(f"📸 Photo received (msg_id={msg.id}), waiting for text...")
            return

        # Text message with setup
        text = msg.text or ""
        if '#сетап' not in text:
            return

        logger.info(f"📨 Setup signal received (msg_id={msg.id})")

        # Try to find the paired photo (previous message)
        chart_path = None
        photo_msg_id = msg.id + 1  # Photo is always ID+1 (sent before text)

        if photo_msg_id in pending_photos:
            photo_msg = pending_photos.pop(photo_msg_id)
            try:
                chart_path = await client.download_media(
                    photo_msg,
                    file=tempfile.mktemp(suffix='.jpg', dir='/tmp')
                )
                logger.info(f"📥 Chart downloaded: {chart_path}")
            except Exception as e:
                logger.error(f"Failed to download chart: {e}")
        else:
            # Try to fetch the photo directly
            try:
                photo_msg = await client.get_messages(entity, ids=photo_msg_id)
                if photo_msg and photo_msg.photo:
                    chart_path = await client.download_media(
                        photo_msg,
                        file=tempfile.mktemp(suffix='.jpg', dir='/tmp')
                    )
                    logger.info(f"📥 Chart fetched and downloaded: {chart_path}")
            except Exception as e:
                logger.error(f"Could not fetch photo msg {photo_msg_id}: {e}")

        # Process the signal
        await process_signal(text, chart_path)

        # Cleanup temp file
        if chart_path and os.path.exists(chart_path):
            try:
                os.unlink(chart_path)
            except:
                pass

    logger.info(f"👀 Monitoring Tradium topic {TRADIUM_TOPIC_ID} for signals...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
