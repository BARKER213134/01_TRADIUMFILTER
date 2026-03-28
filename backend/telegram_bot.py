#!/usr/bin/env python3
"""
Telegram Bot v3
Commands: /start, /signals, /entries, /stats
All signals come from Tradium auto-monitor — no manual analysis
"""

import os
import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[db_name]

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

main_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton("📋 Сигналы"), KeyboardButton("🎯 Вход"), KeyboardButton("📈 Статистика")]],
    resize_keyboard=True
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id

    await db.bot_users.update_one(
        {"chat_id": chat_id},
        {"$set": {"chat_id": chat_id, "registered": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )

    watching = await db.signals.count_documents({"status": "watching"})
    open_entries = await db.entry_signals.count_documents({"status": "OPEN"})

    await update.message.reply_text(
        f"📡 <b>Tradium Signal Monitor</b>\n\n"
        f"Мониторинг сигналов из Tradium.\n"
        f"Оповещения когда цена достигает DCA #4.\n\n"
        f"👀 Слежу за: <b>{watching}</b> сигналов\n"
        f"📊 Открытых: <b>{open_entries}</b> позиций",
        parse_mode='HTML',
        reply_markup=main_keyboard
    )


async def signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    signals = await db.signals.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(10).to_list(10)

    if not signals:
        await update.message.reply_text("📋 Нет сигналов", reply_markup=main_keyboard)
        return

    text = "📋 <b>СИГНАЛЫ</b>\n\n"

    for s in signals:
        status = s.get('status', 'watching')
        if status == 'watching':
            icon = "👀"
        elif status == 'entered':
            icon = "🎯"
        elif status == 'tp_hit':
            icon = "✅"
        elif status == 'sl_hit':
            icon = "❌"
        else:
            icon = "📋"

        dir_icon = "🟢" if s.get('direction') == 'LONG' else "🔴"
        dca4 = s.get('dca4_level', 'N/A')

        text += f"{icon} {dir_icon} <b>{s.get('symbol', '?')}</b> ({s.get('timeframe', '?')})\n"
        text += f"    DCA#4: <code>{dca4}</code> | TP: <code>{s.get('take_profit', '?')}</code> | SL: <code>{s.get('stop_loss', '?')}</code>\n\n"

    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_keyboard)


async def entries_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entries = await db.entry_signals.find(
        {"status": "OPEN"}, {"_id": 0}
    ).sort("triggered_at", -1).limit(10).to_list(10)

    watching = await db.signals.count_documents({"status": "watching", "dca4_level": {"$ne": None}})

    if not entries:
        text = "🎯 <b>СИГНАЛЫ ВХОДА</b>\n\n"
        text += "Нет активных позиций\n\n"
        text += f"⏳ Ожидают DCA #4: <b>{watching}</b> сигналов\n"
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_keyboard)
        return

    text = "🎯 <b>АКТИВНЫЕ ПОЗИЦИИ</b>\n\n"

    for e in entries:
        dir_icon = "🟢 LONG" if e.get('direction') == 'LONG' else "🔴 SHORT"

        text += f"{dir_icon} <b>{e.get('symbol', '?')}</b>\n"
        text += f"    Вход: <code>{e.get('entry_price', '?')}</code>\n"
        text += f"    TP: <code>{e.get('take_profit', '?')}</code>\n"
        text += f"    SL: <code>{e.get('stop_loss', '?')}</code>\n"
        text += f"    R:R: <code>{e.get('rr_ratio', '?')}</code>\n\n"

    tp_count = await db.entry_signals.count_documents({"status": "TP_HIT"})
    sl_count = await db.entry_signals.count_documents({"status": "SL_HIT"})

    if tp_count + sl_count > 0:
        win_rate = (tp_count / (tp_count + sl_count)) * 100
        text += f"\n📊 Win Rate: {win_rate:.0f}% ({tp_count}W / {sl_count}L)"

    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_keyboard)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = await db.signals.count_documents({})
    watching = await db.signals.count_documents({"status": "watching"})
    entered = await db.signals.count_documents({"status": "entered"})

    entries_open = await db.entry_signals.count_documents({"status": "OPEN"})
    tp_hit = await db.entry_signals.count_documents({"status": "TP_HIT"})
    sl_hit = await db.entry_signals.count_documents({"status": "SL_HIT"})

    win_rate = (tp_hit / (tp_hit + sl_hit) * 100) if (tp_hit + sl_hit) > 0 else 0

    text = f"""📈 <b>СТАТИСТИКА</b>

📋 <b>Сигналы:</b>
    Всего: {total}
    Слежу: {watching}
    Вход выполнен: {entered}

🎯 <b>Позиции:</b>
    Открытые: {entries_open}
    TP: {tp_hit} ✅
    SL: {sl_hit} ❌
    Win Rate: {win_rate:.0f}%"""

    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_keyboard)


async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📋 Сигналы":
        await signals_command(update, context)
    elif text == "🎯 Вход":
        await entries_command(update, context)
    elif text == "📈 Статистика":
        await stats_command(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📡 <b>Tradium Signal Monitor</b>\n\n"
        "Бот автоматически мониторит сигналы.\n"
        "Оповещение приходит когда цена\n"
        "достигает уровня DCA #4.\n\n"
        "📋 /signals — список сигналов\n"
        "🎯 /entries — открытые позиции\n"
        "📈 /stats — статистика",
        parse_mode='HTML',
        reply_markup=main_keyboard
    )


def main():
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return

    logger.info("Starting Telegram bot v3...")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("signals", signals_command))
    application.add_handler(CommandHandler("entries", entries_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.Regex(r'^(📋 Сигналы|🎯 Вход|📈 Статистика)$'), handle_buttons))

    logger.info("Bot started! Waiting for messages...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
