#!/usr/bin/env python3
"""
Telegram Bot for Signal Analysis
Receives forwarded messages, analyzes them with AI, and sends results back
"""

import asyncio
import os
import re
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
db_name = os.environ.get('DB_NAME', 'test_database')
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[db_name]

# Binance client
binance_client = UMFutures()

# Bot token
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

def parse_signal(text: str) -> dict | None:
    """Parse trading signal from various formats including cvizor.com breakout signals"""
    text_upper = text.upper()
    original_text = text
    
    # === CVIZOR.COM BREAKOUT FORMAT ===
    # Example: #SKYUSDT.P ПРОБОЙ ПОДДЕРЖКИ 0.0702, Цена 0.07016
    
    # Extract symbol from hashtag (e.g., #SKYUSDT.P -> SKYUSDT)
    symbol_match = re.search(r'#([A-Z0-9]+)(?:\.P)?', text_upper)
    
    # Check for breakout signals (ПРОБОЙ)
    if 'ПРОБОЙ' in text_upper or 'BREAKOUT' in text_upper or 'BREAK' in text_upper:
        # Determine direction based on support/resistance
        if 'ПОДДЕРЖК' in text_upper or 'SUPPORT' in text_upper:
            direction = 'SELL'  # Support breakout = SHORT
            signal_type = 'support_breakout'
        elif 'СОПРОТИВЛЕН' in text_upper or 'RESISTANCE' in text_upper:
            direction = 'BUY'  # Resistance breakout = LONG
            signal_type = 'resistance_breakout'
        else:
            direction = 'BUY'  # Default
            signal_type = 'breakout'
        
        # Find all decimal numbers in the text (format: 0.0702, 0.07016)
        all_numbers = re.findall(r'(\d+\.\d+)', original_text)
        all_numbers = [float(n) for n in all_numbers]
        
        # Filter to reasonable price values (exclude years, percentages etc)
        price_numbers = [n for n in all_numbers if 0.0001 < n < 100000]
        
        if symbol_match and len(price_numbers) >= 2:
            symbol = symbol_match.group(1)
            if symbol.endswith('P'):
                symbol = symbol[:-1]  # Remove trailing P
            if not symbol.endswith('USDT'):
                symbol = symbol + 'USDT'
            
            # First number is usually the level, second is current price
            level = price_numbers[0]
            price = price_numbers[1] if len(price_numbers) > 1 else level
            
            entry = price
            # Auto-calculate TP/SL based on breakout (2% move)
            move_pct = 0.02
            if direction == 'SELL':
                tp = entry * (1 - move_pct * 2)  # 4% down
                sl = level * 1.01  # Just above broken level
            else:
                tp = entry * (1 + move_pct * 2)  # 4% up
                sl = level * 0.99  # Just below broken level
            
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
        # Format: BUY BTCUSDT @ 95000, TP: 96000, SL: 94500
        r'(BUY|SELL|LONG|SHORT)\s+([A-Z0-9]+)\s*@?\s*([\d.]+).*?TP[:\s]*([\d.]+).*?SL[:\s]*([\d.]+)',
        # Format: BTCUSDT BUY Entry: 95000 TP: 96000 SL: 94500
        r'([A-Z0-9]+)\s+(BUY|SELL|LONG|SHORT).*?ENTRY[:\s]*([\d.]+).*?TP[:\s]*([\d.]+).*?SL[:\s]*([\d.]+)',
        # Format: LONG ADAUSDT Entry: 0.45 TP: 0.48 SL: 0.42
        r'(LONG|SHORT|BUY|SELL)\s+([A-Z0-9]+).*?ENTRY[:\s]*([\d.]+).*?TP[:\s]*([\d.]+).*?SL[:\s]*([\d.]+)',
        # Format: Signal: LONG BTCUSDT 95000-96000-94500
        r'(LONG|SHORT|BUY|SELL)\s+([A-Z0-9]+)\s+([\d.]+)[\s\-]+([\d.]+)[\s\-]+([\d.]+)',
        # Simpler format: BTCUSDT LONG 95000 TP 96000 SL 94500
        r'([A-Z0-9]+)\s+(LONG|SHORT|BUY|SELL)\s+([\d.]+).*?TP\s*([\d.]+).*?SL\s*([\d.]+)',
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
        
        bb = ta.volatility.BollingerBands(df['close'], window=20)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_lower'] = bb.bollinger_lband()
        
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        
        current = df.iloc[-1]
        avg_volume = df['volume'].rolling(20).mean().iloc[-1]
        
        trend = "BULLISH" if current['ema20'] > current['ema50'] else "BEARISH"
        recent_high = df['high'].tail(20).max()
        recent_low = df['low'].tail(20).min()
        
        return {
            "current_price": float(current['close']),
            "rsi": float(current['rsi']) if pd.notna(current['rsi']) else 50,
            "ema20": float(current['ema20']) if pd.notna(current['ema20']) else 0,
            "ema50": float(current['ema50']) if pd.notna(current['ema50']) else 0,
            "trend": trend,
            "volume_ratio": float(current['volume'] / avg_volume) if avg_volume > 0 else 1,
            "support": float(recent_low),
            "resistance": float(recent_high)
        }
    except Exception as e:
        logger.error(f"Error fetching market data for {symbol}: {e}")
        return {}

