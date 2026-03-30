#!/usr/bin/env python3
"""
Tradium Signal Monitor v2
Reads trade setups from Tradium [WORKSPACE] topic 3204
AI extracts DCA #4 level from chart images
Saves silently — no notifications
"""

import asyncio
import os
import re
import json
import logging
import base64
import shutil
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Config
API_ID = int(os.environ.get('TELEGRAM_API_ID', 0))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '')
SESSION_FILE = ROOT_DIR / 'telethon_session'
TRADIUM_CHANNEL_ID = int(os.environ.get('TRADIUM_CHANNEL_ID', '-1002423680272'))
TRADIUM_TOPIC_ID = int(os.environ.get('TRADIUM_TOPIC_ID', '3204'))
CHARTS_DIR = ROOT_DIR / 'charts'
CHARTS_DIR.mkdir(exist_ok=True)

# MongoDB
mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[db_name]


def parse_tradium_signal(text: str) -> dict | None:
    """Parse Tradium Setup Screener signal format"""
    if '#сетап' not in text:
        return None

    symbol_match = re.search(r'\$([A-Z0-9]+)', text)
    if not symbol_match:
        return None
    symbol = symbol_match.group(1)
    if not symbol.endswith('USDT'):
        symbol = symbol + 'USDT'

    tf_match = re.search(r'\$[A-Z0-9]+\s+(\d+[hHdDmM])', text)
    timeframe = tf_match.group(1) if tf_match else '4h'

    direction = None
    if re.search(r'Short\s*📉', text):
        direction = 'SHORT'
    elif re.search(r'Long\s*📈', text):
        direction = 'LONG'
    if not direction:
        return None

    entry_match = re.search(r'Entry:\s*([\d.]+)', text)
    if not entry_match:
        return None
    entry_price = float(entry_match.group(1))

    tp_match = re.search(r'TP:\s*([\d.]+)', text)
    take_profit = float(tp_match.group(1)) if tp_match else 0

    sl_match = re.search(r'SL:\s*([\d.]+)', text)
    stop_loss = float(sl_match.group(1)) if sl_match else 0

    rr_match = re.search(r'Risk-reward:\s*([\d.]+)', text)
    rr_ratio = float(rr_match.group(1)) if rr_match else 0

    risk_match = re.search(r'Risk:\s*([\d.]+)%', text)
    risk_pct = float(risk_match.group(1)) if risk_match else 0

    amount_match = re.search(r'Amount:\s*([\d.]+)', text)
    amount = float(amount_match.group(1)) if amount_match else 0

    trend_match = re.search(r'TREND\s+((?:[🟢🔴🟠⚪]+\s*)+)', text)
    trend_raw = trend_match.group(1).strip() if trend_match else ''

    ma_match = re.search(r'MA\s+(🟢|🔴|🟠)', text)
    rsi_match = re.search(r'RSI\s+(🟢|🔴|🟠)', text)
    ma_status = ma_match.group(1) if ma_match else ''
    rsi_status = rsi_match.group(1) if rsi_match else ''

    vol_match = re.search(r'Volume\s+\w+\s+([\d.]+)\s*M', text)
    volume = float(vol_match.group(1)) if vol_match else 0

    tp_pct_match = re.search(r'TP:\s*[\d.]+\s+([\d.]+)%', text)
    tp_pct = float(tp_pct_match.group(1)) if tp_pct_match else 0

    sl_pct_match = re.search(r'SL:\s*[\d.]+\s+([\d.]+)%', text)
    sl_pct = float(sl_pct_match.group(1)) if sl_pct_match else 0

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
        "trend": trend_raw,
        "ma_status": ma_status,
        "rsi_status": rsi_status,
        "volume_1d": volume,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
    }


