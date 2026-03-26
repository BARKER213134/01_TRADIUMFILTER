#!/usr/bin/env python3
"""
Automatic Signal Monitor
Reads signals from @cvizor_bot via Telethon and analyzes them with AI
"""

import asyncio
import os
import re
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telegram import Bot

# AI and Market Data
from binance.um_futures import UMFutures
import pandas as pd
import ta
from emergentintegrations.llm.chat import LlmChat, UserMessage

# MongoDB
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Config
API_ID = int(os.environ.get('TELEGRAM_API_ID', 0))
API_HASH = os.environ.get('TELEGRAM_API_HASH', '')
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
SIGNAL_SOURCE = os.environ.get('SIGNAL_SOURCE_CHAT', 'cvizor_bot')
SESSION_FILE = ROOT_DIR / 'telethon_session'

# MongoDB
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'test_database')
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[db_name]

# Binance client
binance_client = UMFutures()

# Telegram Bot for sending results
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

# Store user chat IDs who started the bot
user_chat_ids = set()

def parse_signal(text: str) -> dict | None:
    """Parse trading signal from various formats including cvizor.com breakout signals"""
    text_upper = text.upper()
    original_text = text
    
    # === CVIZOR.COM BREAKOUT FORMAT ===
    symbol_match = re.search(r'#([A-Z0-9]+)(?:\.P)?', text_upper)
    
    if 'ПРОБОЙ' in text_upper or 'BREAKOUT' in text_upper or 'BREAK' in text_upper:
        if 'ПОДДЕРЖК' in text_upper or 'SUPPORT' in text_upper:
            direction = 'SELL'
            signal_type = 'support_breakout'
        elif 'СОПРОТИВЛЕН' in text_upper or 'RESISTANCE' in text_upper:
            direction = 'BUY'
            signal_type = 'resistance_breakout'
        else:
            direction = 'BUY'
            signal_type = 'breakout'
        
        all_numbers = re.findall(r'(\d+\.\d+)', original_text)
        all_numbers = [float(n) for n in all_numbers]
        price_numbers = [n for n in all_numbers if 0.0001 < n < 100000]
        
        if symbol_match and len(price_numbers) >= 2:
            symbol = symbol_match.group(1)
            if symbol.endswith('P'):
                symbol = symbol[:-1]
            if not symbol.endswith('USDT'):
                symbol = symbol + 'USDT'
            
            level = price_numbers[0]
            price = price_numbers[1] if len(price_numbers) > 1 else level
            
            entry = price
            move_pct = 0.02
            if direction == 'SELL':
                tp = entry * (1 - move_pct * 2)
                sl = level * 1.01
            else:
                tp = entry * (1 + move_pct * 2)
                sl = level * 0.99
            
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rr_ratio = reward / risk if risk > 0 else 0
            
            return {
                "symbol": symbol,
                "direction": direction,
                "entry_price": round(entry, 6),
                "take_profit": round(tp, 6),
                "stop_loss": round(sl, 6),
                "rr_ratio": round(rr_ratio, 2),
                "signal_type": signal_type,
                "level": round(level, 6)
            }
    
    # === STANDARD FORMATS ===
    patterns = [
        r'(BUY|SELL|LONG|SHORT)\s+([A-Z0-9]+)\s*@?\s*([\d.]+).*?TP[:\s]*([\d.]+).*?SL[:\s]*([\d.]+)',
        r'([A-Z0-9]+)\s+(BUY|SELL|LONG|SHORT).*?ENTRY[:\s]*([\d.]+).*?TP[:\s]*([\d.]+).*?SL[:\s]*([\d.]+)',
        r'(LONG|SHORT|BUY|SELL)\s+([A-Z0-9]+).*?ENTRY[:\s]*([\d.]+).*?TP[:\s]*([\d.]+).*?SL[:\s]*([\d.]+)',
        r'(LONG|SHORT|BUY|SELL)\s+([A-Z0-9]+)\s+([\d.]+)[\s\-]+([\d.]+)[\s\-]+([\d.]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_upper, re.IGNORECASE | re.DOTALL)
        if match:
            groups = match.groups()
            
            if groups[0] in ['BUY', 'SELL', 'LONG', 'SHORT']:
                direction = 'BUY' if groups[0] in ['BUY', 'LONG'] else 'SELL'
                symbol = groups[1]
                entry = float(groups[2])
                tp = float(groups[3])
                sl = float(groups[4])
            else:
                symbol = groups[0]
                direction = 'BUY' if groups[1] in ['BUY', 'LONG'] else 'SELL'
                entry = float(groups[2])
                tp = float(groups[3])
                sl = float(groups[4])
            
            if not symbol.endswith('USDT'):
                symbol = symbol + 'USDT'
            
            if direction == 'BUY':
                risk = entry - sl
                reward = tp - entry
            else:
                risk = sl - entry
                reward = entry - tp
            
            rr_ratio = reward / risk if risk > 0 else 0
            
            return {
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry,
                "take_profit": tp,
                "stop_loss": sl,
                "rr_ratio": round(rr_ratio, 2)
            }
    
    return None

async def get_market_data(symbol: str) -> dict:
    """Fetch market data from Binance Futures"""
    try:
        klines = binance_client.klines(symbol=symbol, interval='1h', limit=100)
        
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        df['close'] = pd.to_numeric(df['close'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['volume'] = pd.to_numeric(df['volume'])
        
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        df['ema20'] = ta.trend.EMAIndicator(df['close'], window=20).ema_indicator()
        df['ema50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
        
        current = df.iloc[-1]
        avg_volume = df['volume'].rolling(20).mean().iloc[-1]
        
        trend = "BULLISH" if current['ema20'] > current['ema50'] else "BEARISH"
        
        return {
            "current_price": float(current['close']),
            "rsi": float(current['rsi']) if pd.notna(current['rsi']) else 50,
            "trend": trend,
            "volume_ratio": float(current['volume'] / avg_volume) if avg_volume > 0 else 1,
        }
    except Exception as e:
        logger.error(f"Error fetching market data for {symbol}: {e}")
        return {}

async def analyze_with_ai(signal: dict, market_data: dict) -> dict:
    """Analyze signal with GPT-5.2"""
    try:
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        if not api_key:
            return {"decision": "SKIP", "reasoning": "API key not configured", "confidence": 0}
        
        settings = await db.settings.find_one({}, {"_id": 0})
        if not settings:
            settings = {"min_rr_ratio": 2.0, "min_volume_multiplier": 1.5, "trend_alignment_required": True}
        
        chat = LlmChat(
            api_key=api_key,
            session_id=f"auto-{signal.get('symbol', 'unknown')}-{datetime.now().timestamp()}",
            system_message="""Ты эксперт по криптотрейдингу. Анализируй сигналы кратко.
Отвечай ТОЛЬКО JSON: {"decision": "ACCEPT" или "REJECT", "confidence": 0-100, "reasoning": "1-2 предложения на русском"}"""
        ).with_model("openai", "gpt-5.2")
        
        prompt = f"""{signal['direction']} {signal['symbol']} @ {signal['entry_price']}
TP: {signal['take_profit']} | SL: {signal['stop_loss']} | R:R: {signal['rr_ratio']}
Market: Price {market_data.get('current_price', 'N/A')}, RSI {market_data.get('rsi', 50):.0f}, Trend {market_data.get('trend', 'N/A')}
Min R:R required: {settings.get('min_rr_ratio', 2.0)}. Quick verdict as JSON."""

        response = await chat.send_message(UserMessage(text=prompt))
        
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        return {"decision": "SKIP", "reasoning": "Parse error", "confidence": 0}
        
    except Exception as e:
        logger.error(f"AI error: {e}")
        return {"decision": "SKIP", "reasoning": str(e)[:50], "confidence": 0}

def format_result(signal: dict, market_data: dict, ai_result: dict) -> str:
    """Format analysis result for Telegram"""
    decision = ai_result.get('decision', 'SKIP')
    confidence = ai_result.get('confidence', 0)
    reasoning = ai_result.get('reasoning', 'N/A')
    
    if decision == 'ACCEPT':
        emoji, status = "✅", "ПРИНЯТ"
    elif decision == 'REJECT':
        emoji, status = "❌", "ОТКЛОНЁН"
    else:
        emoji, status = "⏸️", "ПРОПУЩЕН"
    
    trend_emoji = "📈" if market_data.get('trend') == 'BULLISH' else "📉"
    dir_emoji = "🟢 LONG" if signal['direction'] == 'BUY' else "🔴 SHORT"
    
    signal_type_text = ""
    if signal.get('signal_type') == 'support_breakout':
        signal_type_text = f"\n📉 Пробой поддержки ({signal.get('level', '')})"
    elif signal.get('signal_type') == 'resistance_breakout':
        signal_type_text = f"\n📈 Пробой сопротивления ({signal.get('level', '')})"
    
    # Safe number formatting
    try:
        rsi = float(market_data.get('rsi', 50))
        rsi_str = f"{rsi:.0f}"
    except:
        rsi_str = str(market_data.get('rsi', 'N/A'))
    
    try:
        vol = float(market_data.get('volume_ratio', 1))
        vol_str = f"{vol:.1f}x"
    except:
        vol_str = str(market_data.get('volume_ratio', 'N/A'))
    
    return f"""{emoji} <b>СИГНАЛ {status}</b>

{dir_emoji} <b>{signal['symbol']}</b>{signal_type_text}
├ Вход: <code>{signal['entry_price']}</code>
├ TP: <code>{signal['take_profit']}</code>
├ SL: <code>{signal['stop_loss']}</code>
└ R:R: <code>{signal['rr_ratio']}</code>

{trend_emoji} Рынок: RSI <code>{rsi_str}</code> | Объём <code>{vol_str}</code>

🤖 <b>AI ({confidence}%):</b> {reasoning}"""

async def send_to_users(text: str):
    """Send message to all registered users via bot"""
    if not bot:
        return
    
    # Get users from database
    users = await db.bot_users.find({}, {"_id": 0, "chat_id": 1}).to_list(100)
    
    for user in users:
        try:
            await bot.send_message(chat_id=user['chat_id'], text=text, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Failed to send to {user['chat_id']}: {e}")

async def process_signal(text: str):
    """Process incoming signal"""
    signal = parse_signal(text)
    if not signal:
        logger.info(f"Could not parse: {text[:50]}...")
        return
    
    logger.info(f"📊 New signal: {signal['direction']} {signal['symbol']}")
    
    # Get market data
    market_data = await get_market_data(signal['symbol'])
    
    # AI analysis
    ai_result = await analyze_with_ai(signal, market_data)
    
    # Save to database
    doc = {
        "id": f"auto-{datetime.now().timestamp()}",
        "original_text": text[:500],
        "symbol": signal['symbol'],
        "direction": signal['direction'],
        "entry_price": signal['entry_price'],
        "take_profit": signal['take_profit'],
        "stop_loss": signal['stop_loss'],
        "rr_ratio": signal['rr_ratio'],
        "status": "accepted" if ai_result.get('decision') == 'ACCEPT' else "rejected",
        "ai_analysis": ai_result,
        "market_data": market_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "auto_cvizor"
    }
    await db.signals.insert_one(doc)
    
    # Format and send
    result_text = format_result(signal, market_data, ai_result)
    await send_to_users(result_text)
    
    logger.info(f"✅ Signal processed: {ai_result.get('decision')}")

async def main():
    logger.info("🚀 Starting Auto Signal Monitor...")
    
    # Telethon client
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.start()
    
    me = await client.get_me()
    logger.info(f"✅ Logged in as: {me.first_name} (@{me.username})")
    
    # Get source entity
    try:
        source = await client.get_entity(f'@{SIGNAL_SOURCE}')
        logger.info(f"✅ Monitoring: {source.first_name} (@{SIGNAL_SOURCE})")
    except Exception as e:
        logger.error(f"❌ Cannot find @{SIGNAL_SOURCE}: {e}")
        return
    
    # Handler for new messages from cvizor_bot
    @client.on(events.NewMessage(from_users=source.id))
    async def handler(event):
        text = event.message.text or ""
        if text:
            logger.info(f"📨 New message from @{SIGNAL_SOURCE}")
            await process_signal(text)
    
    logger.info("👀 Waiting for signals...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
