#!/usr/bin/env python3
"""
Entry Monitor v4
Two-stage confirmation:
  Stage 1: Price reaches DCA #4 → status "dca4_reached" → notify "waiting for reversal"
  Stage 2: Reversal candle detected → status "confirmed" → send CONFIRMED entry signal
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

from candle_patterns import detect_reversal_pattern

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)

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
        except Exception:
            continue

    try:
        okx = ccxt.okx({'enableRateLimit': True})
        ticker = okx.fetch_ticker(f"{base}/USDT")
        if ticker and ticker.get('last'):
            price = float(ticker['last'])
            price_cache[base] = (datetime.now(), price)
            return price
    except Exception:
        pass

    return 0


def format_dca4_reached(signal: dict, current_price: float) -> str:
    """Stage 1 alert: DCA #4 reached — full entry signal"""
    direction = signal['direction']
    symbol = signal['symbol'].replace('USDT', '')
    timeframe = signal.get('timeframe', '4h')
    dca4 = signal.get('dca4_level', 0)
    dca_data = signal.get('dca_data', {})

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

    tp = signal.get('take_profit', 0)
    sl = signal.get('stop_loss', 0)
    tp_pct = signal.get('tp_pct', 0)
    sl_pct = signal.get('sl_pct', 0)
    rr = signal.get('rr_ratio', 0)

    trend = signal.get('trend', '')
    ma = signal.get('ma_status', '')
    rsi = signal.get('rsi_status', '')

    zone_low = dca_data.get('zone_low', '')
    zone_high = dca_data.get('zone_high', '')
    zone_text = f"{zone_low} — {zone_high}" if zone_low and zone_high else "N/A"

    dca_lines = ""
    for i in range(1, 6):
        lvl = dca_data.get(f'dca{i}', '')
        if lvl:
            marker = " ◀ ВХОД" if i == 4 else ""
            dca_lines += f"    {'│' if i < 5 else '└'} DCA #{i}: <code>{lvl}</code>{marker}\n"

    return f"""{dir_icon}{dir_icon}{dir_icon} <b>СИГНАЛ ВХОДА — DCA #4 {dir_text}</b> {dir_icon}{dir_icon}{dir_icon}

━━━━━━━━━━━━━━━━━━━━━━

<b>${symbol}</b>  •  {timeframe}  •  {action}

📍 <b>Точка входа</b>
    Цена: <code>{current_price}</code>
    DCA #4: <code>{dca4}</code>

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

⚡ <b>{action} {symbol}USDT @ {current_price}</b>
⏳ Жду разворотную свечу для подтверждения"""


