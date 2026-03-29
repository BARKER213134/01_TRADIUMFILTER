#!/usr/bin/env python3
"""
Backfill script: Read last 100 messages from Tradium topic 3204,
parse signals, extract DCA#4 from charts via AI, and add to DB for monitoring.
Skip duplicates. Only add signals that are still relevant (price hasn't passed TP/SL).
"""

import asyncio
import os
import re
import json
import base64
import shutil
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from motor.motor_asyncio import AsyncIOMotorClient
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
import ccxt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_ID = int(os.environ.get('TELEGRAM_API_ID', 0))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '')
SESSION_FILE = ROOT_DIR / 'backfill_session'
TRADIUM_CHANNEL_ID = int(os.environ.get('TRADIUM_CHANNEL_ID', '-1002423680272'))
TRADIUM_TOPIC_ID = int(os.environ.get('TRADIUM_TOPIC_ID', '3204'))
CHARTS_DIR = ROOT_DIR / 'charts'
CHARTS_DIR.mkdir(exist_ok=True)

mongo_client = AsyncIOMotorClient(os.environ.get('MONGO_URL'))
db = mongo_client[os.environ.get('DB_NAME')]

exchange = ccxt.kraken({'enableRateLimit': True})


def parse_tradium_signal(text: str) -> dict | None:
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
        "symbol": symbol, "direction": direction, "entry_price": entry_price,
        "take_profit": take_profit, "stop_loss": stop_loss, "rr_ratio": rr_ratio,
        "risk_pct": risk_pct, "amount": amount, "timeframe": timeframe,
        "trend": trend_raw, "ma_status": ma_status, "rsi_status": rsi_status,
        "volume_1d": volume, "tp_pct": tp_pct, "sl_pct": sl_pct,
    }


async def get_price(symbol: str) -> float:
    base = symbol.replace("USDT", "").replace("PERP", "").upper()
    for sym in [f"{base}/USD", f"{base}/USDT"]:
        try:
            ticker = exchange.fetch_ticker(sym)
            if ticker and ticker.get('last'):
                return float(ticker['last'])
        except Exception:
            continue
    try:
        okx = ccxt.okx({'enableRateLimit': True})
        ticker = okx.fetch_ticker(f"{base}/USDT")
        if ticker and ticker.get('last'):
            return float(ticker['last'])
    except Exception:
        pass
    return 0


