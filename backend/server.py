from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import asyncio
import re
import json
import ccxt
import pandas as pd
import ta
from openai import AsyncOpenAI

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)

INSTANCE_ID = str(uuid.uuid4())[:8]
LEADER_TTL = 45

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

exchange = ccxt.kraken({'enableRateLimit': True})

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot_state = {"is_running": False, "telethon_connected": False, "last_error": None}

class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    telegram_api_id: Optional[str] = None
    telegram_api_hash: Optional[str] = None
    telegram_phone: Optional[str] = None
    source_chat_id: Optional[str] = None
    min_rr_ratio: float = 2.0
    min_volume_multiplier: float = 1.5
    trend_alignment_required: bool = True
    send_rejected: bool = False

class SettingsUpdate(BaseModel):
    telegram_api_id: Optional[str] = None
    telegram_api_hash: Optional[str] = None
    telegram_phone: Optional[str] = None
    source_chat_id: Optional[str] = None
    min_rr_ratio: Optional[float] = None
    min_volume_multiplier: Optional[float] = None
    trend_alignment_required: Optional[bool] = None
    send_rejected: Optional[bool] = None

class Signal(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_text: Optional[str] = ""
    symbol: str = ""
    direction: str = ""
    entry_price: float = 0
    take_profit: float = 0
    stop_loss: float = 0
    rr_ratio: float = 0
    timestamp: Optional[Any] = None
    status: str = "watching"
    dca4_level: Optional[float] = None
    timeframe: Optional[str] = None
    trend: Optional[str] = None
    ma_status: Optional[str] = None
    rsi_status: Optional[str] = None
    volume_1d: Optional[float] = None
    tp_pct: Optional[float] = None
    sl_pct: Optional[float] = None
    dca_data: Optional[Dict[str, Any]] = None
    chart_path: Optional[str] = None
    entry_triggered: Optional[bool] = False
    trigger_price: Optional[float] = None
    source: Optional[str] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    market_data: Optional[Dict[str, Any]] = None

class SignalCreate(BaseModel):
    text: str

class BotStatus(BaseModel):
    is_running: bool
    telethon_connected: bool
    last_error: Optional[str] = None
    signals_today: int = 0
    accepted_today: int = 0
    rejected_today: int = 0

async def get_market_data(symbol: str) -> Dict:
    try:
        base = symbol.replace("USDT", "").replace("PERP", "").upper()
        klines = None
        for sym in [f"{base}/USD", f"{base}/USDT"]:
            try:
                klines = exchange.fetch_ohlcv(sym, '1h', limit=100)
                if klines and len(klines) > 20:
                    break
            except:
                continue
        if not klines or len(klines) < 20:
            return {}
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
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

async def analyze_with_ai(signal: Dict, market_data: Dict, settings: Dict) -> Dict:
    try:
        api_key = os.environ.get('EMERGENT_LLM_KEY') or os.environ.get('OPENAI_API_KEY')
        if not api_key:
            return {"decision": "SKIP", "reasoning": "API key not configured"}
        client_ai = AsyncOpenAI(api_key=api_key)
        prompt = f"""Analyze this trading signal and respond ONLY with JSON:
Symbol: {signal.get('symbol')} | Direction: {signal.get('direction')}
Entry: {signal.get('entry_price')} | TP: {signal.get('take_profit')} | SL: {signal.get('stop_loss')}
R:R: {signal.get('rr_ratio')} | RSI: {market_data.get('rsi')} | Trend: {market_data.get('trend')}
Min R:R required: {settings.get('min_rr_ratio', 2.0)}

Respond with: {{"decision": "ACCEPT" or "REJECT", "confidence": 0-100, "reasoning": "brief"}}"""
        completion = await client_ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        response = completion.choices[0].message.content
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"decision": "SKIP", "reasoning": response[:200]}
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        return {"decision": "SKIP", "reasoning": str(e)}