def format_confirmed_entry(signal: dict, current_price: float, pattern: dict) -> str:
    """Stage 2 alert: Reversal candle confirmed → ENTER"""
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

    zone_low = dca_data.get('zone_low', '')
    zone_high = dca_data.get('zone_high', '')
    zone_text = f"{zone_low} — {zone_high}" if zone_low and zone_high else "N/A"

    dca_lines = ""
    for i in range(1, 6):
        lvl = dca_data.get(f'dca{i}', '')
        if lvl:
            marker = " ◀ ВХОД" if i == 4 else ""
            dca_lines += f"    {'│' if i < 5 else '└'} DCA #{i}: <code>{lvl}</code>{marker}\n"

    tp = signal.get('take_profit', 0)
    sl = signal.get('stop_loss', 0)
    tp_pct = signal.get('tp_pct', 0)
    sl_pct = signal.get('sl_pct', 0)
    rr = signal.get('rr_ratio', 0)

    trend = signal.get('trend', '')
    ma = signal.get('ma_status', '')
    rsi = signal.get('rsi_status', '')

    pattern_name = pattern.get('pattern', '?')
    strength = pattern.get('strength', 0)
    strength_bar = "🟢" * int(strength * 5)

    candle = pattern.get('candle_data', {})
    candle_text = ""
    if candle:
        candle_text = f"    O: <code>{candle.get('open', '')}</code>  H: <code>{candle.get('high', '')}</code>  L: <code>{candle.get('low', '')}</code>  C: <code>{candle.get('close', '')}</code>"

    return f"""{dir_icon}{dir_icon}{dir_icon} <b>ПОДТВЕРЖДЁННЫЙ ВХОД — {dir_text}</b> {dir_icon}{dir_icon}{dir_icon}

━━━━━━━━━━━━━━━━━━━━━━

<b>${symbol}</b>  •  {timeframe}  •  {action}

🕯 <b>Разворотная свеча подтверждена!</b>
    Паттерн: <b>{pattern_name}</b>
    Сила: {strength_bar} ({strength:.0%})
{candle_text}

📍 <b>Точка входа</b>
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
                await bot.send_message(chat_id=user['chat_id'], text=text, parse_mode='HTML')
                with open(chart_path, 'rb') as photo:
                    await bot.send_photo(chat_id=user['chat_id'], photo=photo, caption="📊 График сетапа")
            else:
                await bot.send_message(chat_id=user['chat_id'], text=text, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Send error to {user['chat_id']}: {e}")


# ========== STAGE 1: Price reaches DCA #4 ==========

async def check_dca4_entries():
    """Check if price reached DCA #4 for watching signals → move to dca4_reached"""
    signals = await db.signals.find({
        "status": "watching",
        "entry_triggered": False,
        "dca4_level": {"$ne": None},
    }, {"_id": 0}).to_list(100)

    if signals:
        logger.info(f"👀 Stage 1: Watching {len(signals)} signals for DCA #4")

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
            tolerance = dca4 * 0.003

            if direction == 'SHORT' and price >= dca4 - tolerance:
                triggered = True
            elif direction == 'LONG' and price <= dca4 + tolerance:
                triggered = True

            if triggered:
                # Dedup: skip if entry already exists
                existing = await db.entry_signals.find_one({"signal_id": signal['id'] + "_dca4"})
                if existing:
                    continue

                logger.info(f"📍 Stage 1: DCA#4 HIT! {symbol} {direction} @ {price} (DCA#4={dca4})")

                alert_text = format_dca4_reached(signal, price)
                chart_path = signal.get('chart_path')
                await send_alert(alert_text, chart_path)

                await db.signals.update_one(
                    {"id": signal['id']},
                    {"$set": {
                        "status": "dca4_reached",
                        "dca4_reached_price": price,
                        "dca4_reached_at": datetime.now(timezone.utc).isoformat()
                    }}
                )

                await db.entry_signals.insert_one({
                    "signal_id": signal['id'] + "_dca4",
                    "signal_ref": signal['id'],
                    "symbol": symbol,
                    "direction": direction,
                    "entry_type": "DCA#4",
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
            logger.error(f"Stage 1 error {signal.get('symbol', '?')}: {e}")

        await asyncio.sleep(0.3)


# ========== STAGE 2: Wait for reversal candle ==========

async def check_reversal_candles():
    """Check for reversal candle patterns on dca4_reached signals → confirm entry"""
    signals = await db.signals.find({
        "status": "dca4_reached",
        "dca4_level": {"$ne": None}
    }, {"_id": 0}).to_list(100)

    if signals:
        logger.info(f"🕯 Stage 2: Checking {len(signals)} signals for reversal candles")

    for signal in signals:
        try:
            symbol = signal.get('symbol', '')
            direction = signal.get('direction', '')
            timeframe = signal.get('timeframe', '4h')

            if not symbol or not direction:
                continue

            pattern = detect_reversal_pattern(symbol, timeframe, direction)

            if pattern:
                # Dedup: skip if reversal entry already exists
                existing = await db.entry_signals.find_one({"signal_id": signal['id'] + "_reversal"})
                if existing:
                    continue

                price = await get_price(symbol)
                if price <= 0:
                    continue

                logger.info(f"🕯 Stage 2: CONFIRMED! {symbol} {direction} — {pattern['pattern']} (strength={pattern['strength']})")

                alert_text = format_confirmed_entry(signal, price, pattern)
                chart_path = signal.get('chart_path')
                await send_alert(alert_text, chart_path)

                await db.signals.update_one(
                    {"id": signal['id']},
                    {"$set": {
                        "status": "entered",
                        "entry_triggered": True,
                        "trigger_price": price,
                        "trigger_time": datetime.now(timezone.utc).isoformat(),
                        "reversal_pattern": pattern['pattern'],
                        "pattern_strength": pattern['strength'],
                        "pattern_candle": pattern.get('candle_data', {})
                    }}
                )

                await db.entry_signals.insert_one({
                    "signal_id": signal['id'] + "_reversal",
                    "signal_ref": signal['id'],
                    "symbol": symbol,
                    "direction": direction,
                    "entry_type": "Разворот",
                    "entry_price": price,
                    "dca4_level": signal.get('dca4_level'),
                    "take_profit": signal.get('take_profit', 0),
                    "stop_loss": signal.get('stop_loss', 0),
                    "rr_ratio": signal.get('rr_ratio', 0),
                    "chart_path": signal.get('chart_path'),
                    "reversal_pattern": pattern['pattern'],
                    "pattern_strength": pattern['strength'],
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                    "status": "OPEN"
                })

        except Exception as e:
            logger.error(f"Stage 2 error {signal.get('symbol', '?')}: {e}")

        await asyncio.sleep(1)


# ========== TP/SL monitoring ==========

async def check_tp_sl():
    """Check if open positions hit TP or SL — one notification per parent signal"""
    open_signals = await db.entry_signals.find(
        {"status": "OPEN"}, {"_id": 0}
    ).to_list(100)

    # Group by signal_ref to avoid duplicate alerts for same parent signal
    by_ref = {}
    for signal in open_signals:
        ref = signal.get('signal_ref', signal.get('signal_id', ''))
        if ref not in by_ref:
            by_ref[ref] = signal  # take first (usually DCA#4)

    for ref, signal in by_ref.items():
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
                # Send ONE alert
                alert_text = format_tp_sl_alert(signal, price, result)
                await send_alert(alert_text)

                # Close ALL entry_signals for this parent signal
                await db.entry_signals.update_many(
                    {"signal_ref": ref},
                    {"$set": {
                        "status": result,
                        "closed_at": datetime.now(timezone.utc).isoformat(),
                        "close_price": price
                    }}
                )

                # Update parent signal status
                await db.signals.update_one(
                    {"id": ref},
                    {"$set": {"status": result.lower()}}
                )

                logger.info(f"{'✅' if result == 'TP_HIT' else '❌'} {symbol} {result} @ {price}")

        except Exception as e:
            logger.error(f"TP/SL check error: {e}")


async def send_health_report():
    """Send short health report to Telegram every 2 hours"""
    if not bot:
        return

    try:
        watching = await db.signals.count_documents({"status": "watching", "dca4_level": {"$ne": None}})
        dca4_wait = await db.signals.count_documents({"status": "dca4_reached"})
        open_pos = await db.entry_signals.count_documents({"status": "OPEN"})
        tp = await db.entry_signals.count_documents({"status": "TP_HIT"})
        sl = await db.entry_signals.count_documents({"status": "SL_HIT"})

        # Test price fetch
        price_ok = False
        try:
            test_price = await get_price("BTCUSDT")
            price_ok = test_price > 0
        except Exception:
            pass

        now = datetime.now(timezone.utc).strftime("%H:%M UTC")

        text = f"""💚 <b>Бот работает</b> • {now}

👀 {watching} слежу | 📍 {dca4_wait} DCA#4 | 📊 {open_pos} открыто
✅ {tp} TP | ❌ {sl} SL | {"📈" if price_ok else "⚠️"} Цены: {"OK" if price_ok else "ОШИБКА"}"""

        await send_alert(text)
        logger.info(f"💚 Health report sent: watching={watching}, dca4={dca4_wait}, prices={'OK' if price_ok else 'FAIL'}")

    except Exception as e:
        logger.error(f"Health report error: {e}")


# ========== Main Loop ==========

async def main():
    """Main monitoring loop with two stages"""
    logger.info("🎯 Entry Monitor v4 — Two-stage confirmation (DCA#4 + Reversal Candle)")

    check_counter = 0
    candle_counter = 0
    heartbeat = 0
    health_counter = 0
    HEALTH_INTERVAL = 720  # 720 * 10s = 7200s = 2 hours

    while True:
        try:
            # Stage 1: Check DCA #4 every 10s
            await check_dca4_entries()

            # Stage 2: Check reversal candles every 30s
            candle_counter += 1
            if candle_counter >= 3:
                await check_reversal_candles()
                candle_counter = 0

            # TP/SL: Check every 30s
            check_counter += 1
            if check_counter >= 3:
                await check_tp_sl()
                check_counter = 0

            # Heartbeat log every 5 min
            heartbeat += 1
            if heartbeat % 30 == 0:
                watching = await db.signals.count_documents({"status": "watching", "dca4_level": {"$ne": None}})
                dca4_wait = await db.signals.count_documents({"status": "dca4_reached"})
                open_pos = await db.entry_signals.count_documents({"status": "OPEN"})
                logger.info(f"💓 Heartbeat: watching={watching}, dca4_reached={dca4_wait}, open={open_pos}")

            # Health report to Telegram every 2 hours
            health_counter += 1
            if health_counter >= HEALTH_INTERVAL:
                await send_health_report()
                health_counter = 0

        except Exception as e:
            logger.error(f"Loop error: {e}")

        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