async def extract_dca4(chart_path: str, signal: dict) -> dict | None:
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    if not api_key:
        return None

    with open(chart_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')

    direction = signal['direction']
    if direction == 'SHORT':
        context = "Это ШОРТ сетап. DCA уровни идут ВВЕРХ к зоне RESISTANCE."
    else:
        context = "Это ЛОНГ сетап. DCA уровни идут ВНИЗ к зоне SUPPORT."

    chat = LlmChat(
        api_key=api_key,
        session_id=f"backfill-{signal['symbol']}-{datetime.now().timestamp()}",
        system_message="Ты трейдер-аналитик. Извлекай данные с графиков точно. Отвечай ТОЛЬКО JSON."
    ).with_model("openai", "gpt-5.2")

    msg = UserMessage(
        text=f"""{context}
Монета: {signal['symbol']} | {signal['direction']} | {signal['timeframe']}
Найди на графике ВСЕ DCA уровни и зону.
Отвечай СТРОГО JSON:
{{"dca1": число, "dca2": число, "dca3": число, "dca4": число, "dca5": число, "zone_type": "RESISTANCE" или "SUPPORT", "zone_low": число, "zone_high": число}}""",
        file_contents=[ImageContent(image_base64=img_b64)]
    )

    try:
        response = await chat.send_message(msg)
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            if data.get('dca4'):
                return data
    except Exception as e:
        logger.error(f"DCA extraction error for {signal['symbol']}: {e}")
    return None


async def is_signal_still_valid(signal: dict, current_price: float) -> bool:
    """Check if signal hasn't already hit TP or SL"""
    tp = signal.get('take_profit', 0)
    sl = signal.get('stop_loss', 0)
    direction = signal['direction']

    if current_price <= 0:
        return True

    if direction == 'SHORT':
        if tp > 0 and current_price <= tp:
            return False
        if sl > 0 and current_price >= sl:
            return False
    elif direction == 'LONG':
        if tp > 0 and current_price >= tp:
            return False
        if sl > 0 and current_price <= sl:
            return False

    return True


async def main():
    logger.info("🔍 Backfill: Reading last 100 messages from Tradium...")

    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    logger.info(f"✅ Logged in as: {me.first_name}")

    entity = await client.get_entity(TRADIUM_CHANNEL_ID)
    logger.info(f"✅ Channel: {entity.title}")

    messages = await client.get_messages(entity, limit=100, reply_to=TRADIUM_TOPIC_ID)
    logger.info(f"📨 Got {len(messages)} messages from topic {TRADIUM_TOPIC_ID}")

    # Group: find text messages with #сетап and their paired photos
    signal_msgs = []
    photo_by_id = {}

    for msg in messages:
        if msg.photo and not msg.text:
            photo_by_id[msg.id] = msg

    for msg in messages:
        text = msg.text or ""
        if '#сетап' not in text:
            continue

        parsed = parse_tradium_signal(text)
        if not parsed:
            continue

        # Find paired photo (usually msg.id - 1 or msg.id + 1)
        photo_msg = None
        for offset in [-1, 1, -2, 2]:
            if (msg.id + offset) in photo_by_id:
                photo_msg = photo_by_id[msg.id + offset]
                break

        if not photo_msg:
            try:
                for offset in [-1, 1]:
                    check = await client.get_messages(entity, ids=msg.id + offset)
                    if check and check.photo:
                        photo_msg = check
                        break
            except Exception:
                pass

        signal_msgs.append({
            "parsed": parsed,
            "text": text,
            "photo_msg": photo_msg,
            "msg_id": msg.id,
            "date": msg.date,
        })

    logger.info(f"📋 Found {len(signal_msgs)} signals with #сетап")

    added = 0
    skipped_dup = 0
    skipped_invalid = 0

    for item in signal_msgs:
        parsed = item['parsed']
        symbol = parsed['symbol']
        direction = parsed['direction']
        msg_date = item['date']

        # Check duplicate
        existing = await db.signals.find_one({
            "symbol": symbol,
            "direction": direction,
            "entry_price": parsed['entry_price'],
        })
        if existing:
            skipped_dup += 1
            logger.info(f"⏭ Skip duplicate: {symbol} {direction}")
            continue

        # Check if price hasn't passed TP/SL
        current_price = await get_price(symbol)
        if current_price > 0 and not await is_signal_still_valid(parsed, current_price):
            skipped_invalid += 1
            logger.info(f"❌ Skip expired: {symbol} {direction} (price={current_price}, TP={parsed['take_profit']}, SL={parsed['stop_loss']})")
            continue

        # Download chart
        chart_path = None
        saved_chart = None
        if item['photo_msg']:
            try:
                chart_path = await client.download_media(
                    item['photo_msg'], file=tempfile.mktemp(suffix='.jpg', dir='/tmp')
                )
            except Exception as e:
                logger.error(f"Photo download error: {e}")

        # Extract DCA#4
        dca_data = None
        if chart_path and os.path.exists(chart_path):
            dca_data = await extract_dca4(chart_path, parsed)

            timestamp_str = msg_date.strftime('%Y%m%d_%H%M%S') if msg_date else datetime.now().strftime('%Y%m%d_%H%M%S')
            chart_filename = f"{symbol}_{direction}_{timestamp_str}.jpg"
            saved_chart = str(CHARTS_DIR / chart_filename)
            shutil.copy2(chart_path, saved_chart)

            try:
                os.unlink(chart_path)
            except Exception:
                pass

        # Save to DB
        doc = {
            "id": f"tradium-backfill-{item['msg_id']}",
            "original_text": item['text'][:1000],
            "symbol": symbol,
            "direction": direction,
            "entry_price": parsed['entry_price'],
            "take_profit": parsed['take_profit'],
            "stop_loss": parsed['stop_loss'],
            "rr_ratio": parsed['rr_ratio'],
            "risk_pct": parsed['risk_pct'],
            "amount": parsed['amount'],
            "timeframe": parsed['timeframe'],
            "trend": parsed['trend'],
            "ma_status": parsed['ma_status'],
            "rsi_status": parsed['rsi_status'],
            "volume_1d": parsed['volume_1d'],
            "tp_pct": parsed['tp_pct'],
            "sl_pct": parsed['sl_pct'],
            "dca_data": dca_data,
            "dca4_level": dca_data.get('dca4') if dca_data else None,
            "chart_path": saved_chart,
            "status": "watching",
            "entry_triggered": False,
            "timestamp": msg_date.isoformat() if msg_date else datetime.now(timezone.utc).isoformat(),
            "source": "tradium-backfill"
        }
        await db.signals.insert_one(doc)
        added += 1

        dca4_str = f"DCA#4={dca_data['dca4']}" if dca_data and dca_data.get('dca4') else "no DCA#4"
        chart_str = "📊" if saved_chart else "❌"
        logger.info(f"✅ [{added}] {symbol} {direction} {parsed['timeframe']} | {dca4_str} | price={current_price} | chart={chart_str}")

        await asyncio.sleep(1)

    await client.disconnect()

    logger.info(f"""
{'='*50}
📊 BACKFILL COMPLETE
{'='*50}
✅ Добавлено: {added}
⏭ Дубликаты: {skipped_dup}
❌ Отработанные (TP/SL): {skipped_invalid}
{'='*50}
""")


if __name__ == "__main__":
    asyncio.run(main())