async def send_telegram_message(text: str, chat_id: Optional[str] = None):
    try:
        from telegram import Bot
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            return
        bot = Bot(token=bot_token)
        if not chat_id:
            settings = await db.settings.find_one({}, {"_id": 0})
            if settings:
                chat_id = settings.get('destination_chat_id')
        if chat_id:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")

@api_router.get("/")
async def root():
    return {"message": "AI Trading Signal Screener API"}

@api_router.get("/settings")
async def get_settings():
    settings = await db.settings.find_one({}, {"_id": 0})
    if not settings:
        return Settings().model_dump()
    return settings

@api_router.post("/settings")
async def update_settings(settings: SettingsUpdate):
    current = await db.settings.find_one({})
    if current:
        update_data = {k: v for k, v in settings.model_dump().items() if v is not None}
        await db.settings.update_one({}, {"$set": update_data})
    else:
        await db.settings.insert_one(settings.model_dump())
    return {"status": "success"}

@api_router.get("/signals", response_model=List[Signal])
async def get_signals(status: Optional[str] = None, limit: int = 50, skip: int = 0):
    query = {}
    if status:
        query["status"] = status
    signals = await db.signals.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    return signals

@api_router.get("/signals/stats")
async def get_stats():
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    total = await db.signals.count_documents({})
    accepted = await db.signals.count_documents({"status": "accepted"})
    rejected = await db.signals.count_documents({"status": "rejected"})
    pending = await db.signals.count_documents({"status": "pending"})
    win_rate = (accepted / total * 100) if total > 0 else 0
    pipeline = [{"$match": {"status": "accepted"}}, {"$group": {"_id": None, "avg_rr": {"$avg": "$rr_ratio"}}}]
    result = await db.signals.aggregate(pipeline).to_list(1)
    avg_rr = result[0]["avg_rr"] if result else 0
    return {"total_signals": total, "accepted": accepted, "rejected": rejected, "pending": pending, "win_rate": round(win_rate, 1), "avg_rr_ratio": round(avg_rr, 2) if avg_rr else 0}

@api_router.get("/signals/{signal_id}")
async def get_signal(signal_id: str):
    signal = await db.signals.find_one({"id": signal_id}, {"_id": 0})
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return signal