async def analyze_with_ai(signal: dict, market_data: dict) -> dict:
    """Analyze signal with GPT-5.2"""
    try:
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        if not api_key:
            return {"decision": "SKIP", "reasoning": "API key not configured"}
        
        # Get settings from DB
        settings = await db.settings.find_one({}, {"_id": 0})
        if not settings:
            settings = {"min_rr_ratio": 2.0, "min_volume_multiplier": 1.5, "trend_alignment_required": True}
        
        chat = LlmChat(
            api_key=api_key,
            session_id=f"tg-signal-{signal.get('symbol', 'unknown')}-{datetime.now().timestamp()}",
            system_message="""You are an expert crypto trading analyst. Analyze trading signals and provide recommendations.
            
You must respond ONLY with valid JSON in this exact format:
{
    "decision": "ACCEPT" or "REJECT",
    "confidence": 0-100,
    "reasoning": "Brief explanation in 1-2 sentences",
    "key_factors": ["factor1", "factor2"]
}"""
        ).with_model("openai", "gpt-5.2")
        
        prompt = f"""Analyze this trading signal:

SIGNAL: {signal['direction']} {signal['symbol']}
Entry: {signal['entry_price']} | TP: {signal['take_profit']} | SL: {signal['stop_loss']}
R:R Ratio: {signal['rr_ratio']}

MARKET:
Price: {market_data.get('current_price', 'N/A')} | RSI: {market_data.get('rsi', 'N/A'):.1f}
Trend: {market_data.get('trend', 'N/A')} | Volume: {market_data.get('volume_ratio', 1):.1f}x avg

RULES: Min R:R {settings.get('min_rr_ratio', 2.0)}, Trend align: {settings.get('trend_alignment_required', True)}

Quick analysis - respond with JSON only."""

        response = await chat.send_message(UserMessage(text=prompt))
        
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        
        return {"decision": "SKIP", "reasoning": "Could not parse AI response"}
        
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        return {"decision": "SKIP", "reasoning": str(e)}

