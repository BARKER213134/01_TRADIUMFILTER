#!/usr/bin/env python3
"""
Entry Point Monitor v2
Watches price and alerts when entry price is reached
Готов для вебхука автоматической торговли
"""

import asyncio
import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from telegram import Bot
from motor.motor_asyncio import AsyncIOMotorClient
import ccxt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'test_database')

# MongoDB
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[db_name]

# Exchange for price data
exchange = ccxt.kraken({'enableRateLimit': True})

# Telegram bot
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

# Cache for prices
price_cache = {}


async def get_current_price(symbol: str) -> float:
    """Get current price from exchange with caching"""
    base = symbol.replace("USDT", "").replace("PERP", "").upper()
    
    # Check cache (valid for 5 seconds)
    cache_key = base
    if cache_key in price_cache:
        cached_time, cached_price = price_cache[cache_key]
        if (datetime.now() - cached_time).seconds < 5:
            return cached_price
    
    try:
        for sym in [f"{base}/USD", f"{base}/USDT"]:
            try:
                ticker = exchange.fetch_ticker(sym)
                if ticker and ticker.get('last'):
                    price = float(ticker['last'])
                    price_cache[cache_key] = (datetime.now(), price)
                    return price
            except:
                continue
        
        # Fallback to OKX
        try:
            okx = ccxt.okx({'enableRateLimit': True})
            ticker = okx.fetch_ticker(f"{base}/USDT")
            if ticker and ticker.get('last'):
                price = float(ticker['last'])
                price_cache[cache_key] = (datetime.now(), price)
                return price
        except:
            pass
            
    except Exception as e:
        logger.error(f"Price error {symbol}: {e}")
    
    return 0


