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
from telegram import Update, Bot, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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
    """Parse trading signal from various cvizor.com formats"""
    text_upper = text.upper()
    original_text = text
    
    # === EXTRACT SYMBOL ===
    # Format: BINANCE:DEXEUSDT.P or #DEXEUSDT.P
    symbol_match = re.search(r'(?:BINANCE:|#)([A-Z0-9]+)(?:\.P)?', text_upper)
    if not symbol_match:
        symbol_match = re.search(r'#([A-Z0-9]+)', text_upper)
    
    if not symbol_match:
        return None
    
    symbol = symbol_match.group(1)
    if symbol.endswith('P'):
        symbol = symbol[:-1]
    if not symbol.endswith('USDT'):
        symbol = symbol + 'USDT'
    
    # === EXTRACT PRICE ===
    price_match = re.search(r'(?:ЦЕНА|PRICE)[:\s]*([\d.]+)', text_upper)
    if not price_match:
        # Try to find price at end
        all_nums = re.findall(r'(\d+\.?\d*)', original_text)
        price_candidates = [float(n) for n in all_nums if 0.0001 < float(n) < 100000]
        if price_candidates:
            price_match_val = price_candidates[-1]  # Last number is usually price
        else:
            return None
    else:
        price_match_val = float(price_match.group(1))
    
    price = price_match_val
    if price <= 0:
        return None
    
    # === DETERMINE DIRECTION ===
    direction = None
    signal_type = "unknown"
    
    # Check emojis and keywords
    if '🔻' in text or 'SHORT' in text_upper or 'ШОРТ' in text_upper:
        direction = 'SELL'
        signal_type = 'short_signal'
    elif '🟢' in text or '✅' in text or 'LONG' in text_upper or 'ЛОНГ' in text_upper or 'RAKETA' in text_upper:
        direction = 'BUY'
        signal_type = 'long_signal'
    elif '🟡' in text:
        # Yellow = breakout, determine by context
        if 'ПРОБОЙ СОПРОТИВЛЕН' in text_upper or 'RESISTANCE' in text_upper:
            direction = 'BUY'
            signal_type = 'resistance_breakout'
        elif 'ПРОБОЙ ПОДДЕРЖК' in text_upper or 'SUPPORT' in text_upper:
            direction = 'SELL'
            signal_type = 'support_breakout'
        else:
            direction = 'BUY'
            signal_type = 'breakout'
    elif 'ПРОБОЙ ПОДДЕРЖК' in text_upper:
        direction = 'SELL'
        signal_type = 'support_breakout'
    elif 'ПРОБОЙ СОПРОТИВЛЕН' in text_upper or 'ПРОБОЙ УРОВНЯ' in text_upper:
        direction = 'BUY'
        signal_type = 'resistance_breakout'
    elif '🟤' in text:
        # Brown = support breakout
        direction = 'SELL'
        signal_type = 'support_breakout'
    
    if not direction:
        # Try RSI context
        rsi_high = re.search(r'RSI\d*\s*(?:БОЛЬШЕ|>)\s*(?:ЧЕМ)?\s*(\d+)', text_upper)
        rsi_low = re.search(r'RSI\d*\s*(?:МЕНЬШЕ|<)\s*(?:ЧЕМ)?\s*(\d+)', text_upper)
        
        if rsi_high:
            rsi_val = int(rsi_high.group(1))
            if rsi_val >= 60:
                direction = 'SELL'
        elif rsi_low:
            rsi_val = int(rsi_low.group(1))
            if rsi_val <= 40:
                direction = 'BUY'
        
        if not direction:
            direction = 'BUY'
            signal_type = 'general'
    
    # === EXTRACT LEVELS FOR TP/SL ===
    support_match = re.search(r'(?:ПОДДЕРЖК|SUPPORT)[^\d]*(-?[\d.]+)%', text_upper)
    resistance_match = re.search(r'(?:СОПРОТИВЛЕН|RESISTANCE)[^\d]*(-?[\d.]+)%', text_upper)
    level_match = re.search(r'(?:ПРОБОЙ\s+(?:ПОДДЕРЖК|СОПРОТИВЛЕН|УРОВНЯ)\w*)\s*([\d.]+)', text_upper)
    
    # Calculate TP and SL
    if direction == 'BUY':
        if support_match:
            support_dist = abs(float(support_match.group(1)))
            sl = price * (1 - support_dist / 100 - 0.01)
        else:
            sl = price * 0.97
        
        if resistance_match:
            resist_dist = abs(float(resistance_match.group(1)))
            tp = price * (1 + resist_dist / 100 + 0.02)
        else:
            tp = price * 1.04
    else:
        if resistance_match:
            resist_dist = abs(float(resistance_match.group(1)))
            sl = price * (1 + resist_dist / 100 + 0.01)
        else:
            sl = price * 1.03
        
        if support_match:
            support_dist = abs(float(support_match.group(1)))
            tp = price * (1 - support_dist / 100 - 0.02)
        else:
            tp = price * 0.96
    
    # Use breakout level
    if level_match:
        level = float(level_match.group(1))
        if level > 0:
            if direction == 'BUY':
                sl = min(sl, level * 0.99)
            else:
                sl = max(sl, level * 1.01)
    
    # R:R
    if direction == 'BUY':
        risk = price - sl
        reward = tp - price
    else:
        risk = sl - price
        reward = price - tp
    
    rr_ratio = reward / risk if risk > 0 else 0
    
    return {
        "symbol": symbol,
        "direction": direction,
        "entry_price": round(price, 6),
        "take_profit": round(tp, 6),
        "stop_loss": round(sl, 6),
        "rr_ratio": round(rr_ratio, 2),
        "signal_type": signal_type
    }

