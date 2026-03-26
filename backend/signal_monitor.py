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

# Import professional analyzer
from pro_analyzer import deep_analyze_signal, format_deep_analysis

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

# Import parse_signal from telegram_bot
from telegram_bot import parse_signal


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
    """Process incoming signal with deep analysis"""
    signal = parse_signal(text)
    if not signal:
        logger.info(f"Could not parse: {text[:50]}...")
        return
    
    logger.info(f"📊 New signal: {signal['direction']} {signal['symbol']}")
    
    # Deep professional analysis (news, sentiment, technicals)
    analysis = await deep_analyze_signal(signal)
    
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
        "status": "accepted" if analysis.get('decision') == 'ACCEPT' else "rejected",
        "ai_analysis": analysis,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "auto_cvizor"
    }
    await db.signals.insert_one(doc)
    
    # Format and send
    result_text = format_deep_analysis(signal, analysis)
    await send_to_users(result_text)
    
    logger.info(f"✅ Signal processed: {analysis.get('decision')}")

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