def check_entry_reached(signal: dict, current_price: float) -> Optional[dict]:
    """
    Check if entry price has been reached
    Returns entry data if triggered, None otherwise
    """
    if current_price <= 0:
        return None
    
    entry = float(signal['entry_price'])
    tp = float(signal['take_profit'])
    sl = float(signal['stop_loss'])
    direction = signal['direction']
    
    # Tolerance: 0.3% from entry price
    tolerance = entry * 0.003
    
    triggered = False
    trigger_type = None
    
    if direction == 'BUY':
        # LONG: trigger when price <= entry (or slightly above)
        if current_price <= entry + tolerance:
            triggered = True
            if current_price < entry:
                trigger_type = "НИЖЕ_ВХОДА"
            else:
                trigger_type = "НА_УРОВНЕ"
    else:
        # SHORT: trigger when price >= entry (or slightly below)
        if current_price >= entry - tolerance:
            triggered = True
            if current_price > entry:
                trigger_type = "ВЫШЕ_ВХОДА"
            else:
                trigger_type = "НА_УРОВНЕ"
    
    if not triggered:
        return None
    
    # Calculate actual R:R with current price
    if direction == 'BUY':
        risk = current_price - sl
        reward = tp - current_price
    else:
        risk = sl - current_price
        reward = current_price - tp
    
    actual_rr = reward / risk if risk > 0 else 0
    
    # Calculate profit/loss distances
    if direction == 'BUY':
        tp_distance = ((tp - current_price) / current_price) * 100
        sl_distance = ((current_price - sl) / current_price) * 100
    else:
        tp_distance = ((current_price - tp) / current_price) * 100
        sl_distance = ((sl - current_price) / current_price) * 100
    
    return {
        "triggered": True,
        "trigger_type": trigger_type,
        "current_price": current_price,
        "entry_price": entry,
        "actual_rr": round(actual_rr, 2),
        "tp_distance_pct": round(tp_distance, 2),
        "sl_distance_pct": round(sl_distance, 2),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


async def send_entry_signal(signal: dict, entry_data: dict):
    """Send ENTRY signal to users - ready for webhook"""
    if not bot:
        return
    
    direction = signal['direction']
    dir_emoji = "🟢 LONG" if direction == 'BUY' else "🔴 SHORT"
    dir_text = "ЛОНГ" if direction == 'BUY' else "ШОРТ"
    
    current_price = entry_data['current_price']
    
    message = f"""🎯 <b>СИГНАЛ ВХОДА</b>

{dir_emoji} <b>{signal['symbol']}</b>

📍 <b>ВХОД:</b>
├ Цена сейчас: <code>{current_price}</code>
├ Целевой вход: <code>{signal['entry_price']}</code>
├ Статус: {entry_data['trigger_type']}

🎯 <b>ЦЕЛИ:</b>
├ Take Profit: <code>{signal['take_profit']}</code> (+{entry_data['tp_distance_pct']}%)
├ Stop Loss: <code>{signal['stop_loss']}</code> (-{entry_data['sl_distance_pct']}%)
└ R:R: <code>{entry_data['actual_rr']}</code>

⚡️ <b>ДЕЙСТВИЕ: ОТКРЫТЬ {dir_text}</b>

🔗 Webhook данные:
<code>{{
  "action": "{direction}",
  "symbol": "{signal['symbol']}",
  "price": {current_price},
  "tp": {signal['take_profit']},
  "sl": {signal['stop_loss']}
}}</code>"""

    # Save entry signal to database
    entry_record = {
        "signal_id": signal['id'],
        "symbol": signal['symbol'],
        "direction": direction,
        "entry_price": current_price,
        "take_profit": signal['take_profit'],
        "stop_loss": signal['stop_loss'],
        "rr_ratio": entry_data['actual_rr'],
        "triggered_at": entry_data['timestamp'],
        "status": "OPEN",
        "type": "entry_signal"
    }
    await db.entry_signals.insert_one(entry_record)
    
    # Send to all users
    users = await db.bot_users.find({}, {"_id": 0, "chat_id": 1}).to_list(100)
    for user in users:
        try:
            await bot.send_message(chat_id=user['chat_id'], text=message, parse_mode='HTML')
            logger.info(f"Entry signal sent for {signal['symbol']}")
        except Exception as e:
            logger.error(f"Send error: {e}")
    
    # Mark original signal as entry_triggered
    await db.signals.update_one(
        {"id": signal['id']},
        {"$set": {
            "entry_triggered": True,
            "entry_trigger_time": entry_data['timestamp'],
            "entry_trigger_price": current_price
        }}
    )


async def check_active_signals():
    """Check all active signals for entry points"""
    # Get signals from last 12 hours that:
    # - Were ACCEPTED by AI
    # - Haven't been triggered yet
    cutoff = datetime.now(timezone.utc) - timedelta(hours=12)
    
    signals = await db.signals.find({
        "timestamp": {"$gte": cutoff.isoformat()},
        "status": "accepted",
        "entry_triggered": {"$ne": True}
    }, {"_id": 0}).to_list(100)
    
    if signals:
        logger.info(f"Monitoring {len(signals)} active signals")
    
    for signal in signals:
        try:
            symbol = signal.get('symbol', '')
            if not symbol:
                continue
            
            current_price = await get_current_price(symbol)
            if current_price <= 0:
                continue
            
            entry_data = check_entry_reached(signal, current_price)
            
            if entry_data and entry_data['triggered']:
                logger.info(f"🎯 Entry triggered for {symbol} at {current_price}")
                await send_entry_signal(signal, entry_data)
            
        except Exception as e:
            logger.error(f"Check error {signal.get('symbol', '?')}: {e}")
        
        await asyncio.sleep(0.3)


async def check_price_targets():
    """Check if open positions hit TP or SL"""
    # Get open entry signals
    open_signals = await db.entry_signals.find({
        "status": "OPEN"
    }, {"_id": 0}).to_list(100)
    
    for signal in open_signals:
        try:
            symbol = signal.get('symbol', '')
            current_price = await get_current_price(symbol)
            if current_price <= 0:
                continue
            
            tp = float(signal['take_profit'])
            sl = float(signal['stop_loss'])
            direction = signal['direction']
            
            result = None
            
            if direction == 'BUY':
                if current_price >= tp:
                    result = "TP_HIT"
                elif current_price <= sl:
                    result = "SL_HIT"
            else:
                if current_price <= tp:
                    result = "TP_HIT"
                elif current_price >= sl:
                    result = "SL_HIT"
            
            if result:
                emoji = "✅" if result == "TP_HIT" else "❌"
                status_text = "TAKE PROFIT" if result == "TP_HIT" else "STOP LOSS"
                
                message = f"""{emoji} <b>{status_text} ДОСТИГНУТ</b>

{signal['symbol']} | {'LONG' if direction == 'BUY' else 'SHORT'}
├ Вход: <code>{signal['entry_price']}</code>
├ Текущая: <code>{current_price}</code>
└ Результат: <b>{status_text}</b>"""

                # Update status
                await db.entry_signals.update_one(
                    {"signal_id": signal['signal_id']},
                    {"$set": {"status": result, "closed_at": datetime.now(timezone.utc).isoformat(), "close_price": current_price}}
                )
                
                # Notify users
                users = await db.bot_users.find({}, {"_id": 0, "chat_id": 1}).to_list(100)
                for user in users:
                    try:
                        await bot.send_message(chat_id=user['chat_id'], text=message, parse_mode='HTML')
                    except:
                        pass
                
                logger.info(f"{emoji} {symbol} {result} at {current_price}")
                
        except Exception as e:
            logger.error(f"Target check error: {e}")


async def main():
    """Main monitoring loop"""
    logger.info("🎯 Entry Monitor v2 started")
    
    check_counter = 0
    
    while True:
        try:
            # Check entry points every 10 seconds
            await check_active_signals()
            
            # Check TP/SL every 30 seconds
            check_counter += 1
            if check_counter >= 3:
                await check_price_targets()
                check_counter = 0
                
        except Exception as e:
            logger.error(f"Loop error: {e}")
        
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
