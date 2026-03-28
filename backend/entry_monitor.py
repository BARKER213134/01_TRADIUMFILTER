#!/usr/bin/env python3
"""
Entry Monitor v3
Monitors price and sends beautiful alerts when DCA #4 is reached
Sends chart image with the notification
"""

import asyncio
import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot
from motor.motor_asyncio import AsyncIOMotorClient
import ccxt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')

mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[db_name]

exchange = ccxt.kraken({'enableRateLimit': True})
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

price_cache = {}


async def get_price(symbol: str) -> float:
    """Get current price with caching (5s)"""
    base = symbol.replace("USDT", "").replace("PERP", "").upper()

    if base in price_cache:
        cached_time, cached_price = price_cache[base]
        if (datetime.now() - cached_time).seconds < 5:
            return cached_price

    for sym in [f"{base}/USD", f"{base}/USDT"]:
        try:
            ticker = exchange.fetch_ticker(sym)
            if ticker and ticker.get('last'):
                price = float(ticker['last'])
                price_cache[base] = (datetime.now(), price)
                return price
        except:
            continue

    # Fallback OKX
    try:
        okx = ccxt.okx({'enableRateLimit': True})
        ticker = okx.fetch_ticker(f"{base}/USDT")
        if ticker and ticker.get('last'):
            price = float(ticker['last'])
            price_cache[base] = (datetime.now(), price)
            return price
    except:
        pass

    return 0


def format_entry_alert(signal: dict, current_price: float) -> str:
    """Format beautiful entry alert message"""
    direction = signal['direction']
    symbol = signal['symbol'].replace('USDT', '')
    timeframe = signal.get('timeframe', '4h')
    dca_data = signal.get('dca_data', {})
    dca4 = signal.get('dca4_level', 0)

    if direction == 'SHORT':
        dir_icon = "🔴"
        dir_text = "ШОРТ"
        action = "SELL"
        zone_type = "сопротивления"
    else:
        dir_icon = "🟢"
        dir_text = "ЛОНГ"
        action = "BUY"
        zone_type = "поддержки"

    # Zone info
    zone_low = dca_data.get('zone_low', '')
    zone_high = dca_data.get('zone_high', '')
    zone_text = f"{zone_low} — {zone_high}" if zone_low and zone_high else "N/A"

    # DCA levels display
    dca_lines = ""
    for i in range(1, 6):
        lvl = dca_data.get(f'dca{i}', '')
        if lvl:
            marker = " ◀ ВХОД" if i == 4 else ""
            dca_lines += f"    {'│' if i < 5 else '└'} DCA #{i}: <code>{lvl}</code>{marker}\n"

    # Distance from entry to TP/SL
    tp = signal.get('take_profit', 0)
    sl = signal.get('stop_loss', 0)
    tp_pct = signal.get('tp_pct', 0)
    sl_pct = signal.get('sl_pct', 0)
    rr = signal.get('rr_ratio', 0)

    # Trend indicators
    trend = signal.get('trend', '')
    ma = signal.get('ma_status', '')
    rsi = signal.get('rsi_status', '')

    msg = f"""{dir_icon}{dir_icon}{dir_icon} <b>СИГНАЛ ВХОДА — {dir_text}</b> {dir_icon}{dir_icon}{dir_icon}

━━━━━━━━━━━━━━━━━━━━━━

<b>${symbol}</b>  •  {timeframe}  •  {action}

📍 <b>Цена достигла DCA #4</b>
    Текущая: <code>{current_price}</code>
    DCA #4:  <code>{dca4}</code>

━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>Параметры сделки:</b>
    TP: <code>{tp}</code>  (+{tp_pct}%)
    SL: <code>{sl}</code>  (-{sl_pct}%)
    R:R: <code>{rr}</code>

📊 <b>Уровни DCA:</b>
{dca_lines}
📐 <b>Зона {zone_type}:</b>
    {zone_text}

📈 <b>Индикаторы:</b>
    Тренд: {trend}
    MA: {ma}  •  RSI: {rsi}

━━━━━━━━━━━━━━━━━━━━━━

⚡️ <b>{action} {symbol}USDT @ {current_price}</b>"""

    return msg.strip()


def format_tp_sl_alert(signal: dict, current_price: float, result: str) -> str:
    """Format TP/SL hit alert"""
    symbol = signal['symbol'].replace('USDT', '')
    direction = signal['direction']
    entry = signal.get('trigger_price', signal.get('dca4_level', 0))

    if result == "TP_HIT":
        icon = "✅"
        status = "TAKE PROFIT"
        if direction == 'SHORT':
            pnl_pct = ((entry - current_price) / entry) * 100 if entry else 0
        else:
            pnl_pct = ((current_price - entry) / entry) * 100 if entry else 0
    else:
        icon = "❌"
        status = "STOP LOSS"
        if direction == 'SHORT':
            pnl_pct = -((current_price - entry) / entry) * 100 if entry else 0
        else:
            pnl_pct = -((entry - current_price) / entry) * 100 if entry else 0

    pnl_sign = "+" if pnl_pct > 0 else ""
    dir_text = "ШОРТ" if direction == 'SHORT' else "ЛОНГ"

    return f"""{icon}{icon}{icon} <b>{status}</b> {icon}{icon}{icon}

━━━━━━━━━━━━━━━━━━━━━━

<b>${symbol}</b>  •  {dir_text}

    Вход: <code>{entry}</code>
    Закрытие: <code>{current_price}</code>
    P&L: <b>{pnl_sign}{pnl_pct:.2f}%</b>

━━━━━━━━━━━━━━━━━━━━━━"""