async def get_market_data(symbol: str) -> dict:
    """Fetch market data from Binance Futures"""
    try:
        klines = binance_client.klines(symbol=symbol, interval='1h', limit=100)
        
        if not klines:
            logger.warning(f"No klines data for {symbol}")
            return {"current_price": 0, "rsi": 50, "trend": "UNKNOWN", "volume_ratio": 1}
        
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
        return {"current_price": 0, "rsi": 50, "trend": "UNKNOWN", "volume_ratio": 1}

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
            system_message="""Ты эксперт по криптотрейдингу. Анализируй сигналы кратко.
            
Отвечай ТОЛЬКО JSON: {"decision": "ACCEPT" или "REJECT", "confidence": 0-100, "reasoning": "1-2 предложения на русском"}"""
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
        return {"decision": "SKIP", "reasoning": "AI analysis failed", "confidence": 0}

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
# Main keyboard
main_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📋 Сигналы"), KeyboardButton("🎯 Вход")],
        [KeyboardButton("📈 Статистика")]
    ],
    resize_keyboard=True
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    chat_id = update.message.chat_id
    
    # Save user to database for notifications
    await db.bot_users.update_one(
        {"chat_id": chat_id},
        {"$set": {"chat_id": chat_id, "registered": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    
    await update.message.reply_text(
        "👋 <b>AI Signal Screener</b>\n\n"
        "🔔 Ты подписан на уведомления!\n\n"
        "💡 Перешли мне сигнал для анализа",
        parse_mode='HTML',
        reply_markup=main_keyboard
    )


async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent signal analysis"""
    signals = await db.signals.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(5).to_list(5)
    
    if not signals:
        await update.message.reply_text("📋 Нет сигналов пока", reply_markup=main_keyboard)
        return
    
    text = "📋 <b>ОБЗОР СИГНАЛОВ</b>\n\n"
    
    for s in signals:
        status_emoji = "✅" if s.get('status') == 'accepted' else "❌"
        dir_emoji = "🟢" if s.get('direction') == 'BUY' else "🔴"
        confidence = s.get('ai_analysis', {}).get('confidence', 0)
        
        text += f"{status_emoji} {dir_emoji} <b>{s.get('symbol', '?')}</b>\n"
        text += f"├ Вход: {s.get('entry_price', '?')} | R:R: {s.get('rr_ratio', '?')}\n"
        text += f"└ AI: {confidence}% | {s.get('status', '?').upper()}\n\n"
    
    text += "💡 Перешли сигнал для детального анализа"
    
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_keyboard)


async def entries_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show entry signals"""
    # Get active entry signals
    entries = await db.entry_signals.find(
        {"status": "OPEN"}, {"_id": 0}
    ).sort("triggered_at", -1).limit(10).to_list(10)
    
    if not entries:
        # Check for pending signals
        pending = await db.signals.count_documents({
            "status": "accepted",
            "entry_triggered": {"$ne": True}
        })
        
        text = "🎯 <b>СИГНАЛЫ ВХОДА</b>\n\n"
        text += "Нет активных сигналов входа\n\n"
        text += f"⏳ Ожидают входа: {pending} сигналов\n"
        text += "Уведомлю когда цена достигнет точки входа!"
        
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_keyboard)
        return
    
    text = "🎯 <b>АКТИВНЫЕ СИГНАЛЫ ВХОДА</b>\n\n"
    
    for e in entries:
        dir_emoji = "🟢 LONG" if e.get('direction') == 'BUY' else "🔴 SHORT"
        
        text += f"{dir_emoji} <b>{e.get('symbol', '?')}</b>\n"
        text += f"├ Вход: <code>{e.get('entry_price', '?')}</code>\n"
        text += f"├ TP: <code>{e.get('take_profit', '?')}</code>\n"
        text += f"├ SL: <code>{e.get('stop_loss', '?')}</code>\n"
        text += f"└ R:R: {e.get('rr_ratio', '?')}\n\n"
    
    # Show closed signals stats
    tp_count = await db.entry_signals.count_documents({"status": "TP_HIT"})
    sl_count = await db.entry_signals.count_documents({"status": "SL_HIT"})
    
    if tp_count + sl_count > 0:
        win_rate = (tp_count / (tp_count + sl_count)) * 100
        text += f"📊 Win Rate: {win_rate:.0f}% ({tp_count}W / {sl_count}L)"
    
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_keyboard)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show statistics"""
    total = await db.signals.count_documents({})
    accepted = await db.signals.count_documents({"status": "accepted"})
    rejected = await db.signals.count_documents({"status": "rejected"})
    
    entries_open = await db.entry_signals.count_documents({"status": "OPEN"})
    tp_hit = await db.entry_signals.count_documents({"status": "TP_HIT"})
    sl_hit = await db.entry_signals.count_documents({"status": "SL_HIT"})
    
    win_rate = (tp_hit / (tp_hit + sl_hit) * 100) if (tp_hit + sl_hit) > 0 else 0
    
    text = f"""📈 <b>СТАТИСТИКА</b>

📋 <b>Сигналы:</b>
├ Всего: {total}
├ Принято: {accepted}
└ Отклонено: {rejected}

🎯 <b>Входы:</b>
├ Открытые: {entries_open}
├ TP достигнут: {tp_hit} ✅
├ SL достигнут: {sl_hit} ❌
└ Win Rate: {win_rate:.0f}%"""

    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_keyboard)


async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle keyboard button presses"""
    text = update.message.text
    
    if text == "📋 Сигналы":
        await signals_command(update, context)
    elif text == "🎯 Вход":
        await entries_command(update, context)
    elif text == "📈 Статистика":
        await stats_command(update, context)
    else:
        # It's a signal to analyze
        await analyze_message(update, context)

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
        f"🔄 <b>Глубокий анализ {signal['symbol']}...</b>\n\n"
        f"📊 Собираю технические данные...\n"
        f"📰 Ищу новости...\n"
        f"🐦 Анализирую настроения...\n"
        f"🤖 AI обрабатывает...",
        parse_mode='HTML'
    )
    
    try:
        # Deep professional analysis
        analysis = await deep_analyze_signal(signal)
        
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
            "status": "accepted" if analysis.get('decision') == 'ACCEPT' else "rejected",
            "ai_analysis": analysis,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "telegram",
            "chat_id": update.message.chat_id
        }
        await db.signals.insert_one(doc)
        
        # Format and send result
        result_text = format_deep_analysis(signal, analysis)
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
    application.add_handler(CommandHandler("signals", signals_command))
    application.add_handler(CommandHandler("entries", entries_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.Regex(r'^(📋 Сигналы|🎯 Вход|📈 Статистика)$'), handle_buttons))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_message))
    application.add_handler(MessageHandler(filters.FORWARDED, analyze_message))
    
    # Start polling
    logger.info("Bot started! Waiting for messages...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