@api_router.delete("/signals/{signal_id}")
async def delete_signal(signal_id: str):
    result = await db.signals.delete_one({"id": signal_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Signal not found")
    return {"status": "deleted", "id": signal_id}

@api_router.post("/signals/delete-batch")
async def delete_signals_batch(data: dict):
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    result = await db.signals.delete_many({"id": {"$in": ids}})
    return {"status": "deleted", "count": result.deleted_count}

@api_router.delete("/entries/{signal_id}")
async def delete_entry(signal_id: str):
    result = await db.entry_signals.delete_one({"signal_id": signal_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"status": "deleted", "id": signal_id}

@api_router.post("/entries/delete-batch")
async def delete_entries_batch(data: dict):
    ids = data.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    result = await db.entry_signals.delete_many({"signal_id": {"$in": ids}})
    return {"status": "deleted", "count": result.deleted_count}

@api_router.get("/health")
async def health_check():
    db_ok = False
    try:
        await db.signals.count_documents({})
        db_ok = True
    except Exception:
        pass
    ws = {}
    for name in ["signal_monitor", "entry_monitor", "telegram_bot"]:
        task = worker_tasks.get(name)
        ws[name] = {"running": task is not None and not task.done(), "status": worker_status.get(name, "standby")}
    return {
        "status": "leader" if is_leader else "standby",
        "instance_id": INSTANCE_ID,
        "is_leader": is_leader,
        "workers": ws,
        "db_connected": db_ok,
    }

@api_router.get("/entries")
async def get_entries(status: Optional[str] = None, limit: int = 50):
    query = {}
    if status:
        query["status"] = status
    entries = await db.entry_signals.find(query, {"_id": 0}).sort("triggered_at", -1).limit(limit).to_list(limit)
    return entries

@api_router.get("/entries/stats")
async def get_entries_stats():
    open_count = await db.entry_signals.count_documents({"status": "OPEN"})
    tp_count = await db.entry_signals.count_documents({"status": "TP_HIT"})
    sl_count = await db.entry_signals.count_documents({"status": "SL_HIT"})
    watching = await db.signals.count_documents({"status": "watching"})
    dca4_reached = await db.signals.count_documents({"status": "dca4_reached"})
    total_signals = await db.signals.count_documents({})
    entered = await db.signals.count_documents({"status": "entered"})
    win_rate = (tp_count / (tp_count + sl_count) * 100) if (tp_count + sl_count) > 0 else 0
    return {"total_signals": total_signals, "watching": watching, "dca4_reached": dca4_reached, "entered": entered, "open": open_count, "tp_hit": tp_count, "sl_hit": sl_count, "win_rate": round(win_rate, 1)}

@api_router.get("/bot/status")
async def get_bot_status():
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    signals_today = await db.signals.count_documents({"timestamp": {"$gte": today_start.isoformat()}})
    accepted_today = await db.signals.count_documents({"status": "accepted", "timestamp": {"$gte": today_start.isoformat()}})
    rejected_today = await db.signals.count_documents({"status": "rejected", "timestamp": {"$gte": today_start.isoformat()}})
    return BotStatus(is_running=bot_state["is_running"], telethon_connected=bot_state["telethon_connected"], last_error=bot_state["last_error"], signals_today=signals_today, accepted_today=accepted_today, rejected_today=rejected_today)

@api_router.post("/bot/start")
async def start_bot():
    bot_state["is_running"] = True
    bot_state["last_error"] = None
    return {"status": "started"}

@api_router.post("/bot/stop")
async def stop_bot():
    bot_state["is_running"] = False
    return {"status": "stopped"}

@api_router.get("/signals/chart/daily")
async def get_daily_chart_data(days: int = 7):
    data = []
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(days - 1, -1, -1):
        day_start = today - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        total = await db.signals.count_documents({"timestamp": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}})
        accepted = await db.signals.count_documents({"status": "accepted", "timestamp": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}})
        data.append({"date": day_start.strftime("%m/%d"), "total": total, "accepted": accepted, "rejected": total - accepted})
    return data

@api_router.get("/charts/{filename}")
async def serve_chart(filename: str):
    charts_dir = ROOT_DIR / "charts"
    file_path = charts_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Chart not found")
    return FileResponse(str(file_path), media_type="image/jpeg")

@api_router.get("/market/{symbol}")
async def get_market_info(symbol: str):
    data = await get_market_data(symbol.upper())
    if not data:
        raise HTTPException(status_code=404, detail="Could not fetch market data")
    return data

refresh_lock = asyncio.Lock()

@api_router.post("/signals/refresh")
async def refresh_signals():
    if refresh_lock.locked():
        return {"status": "busy", "message": "Обновление уже идёт"}
    async with refresh_lock:
        try:
            from telethon import TelegramClient
            from signal_monitor import parse_tradium_signal, CHARTS_DIR
            api_id = int(os.environ.get('TELEGRAM_API_ID', 0))
            api_hash = os.environ.get('TELEGRAM_API_HASH', '')
            source_session = ROOT_DIR / 'telethon_session.session'
            if not source_session.exists():
                return {"status": "error", "message": "Telethon сессия не найдена"}
            channel_id = int(os.environ.get('TRADIUM_CHANNEL_ID', '-1002423680272'))
            topic_id = int(os.environ.get('TRADIUM_TOPIC_ID', '3204'))
            import shutil
            tmp_session = ROOT_DIR / 'refresh_session'
            shutil.copy2(str(source_session), str(tmp_session) + '.session')
            tg_client = TelegramClient(str(tmp_session), api_id, api_hash)
            await tg_client.connect()
            if not await tg_client.is_user_authorized():
                await tg_client.disconnect()
                return {"status": "error", "message": "Telethon не авторизован"}
            entity = await tg_client.get_entity(channel_id)
            messages = await tg_client.get_messages(entity, limit=50, reply_to=topic_id)
            added = 0
            skipped = 0
            added_symbols = []
            for msg in messages:
                text = msg.text or ""
                if '#сетап' not in text:
                    continue
                parsed = parse_tradium_signal(text)
                if not parsed:
                    continue
                existing = await db.signals.find_one({"symbol": parsed['symbol'], "direction": parsed['direction'], "entry_price": parsed['entry_price']})
                if existing:
                    skipped += 1
                    continue
                doc = {"id": f"tradium-refresh-{msg.id}", "original_text": text[:1000], "symbol": parsed['symbol'], "direction": parsed['direction'], "entry_price": parsed['entry_price'], "take_profit": parsed.get('take_profit', 0), "stop_loss": parsed.get('stop_loss', 0), "rr_ratio": parsed.get('rr_ratio', 0), "timeframe": parsed.get('timeframe', '4h'), "status": "watching", "entry_triggered": False, "timestamp": msg.date.isoformat() if msg.date else datetime.now(timezone.utc).isoformat(), "source": "tradium-refresh"}
                await db.signals.insert_one(doc)
                added += 1
                added_symbols.append(f"{parsed['direction']} {parsed['symbol']}")
            await tg_client.disconnect()
            for ext in ['.session', '.session-journal']:
                p = ROOT_DIR / f'refresh_session{ext}'
                if p.exists():
                    p.unlink()
            return {"status": "ok", "added": added, "skipped": skipped, "added_symbols": added_symbols, "message": f"Добавлено: {added}, пропущено: {skipped}"}
        except Exception as e:
            logger.error(f"Refresh error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','), allow_methods=["*"], allow_headers=["*"])

worker_tasks = {}
worker_status = {}
is_leader = False

async def start_workers():
    global is_leader
    is_leader = True
    logger.info(f"Instance {INSTANCE_ID} starting workers...")
    worker_tasks["signal_monitor"] = asyncio.create_task(run_signal_monitor())
    worker_tasks["entry_monitor"] = asyncio.create_task(run_entry_monitor())
    worker_tasks["telegram_bot"] = asyncio.create_task(run_telegram_bot())

async def run_signal_monitor():
    while True:
        try:
            worker_status["signal_monitor"] = "starting"
            from signal_monitor import main as sm_main
            worker_status["signal_monitor"] = "running"
            await sm_main()
        except Exception as e:
            worker_status["signal_monitor"] = f"crashed: {e}"
            await asyncio.sleep(5)

async def run_entry_monitor():
    while True:
        try:
            worker_status["entry_monitor"] = "starting"
            from entry_monitor import main as em_main
            worker_status["entry_monitor"] = "running"
            await em_main()
        except Exception as e:
            worker_status["entry_monitor"] = f"crashed: {e}"
            await asyncio.sleep(5)

async def run_telegram_bot():
    while True:
        try:
            worker_status["telegram_bot"] = "starting"
            from telegram import Update
            from telegram.ext import Application, CommandHandler, MessageHandler, filters
            from telegram_bot import start_command, help_command, signals_command, dca4_command, confirmed_command, results_command, BOT_TOKEN
            if not BOT_TOKEN:
                worker_status["telegram_bot"] = "no token"
                await asyncio.sleep(30)
                continue
            application = Application.builder().token(BOT_TOKEN).build()
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(CommandHandler("signals", signals_command))
            application.add_handler(CommandHandler("dca4", dca4_command))
            application.add_handler(CommandHandler("confirmed", confirmed_command))
            application.add_handler(CommandHandler("results", results_command))
            await application.initialize()
            await application.start()
            await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            worker_status["telegram_bot"] = "running"
            while True:
                await asyncio.sleep(60)
        except Exception as e:
            worker_status["telegram_bot"] = f"crashed: {e}"
            await asyncio.sleep(5)

@app.on_event("startup")
async def startup_workers():
    asyncio.create_task(start_workers())

@app.on_event("shutdown")
async def shutdown_all():
    for name, task in list(worker_tasks.items()):
        task.cancel()
    client.close()