async def send_alert(text: str, chart_path: str = None):
    """Send alert to all registered users"""
    if not bot:
        return

    users = await db.bot_users.find({}, {"_id": 0, "chat_id": 1}).to_list(100)

    for user in users:
        try:
            if chart_path and os.path.exists(chart_path):
                # Send text first, then chart
                await bot.send_message(
                    chat_id=user['chat_id'],
                    text=text,
                    parse_mode='HTML'
                )
                with open(chart_path, 'rb') as photo:
                    await bot.send_photo(
                        chat_id=user['chat_id'],
                        photo=photo,
                        caption=f"📊 График сетапа"
                    )
            else:
                await bot.send_message(
                    chat_id=user['chat_id'],
                    text=text,
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Send error to {user['chat_id']}: {e}")


async def check_dca4_entries():
    """Check if price reached DCA #4 for any watching signals"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    signals = await db.signals.find({
        "status": "watching",
        "entry_triggered": False,
        "dca4_level": {"$ne": None},
        "timestamp": {"$gte": cutoff.isoformat()}
    }, {"_id": 0}).to_list(100)

    if signals:
        logger.info(f"👀 Watching {len(signals)} signals for DCA #4 entry")
    else:
        logger.debug("No watching signals")

    for signal in signals:
        try:
            symbol = signal.get('symbol', '')
            dca4 = float(signal.get('dca4_level', 0))
            direction = signal.get('direction', '')

            if not symbol or dca4 <= 0:
                continue

            price = await get_price(symbol)
            if price <= 0:
                continue

            triggered = False
            tolerance = dca4 * 0.003  # 0.3% tolerance

            if direction == 'SHORT' and price >= dca4 - tolerance:
                triggered = True
            elif direction == 'LONG' and price <= dca4 + tolerance:
                triggered = True

            if triggered:
                logger.info(f"🎯 DCA#4 HIT! {symbol} {direction} @ {price} (DCA#4={dca4})")

                # Format and send alert
                alert_text = format_entry_alert(signal, price)
                chart_path = signal.get('chart_path')
                await send_alert(alert_text, chart_path)

                # Update signal in DB
                await db.signals.update_one(
                    {"id": signal['id']},
                    {"$set": {
                        "status": "entered",
                        "entry_triggered": True,
                        "trigger_price": price,
                        "trigger_time": datetime.now(timezone.utc).isoformat()
                    }}
                )

                # Create entry record for TP/SL tracking
                await db.entry_signals.insert_one({
                    "signal_id": signal['id'],
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": price,
                    "dca4_level": dca4,
                    "take_profit": signal.get('take_profit', 0),
                    "stop_loss": signal.get('stop_loss', 0),
                    "rr_ratio": signal.get('rr_ratio', 0),
                    "chart_path": signal.get('chart_path'),
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                    "status": "OPEN"
                })

        except Exception as e:
            logger.error(f"Check error {signal.get('symbol', '?')}: {e}")

        await asyncio.sleep(0.3)


async def check_tp_sl():
    """Check if open positions hit TP or SL"""
    open_signals = await db.entry_signals.find(
        {"status": "OPEN"}, {"_id": 0}
    ).to_list(100)

    for signal in open_signals:
        try:
            symbol = signal.get('symbol', '')
            price = await get_price(symbol)
            if price <= 0:
                continue

            tp = float(signal.get('take_profit', 0))
            sl = float(signal.get('stop_loss', 0))
            direction = signal.get('direction', '')

            result = None
            if direction == 'SHORT':
                if tp > 0 and price <= tp:
                    result = "TP_HIT"
                elif sl > 0 and price >= sl:
                    result = "SL_HIT"
            elif direction == 'LONG':
                if tp > 0 and price >= tp:
                    result = "TP_HIT"
                elif sl > 0 and price <= sl:
                    result = "SL_HIT"

            if result:
                alert_text = format_tp_sl_alert(signal, price, result)
                await send_alert(alert_text)

                await db.entry_signals.update_one(
                    {"signal_id": signal['signal_id']},
                    {"$set": {
                        "status": result,
                        "closed_at": datetime.now(timezone.utc).isoformat(),
                        "close_price": price
                    }}
                )

                await db.signals.update_one(
                    {"id": signal['signal_id']},
                    {"$set": {"status": result.lower()}}
                )

                logger.info(f"{'✅' if result == 'TP_HIT' else '❌'} {symbol} {result} @ {price}")

        except Exception as e:
            logger.error(f"TP/SL check error: {e}")


async def main():
    """Main monitoring loop"""
    logger.info("🎯 Entry Monitor v3 started — watching for DCA #4 levels")

    check_counter = 0
    heartbeat = 0

    while True:
        try:
            await check_dca4_entries()

            check_counter += 1
            if check_counter >= 3:
                await check_tp_sl()
                check_counter = 0

            heartbeat += 1
            if heartbeat % 30 == 0:  # Every 5 min
                watching = await db.signals.count_documents({"status": "watching", "dca4_level": {"$ne": None}})
                open_pos = await db.entry_signals.count_documents({"status": "OPEN"})
                logger.info(f"💓 Heartbeat: watching={watching}, open={open_pos}")

        except Exception as e:
            logger.error(f"Loop error: {e}")

        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