async def extract_dca4_from_chart(chart_path: str, signal: dict) -> dict | None:
    """Use GPT-5.2 Vision to extract DCA #4 level from chart"""
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    if not api_key:
        return None

    with open(chart_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')

    direction = signal['direction']
    if direction == 'SHORT':
        context = "Это ШОРТ сетап. DCA уровни идут ВВЕРХ к зоне RESISTANCE. DCA #4 находится возле сопротивления."
    else:
        context = "Это ЛОНГ сетап. DCA уровни идут ВНИЗ к зоне SUPPORT. DCA #4 находится возле поддержки."

    chat = LlmChat(
        api_key=api_key,
        session_id=f"dca-extract-{signal['symbol']}-{datetime.now().timestamp()}",
        system_message="Ты трейдер-аналитик. Извлекай данные с графиков точно. Отвечай ТОЛЬКО JSON."
    ).with_model("openai", "gpt-5.2")

    msg = UserMessage(
        text=f"""{context}

Монета: {signal['symbol']} | {signal['direction']} | {signal['timeframe']}

Найди на графике ВСЕ DCA уровни и зону поддержки/сопротивления.
Отвечай СТРОГО JSON:
{{
    "dca1": число,
    "dca2": число,
    "dca3": число,
    "dca4": число,
    "dca5": число,
    "zone_type": "RESISTANCE" или "SUPPORT",
    "zone_low": число,
    "zone_high": число,
    "current_price": число
}}""",
        file_contents=[ImageContent(image_base64=img_b64)]
    )

    try:
        response = await chat.send_message(msg)
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            if data.get('dca4'):
                logger.info(f"📊 {signal['symbol']}: DCA#4 = {data['dca4']} ({data.get('zone_type', 'N/A')} {data.get('zone_low', '')}-{data.get('zone_high', '')})")
                return data
    except Exception as e:
        logger.error(f"DCA extraction error: {e}")

    return None


async def process_signal(text: str, chart_path: str = None, client=None, entity=None):
    """Process incoming Tradium signal — parse, extract DCA#4, save silently"""
    signal = parse_tradium_signal(text)
    if not signal:
        return

    logger.info(f"📨 New signal: {signal['direction']} {signal['symbol']} ({signal['timeframe']})")

    # Extract DCA #4 from chart
    dca_data = None
    saved_chart = None

    if chart_path and os.path.exists(chart_path):
        dca_data = await extract_dca4_from_chart(chart_path, signal)

        # Save chart permanently
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        chart_filename = f"{signal['symbol']}_{signal['direction']}_{timestamp}.jpg"
        saved_chart = str(CHARTS_DIR / chart_filename)
        shutil.copy2(chart_path, saved_chart)

    # Build database document
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
        "amount": signal['amount'],
        "timeframe": signal['timeframe'],
        "trend": signal['trend'],
        "ma_status": signal['ma_status'],
        "rsi_status": signal['rsi_status'],
        "volume_1d": signal['volume_1d'],
        "tp_pct": signal['tp_pct'],
        "sl_pct": signal['sl_pct'],
        "dca_data": dca_data,
        "dca4_level": dca_data.get('dca4') if dca_data else None,
        "chart_path": saved_chart,
        "status": "watching",
        "entry_triggered": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "tradium"
    }
    await db.signals.insert_one(doc)

    if dca_data and dca_data.get('dca4'):
        logger.info(f"✅ Saved {signal['symbol']} {signal['direction']} | DCA#4: {dca_data['dca4']} | Chart: {saved_chart}")
    else:
        logger.warning(f"⚠️ Saved {signal['symbol']} without DCA#4 (no chart or AI failed)")


async def main():
    logger.info("🚀 Starting Tradium Signal Monitor v2...")

    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    logger.info(f"✅ Logged in as: {me.first_name} (@{me.username})")

    try:
        entity = await client.get_entity(TRADIUM_CHANNEL_ID)
        logger.info(f"✅ Connected to: {entity.title}")
    except Exception as e:
        logger.error(f"❌ Cannot access Tradium channel: {e}")
        return

    # Storage for pairing photos with text
    pending_photos = {}

    @client.on(events.NewMessage(chats=TRADIUM_CHANNEL_ID))
    async def handler(event):
        msg = event.message

        reply_to = getattr(msg, 'reply_to', None)
        if not reply_to:
            return

        topic_id = getattr(reply_to, 'reply_to_top_id', None) or getattr(reply_to, 'reply_to_msg_id', None)
        if topic_id != TRADIUM_TOPIC_ID:
            return

        # Photo → store
        if msg.photo and not msg.text:
            pending_photos[msg.id] = msg
            return

        text = msg.text or ""
        if '#сетап' not in text:
            return

        # Find paired chart photo
        chart_path = None
        photo_msg_id = msg.id + 1

        if photo_msg_id in pending_photos:
            photo_msg = pending_photos.pop(photo_msg_id)
            try:
                import tempfile
                chart_path = await client.download_media(
                    photo_msg, file=tempfile.mktemp(suffix='.jpg', dir='/tmp')
                )
            except Exception as e:
                logger.error(f"Photo download error: {e}")
        else:
            try:
                photo_msg = await client.get_messages(entity, ids=photo_msg_id)
                if photo_msg and photo_msg.photo:
                    import tempfile
                    chart_path = await client.download_media(
                        photo_msg, file=tempfile.mktemp(suffix='.jpg', dir='/tmp')
                    )
            except:
                pass

        await process_signal(text, chart_path)

        # Cleanup temp
        if chart_path and os.path.exists(chart_path) and '/tmp/' in chart_path:
            try:
                os.unlink(chart_path)
            except:
                pass

    logger.info(f"👀 Monitoring Tradium topic {TRADIUM_TOPIC_ID}...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