def format_result(signal: dict, market_data: dict, ai_result: dict) -> str:
    """Format analysis result for Telegram"""
    decision = ai_result.get('decision', 'SKIP')
    confidence = ai_result.get('confidence', 0)
    reasoning = ai_result.get('reasoning', 'No analysis available')
    
    if decision == 'ACCEPT':
        emoji = "✅"
        status = "ПРИНЯТ"
    elif decision == 'REJECT':
        emoji = "❌"
        status = "ОТКЛОНЁН"
    else:
        emoji = "⏸️"
        status = "ПРОПУЩЕН"
    
    trend_emoji = "📈" if market_data.get('trend') == 'BULLISH' else "📉"
    direction_emoji = "🟢 LONG" if signal['direction'] == 'BUY' else "🔴 SHORT"
    
    # Check for breakout signal type
    signal_type_text = ""
    if signal.get('signal_type'):
        if signal['signal_type'] == 'support_breakout':
            signal_type_text = "\n📉 Пробой поддержки"
        elif signal['signal_type'] == 'resistance_breakout':
            signal_type_text = "\n📈 Пробой сопротивления"
        if signal.get('level'):
            signal_type_text += f" ({signal['level']})"
    
    # Safe formatting for market data
    current_price = market_data.get('current_price', 'N/A')
    rsi = market_data.get('rsi', 50)
    trend = market_data.get('trend', 'N/A')
    volume_ratio = market_data.get('volume_ratio', 1)
    
    # Convert to float if needed
    try:
        rsi_str = f"{float(rsi):.1f}"
    except:
        rsi_str = str(rsi)
    
    try:
        vol_str = f"{float(volume_ratio):.1f}x"
    except:
        vol_str = str(volume_ratio)
    
    msg = f"""{emoji} <b>СИГНАЛ {status}</b>

{direction_emoji} <b>{signal['symbol']}</b>{signal_type_text}
├ Вход: <code>{signal['entry_price']}</code>
├ TP: <code>{signal['take_profit']}</code>
├ SL: <code>{signal['stop_loss']}</code>
└ R:R: <code>{signal['rr_ratio']}</code>

{trend_emoji} <b>Рынок:</b>
├ Цена: <code>{current_price}</code>
├ RSI: <code>{rsi_str}</code>
├ Тренд: {trend}
└ Объём: <code>{vol_str}</code>

🤖 <b>AI ({confidence}%):</b>
{reasoning}"""
    return msg.strip()

# Bot handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "👋 Привет! Я анализирую торговые сигналы с помощью AI.\n\n"
        "📨 <b>Как использовать:</b>\n"
        "Просто перешли мне сообщение с сигналом, и я проанализирую его.\n\n"
        "📝 <b>Поддерживаемые форматы:</b>\n"
        "<code>BUY BTCUSDT @ 95000, TP: 96000, SL: 94500</code>\n"
        "<code>LONG ETHUSDT Entry: 3200 TP: 3400 SL: 3100</code>\n\n"
        "🔍 Я проверю R:R ratio, тренд, RSI и объёмы через Binance.",
        parse_mode='HTML'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_text(
        "🔍 <b>AI Signal Screener</b>\n\n"
        "Перешли мне сигнал — я проанализирую:\n"
        "• Risk/Reward ratio\n"
        "• Соответствие тренду\n"
        "• RSI (перекупленность/перепроданность)\n"
        "• Объёмы торгов\n\n"
        "И скажу: принять или отклонить сделку.",
        parse_mode='HTML'
    )

async def analyze_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages with signals"""
    text = update.message.text or update.message.caption or ""
    
    if not text:
        return
    
    # Parse signal
    signal = parse_signal(text)
    
    if not signal:
        await update.message.reply_text(
            "⚠️ Не удалось распознать сигнал.\n\n"
            "Убедитесь, что сообщение содержит:\n"
            "• Направление (BUY/SELL/LONG/SHORT)\n"
            "• Символ (BTCUSDT, ETHUSDT...)\n"
            "• Цену входа, TP и SL",
            parse_mode='HTML'
        )
        return
    
    # Send "analyzing" message
    processing_msg = await update.message.reply_text(
        f"🔄 Анализирую <b>{signal['symbol']}</b>...",
        parse_mode='HTML'
    )
    
    try:
        # Get market data
        market_data = await get_market_data(signal['symbol'])
        
        # AI analysis
        ai_result = await analyze_with_ai(signal, market_data)
        
        # Save to database
        doc = {
            "id": f"tg-{update.message.message_id}",
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
            "source": "telegram",
            "chat_id": update.message.chat_id
        }
        await db.signals.insert_one(doc)
        
        # Format and send result
        result_text = format_result(signal, market_data, ai_result)
        await processing_msg.edit_text(result_text, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error analyzing signal: {e}")
        await processing_msg.edit_text(
            f"❌ Ошибка анализа: {str(e)[:100]}",
            parse_mode='HTML'
        )

def main():
    """Start the bot"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    logger.info("Starting Telegram bot...")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_message))
    application.add_handler(MessageHandler(filters.FORWARDED, analyze_message))
    
    # Start polling
    logger.info("Bot started! Waiting for messages...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
