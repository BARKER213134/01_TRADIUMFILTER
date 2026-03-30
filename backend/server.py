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
from datetime import datetime, timezone
import asyncio
import re
import json

# Technical Analysis via CCXT (Kraken - works globally)
import ccxt
import pandas as pd
import ta

# AI Integration
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=True)


def is_preview_env() -> bool:
    """Detect if running in preview/agent environment (not production).
    Supervisor sets APP_URL — preview URLs contain 'preview.emergentagent.com'."""
    app_url = os.environ.get("APP_URL", "")
    return "preview.emergentagent.com" in app_url


IS_PREVIEW = is_preview_env()

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Exchange client (Kraken - works globally without restrictions)
exchange = ccxt.kraken({'enableRateLimit': True})

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state for bot
bot_state = {
    "is_running": False,
    "telethon_connected": False,
    "last_error": None
}

# ============ MODELS ============

class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    telegram_api_id: Optional[str] = None
    telegram_api_hash: Optional[str] = None
    telegram_phone: Optional[str] = None
    source_chat_id: Optional[str] = None  # Chat ID to read signals from
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

class Stats(BaseModel):
    total_signals: int
    accepted: int
    rejected: int
    pending: int
    win_rate: float
    avg_rr_ratio: float

# ============ HELPER FUNCTIONS ============

def parse_signal(text: str) -> Optional[Dict]:
    """Parse trading signal from various formats"""
    text = text.upper()
    
    # Common patterns
    patterns = [
        # Format: BUY BTCUSDT @ 95000, TP: 96000, SL: 94500
        r'(BUY|SELL|LONG|SHORT)\s+([A-Z0-9]+)\s*@?\s*([\d.]+).*?TP[:\s]*([\d.]+).*?SL[:\s]*([\d.]+)',
        # Format: BTCUSDT BUY Entry: 95000 TP: 96000 SL: 94500
        r'([A-Z0-9]+)\s+(BUY|SELL|LONG|SHORT).*?ENTRY[:\s]*([\d.]+).*?TP[:\s]*([\d.]+).*?SL[:\s]*([\d.]+)',
        # Format: LONG ADAUSDT Entry: 0.45 TP: 0.48 SL: 0.42
        r'(LONG|SHORT|BUY|SELL)\s+([A-Z0-9]+).*?ENTRY[:\s]*([\d.]+).*?TP[:\s]*([\d.]+).*?SL[:\s]*([\d.]+)',
        # Format: Signal: LONG BTCUSDT 95000-96000-94500
        r'(LONG|SHORT|BUY|SELL)\s+([A-Z0-9]+)\s+([\d.]+)[\s\-]+([\d.]+)[\s\-]+([\d.]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            groups = match.groups()
            
            # Determine order of groups based on pattern
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
            
            # Normalize symbol
            if not symbol.endswith('USDT'):
                symbol = symbol + 'USDT'
            
            # Calculate R:R ratio
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

async def get_market_data(symbol: str) -> Dict:
    """Fetch market data from Kraken/OKX via CCXT"""
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
            # Fallback to OKX
            try:
                okx = ccxt.okx({'enableRateLimit': True})
                klines = okx.fetch_ohlcv(f"{base}/USDT", '1h', limit=100)
            except:
                pass
        
        if not klines or len(klines) < 20:
            return {}
        
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        
        # Calculate indicators
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
            "bb_upper": float(current['bb_upper']) if pd.notna(current['bb_upper']) else 0,
            "bb_lower": float(current['bb_lower']) if pd.notna(current['bb_lower']) else 0,
            "macd": float(current['macd']) if pd.notna(current['macd']) else 0,
            "macd_signal": float(current['macd_signal']) if pd.notna(current['macd_signal']) else 0,
            "trend": trend,
            "current_volume": float(current['volume']),
            "avg_volume": float(avg_volume) if pd.notna(avg_volume) else 0,
            "volume_ratio": float(current['volume'] / avg_volume) if avg_volume > 0 else 1,
            "support": float(recent_low),
            "resistance": float(recent_high)
        }
    except Exception as e:
        logger.error(f"Error fetching market data for {symbol}: {e}")
        return {}

async def analyze_with_ai(signal: Dict, market_data: Dict, settings: Dict) -> Dict:
    """Analyze signal with GPT-5.2"""
    try:
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        if not api_key:
            return {"decision": "SKIP", "reasoning": "API key not configured"}
        
        chat = LlmChat(
            api_key=api_key,
            session_id=f"signal-{signal.get('symbol', 'unknown')}-{datetime.now().timestamp()}",
            system_message="""You are an expert crypto trading analyst. Analyze trading signals and provide recommendations.
            
You must respond ONLY with valid JSON in this exact format:
{
    "decision": "ACCEPT" or "REJECT",
    "confidence": 0-100,
    "reasoning": "Brief explanation",
    "technical_score": 0-100,
    "risk_score": 0-100,
    "key_factors": ["factor1", "factor2", "factor3"]
}"""
        ).with_model("openai", "gpt-5.2")
        
        prompt = f"""Analyze this trading signal:

SIGNAL:
- Symbol: {signal['symbol']}
- Direction: {signal['direction']}
- Entry: {signal['entry_price']}
- Take Profit: {signal['take_profit']}
- Stop Loss: {signal['stop_loss']}
- Risk/Reward: {signal['rr_ratio']}

MARKET DATA:
- Current Price: {market_data.get('current_price', 'N/A')}
- RSI: {market_data.get('rsi', 'N/A')}
- Trend (EMA20/50): {market_data.get('trend', 'N/A')}
- EMA20: {market_data.get('ema20', 'N/A')}
- EMA50: {market_data.get('ema50', 'N/A')}
- MACD: {market_data.get('macd', 'N/A')}
- MACD Signal: {market_data.get('macd_signal', 'N/A')}
- Bollinger Upper: {market_data.get('bb_upper', 'N/A')}
- Bollinger Lower: {market_data.get('bb_lower', 'N/A')}
- Volume Ratio: {market_data.get('volume_ratio', 'N/A')}x average
- Support: {market_data.get('support', 'N/A')}
- Resistance: {market_data.get('resistance', 'N/A')}

FILTER CRITERIA:
- Min R:R Ratio: {settings.get('min_rr_ratio', 2.0)}
- Min Volume Multiplier: {settings.get('min_volume_multiplier', 1.5)}
- Trend Alignment Required: {settings.get('trend_alignment_required', True)}

Evaluate:
1. Is R:R ratio acceptable?
2. Does direction align with trend?
3. Is volume sufficient?
4. Are RSI levels favorable (not overbought/oversold against direction)?
5. Is entry price reasonable relative to support/resistance?

Respond with JSON only."""

        response = await chat.send_message(UserMessage(text=prompt))
        
        # Parse JSON response
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        
        return {
            "decision": "SKIP",
            "reasoning": "Could not parse AI response",
            "raw_response": response[:500]
        }
        
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        return {"decision": "SKIP", "reasoning": str(e)}

async def send_telegram_message(text: str, chat_id: Optional[str] = None):
    """Send message via Telegram bot"""
    try:
        from telegram import Bot
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            logger.warning("Telegram bot token not configured")
            return
        
        bot = Bot(token=bot_token)
        
        # Get chat_id from settings if not provided
        if not chat_id:
            settings = await db.settings.find_one({}, {"_id": 0})
            if settings:
                chat_id = settings.get('destination_chat_id')
        
        if chat_id:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
            logger.info(f"Message sent to {chat_id}")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")

# ============ API ENDPOINTS ============

@api_router.get("/")
async def root():
    return {"message": "AI Trading Signal Screener API"}

# Settings endpoints
@api_router.get("/settings")
async def get_settings():
    settings = await db.settings.find_one({}, {"_id": 0})
    if not settings:
        # Return defaults
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
    
    return {"status": "success", "message": "Settings updated"}

# Signal endpoints
@api_router.get("/signals", response_model=List[Signal])
async def get_signals(
    status: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    query = {}
    if status:
        query["status"] = status
    
    signals = await db.signals.find(
        query, {"_id": 0}
    ).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    
    return signals

@api_router.get("/signals/stats")
async def get_stats():
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    total = await db.signals.count_documents({})
    accepted = await db.signals.count_documents({"status": "accepted"})
    rejected = await db.signals.count_documents({"status": "rejected"})
    pending = await db.signals.count_documents({"status": "pending"})
    
    today_total = await db.signals.count_documents({
        "timestamp": {"$gte": today_start.isoformat()}
    })
    today_accepted = await db.signals.count_documents({
        "status": "accepted",
        "timestamp": {"$gte": today_start.isoformat()}
    })
    today_rejected = await db.signals.count_documents({
        "status": "rejected", 
        "timestamp": {"$gte": today_start.isoformat()}
    })
    
    # Calculate average R:R for accepted signals
    pipeline = [
        {"$match": {"status": "accepted"}},
        {"$group": {"_id": None, "avg_rr": {"$avg": "$rr_ratio"}}}
    ]
    result = await db.signals.aggregate(pipeline).to_list(1)
    avg_rr = result[0]["avg_rr"] if result else 0
    
    win_rate = (accepted / total * 100) if total > 0 else 0
    
    return {
        "total_signals": total,
        "accepted": accepted,
        "rejected": rejected,
        "pending": pending,
        "win_rate": round(win_rate, 1),
        "avg_rr_ratio": round(avg_rr, 2) if avg_rr else 0,
        "today": {
            "total": today_total,
            "accepted": today_accepted,
            "rejected": today_rejected
        }
    }

@api_router.post("/signals/analyze")
async def analyze_signal(signal_input: SignalCreate):
    """Manually analyze a signal"""
    parsed = parse_signal(signal_input.text)
    if not parsed:
        raise HTTPException(status_code=400, detail="Could not parse signal format")
    
    # Get settings
    settings = await db.settings.find_one({}, {"_id": 0})
    if not settings:
        settings = Settings().model_dump()
    
    # Get market data
    market_data = await get_market_data(parsed['symbol'])
    
    # AI Analysis
    ai_result = await analyze_with_ai(parsed, market_data, settings)
    
    # Determine status
    status = "accepted" if ai_result.get("decision") == "ACCEPT" else "rejected"
    
    # Create signal record
    signal = Signal(
        original_text=signal_input.text,
        symbol=parsed['symbol'],
        direction=parsed['direction'],
        entry_price=parsed['entry_price'],
        take_profit=parsed['take_profit'],
        stop_loss=parsed['stop_loss'],
        rr_ratio=parsed['rr_ratio'],
        status=status,
        ai_analysis=ai_result,
        market_data=market_data
    )
    
    # Save to database
    doc = signal.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    await db.signals.insert_one(doc)
    
    return signal

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
    """Health check with worker status"""
    if IS_PREVIEW:
        db_ok = False
        try:
            await db.signals.count_documents({})
            db_ok = True
        except Exception:
            pass
        return {
            "status": "preview",
            "mode": "preview — workers disabled to avoid Telegram conflicts",
            "workers": {k: {"running": False, "status": v} for k, v in worker_status.items()},
            "db_connected": db_ok,
            "telethon_session": (ROOT_DIR / "telethon_session.session").exists(),
        }

    ws = {}
    for name, task in worker_tasks.items():
        ws[name] = {
            "running": not task.done(),
            "status": worker_status.get(name, "unknown")
        }

    db_ok = False
    try:
        await db.signals.count_documents({})
        db_ok = True
    except Exception:
        pass

    session_exists = (ROOT_DIR / "telethon_session.session").exists()

    return {
        "status": "ok" if all(not t.done() for t in worker_tasks.values()) else "degraded",
        "mode": "production",
        "workers": ws,
        "db_connected": db_ok,
        "telethon_session": session_exists,
    }

@api_router.get("/entries")
async def get_entries(status: Optional[str] = None, limit: int = 50):
    query = {}
    if status:
        query["status"] = status
    entries = await db.entry_signals.find(
        query, {"_id": 0}
    ).sort("triggered_at", -1).limit(limit).to_list(limit)
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
    return {
        "total_signals": total_signals,
        "watching": watching,
        "dca4_reached": dca4_reached,
        "entered": entered,
        "open": open_count,
        "tp_hit": tp_count,
        "sl_hit": sl_count,
        "win_rate": round(win_rate, 1)
    }

# Bot control endpoints
@api_router.get("/bot/status")
async def get_bot_status():
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    signals_today = await db.signals.count_documents({
        "timestamp": {"$gte": today_start.isoformat()}
    })
    accepted_today = await db.signals.count_documents({
        "status": "accepted",
        "timestamp": {"$gte": today_start.isoformat()}
    })
    rejected_today = await db.signals.count_documents({
        "status": "rejected",
        "timestamp": {"$gte": today_start.isoformat()}
    })
    
    return BotStatus(
        is_running=bot_state["is_running"],
        telethon_connected=bot_state["telethon_connected"],
        last_error=bot_state["last_error"],
        signals_today=signals_today,
        accepted_today=accepted_today,
        rejected_today=rejected_today
    )

@api_router.post("/bot/start")
async def start_bot(background_tasks: BackgroundTasks):
    """Start the signal monitoring bot"""
    if bot_state["is_running"]:
        return {"status": "already_running"}
    
    bot_state["is_running"] = True
    bot_state["last_error"] = None
    
    return {"status": "started", "message": "Bot monitoring started. Configure Telegram credentials in settings to enable live signal reading."}

@api_router.post("/bot/stop")
async def stop_bot():
    """Stop the signal monitoring bot"""
    bot_state["is_running"] = False
    bot_state["telethon_connected"] = False
    return {"status": "stopped"}

# Chart data endpoint
@api_router.get("/signals/chart/daily")
async def get_daily_chart_data(days: int = 7):
    """Get daily signal statistics for chart"""
    from datetime import timedelta
    
    data = []
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    for i in range(days - 1, -1, -1):
        day_start = today - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        
        total = await db.signals.count_documents({
            "timestamp": {
                "$gte": day_start.isoformat(),
                "$lt": day_end.isoformat()
            }
        })
        accepted = await db.signals.count_documents({
            "status": "accepted",
            "timestamp": {
                "$gte": day_start.isoformat(),
                "$lt": day_end.isoformat()
            }
        })
        
        data.append({
            "date": day_start.strftime("%m/%d"),
            "total": total,
            "accepted": accepted,
            "rejected": total - accepted
        })
    
    return data

# Chart image serving endpoint
@api_router.get("/charts/{filename}")
async def serve_chart(filename: str):
    """Serve chart image files"""
    charts_dir = ROOT_DIR / "charts"
    file_path = charts_dir / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Chart not found")
    return FileResponse(str(file_path), media_type="image/jpeg")


@api_router.get("/signals/{signal_id}/chart")
async def get_signal_chart(signal_id: str):
    """Get chart filename for a specific signal"""
    signal = await db.signals.find_one({"id": signal_id}, {"_id": 0, "chart_path": 1})
    if not signal or not signal.get("chart_path"):
        raise HTTPException(status_code=404, detail="Chart not found for this signal")
    chart_path = Path(signal["chart_path"])
    if not chart_path.exists():
        raise HTTPException(status_code=404, detail="Chart file missing")
    return {"filename": chart_path.name}


# Market data endpoint (for testing)
@api_router.get("/market/{symbol}")
async def get_market_info(symbol: str):
    """Get current market data for a symbol"""
    data = await get_market_data(symbol.upper())
    if not data:
        raise HTTPException(status_code=404, detail="Could not fetch market data")
    return data

# Include the router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Background workers management — run as asyncio tasks in-process
worker_tasks = {}
worker_status = {}


async def run_signal_monitor():
    """Run signal_monitor as in-process asyncio task"""
    while True:
        try:
            logger.info("🚀 Starting signal_monitor in-process...")
            worker_status["signal_monitor"] = "starting"
            from signal_monitor import main as sm_main
            worker_status["signal_monitor"] = "running"
            await sm_main()
        except Exception as e:
            logger.error(f"❌ signal_monitor crashed: {e}", exc_info=True)
            worker_status["signal_monitor"] = f"crashed: {e}"
        logger.warning("⚠️ signal_monitor exited, restarting in 5s...")
        await asyncio.sleep(5)


async def run_entry_monitor():
    """Run entry_monitor as in-process asyncio task"""
    while True:
        try:
            logger.info("🚀 Starting entry_monitor in-process...")
            worker_status["entry_monitor"] = "starting"
            from entry_monitor import main as em_main
            worker_status["entry_monitor"] = "running"
            await em_main()
        except Exception as e:
            logger.error(f"❌ entry_monitor crashed: {e}", exc_info=True)
            worker_status["entry_monitor"] = f"crashed: {e}"
        logger.warning("⚠️ entry_monitor exited, restarting in 5s...")
        await asyncio.sleep(5)


async def run_telegram_bot():
    """Run telegram_bot as in-process asyncio task using start() instead of run_polling()"""
    while True:
        try:
            logger.info("🚀 Starting telegram_bot in-process...")
            worker_status["telegram_bot"] = "starting"

            from telegram import Update
            from telegram.ext import Application, CommandHandler, MessageHandler, filters

            from telegram_bot import (
                start_command, help_command, signals_command, dca4_command,
                confirmed_command, results_command, BOT_TOKEN
            )

            if not BOT_TOKEN:
                logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
                worker_status["telegram_bot"] = "no token"
                await asyncio.sleep(30)
                continue

            application = Application.builder().token(BOT_TOKEN).build()

            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(CommandHandler("help", help_command))
            application.add_handler(CommandHandler("signals", signals_command))
            application.add_handler(CommandHandler("dca4", dca4_command))
            application.add_handler(CommandHandler("confirmed", confirmed_command))
            application.add_handler(CommandHandler("results", results_command))
            application.add_handler(MessageHandler(filters.Regex(r"📋 Tradium"), signals_command))
            application.add_handler(MessageHandler(filters.Regex(r"📍 DCA"), dca4_command))
            application.add_handler(MessageHandler(filters.Regex(r"⚡ Вход"), confirmed_command))
            application.add_handler(MessageHandler(filters.Regex(r"📊 Результат"), results_command))

            await application.initialize()
            await application.start()
            await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

            worker_status["telegram_bot"] = "running"
            logger.info("✅ Telegram bot polling started")

            # Keep alive
            while True:
                await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"❌ telegram_bot crashed: {e}", exc_info=True)
            worker_status["telegram_bot"] = f"crashed: {e}"

        logger.warning("⚠️ telegram_bot exited, restarting in 5s...")
        await asyncio.sleep(5)


@app.on_event("startup")
async def startup_workers():
    """Start all background workers as asyncio tasks — ONLY in production"""
    if IS_PREVIEW:
        logger.info("⚠️ PREVIEW environment detected — background workers DISABLED to avoid Telegram conflicts")
        worker_status["signal_monitor"] = "disabled (preview)"
        worker_status["entry_monitor"] = "disabled (preview)"
        worker_status["telegram_bot"] = "disabled (preview)"
        return

    logger.info(f"🚀 PRODUCTION mode — starting background workers from {ROOT_DIR}...")

    worker_tasks["signal_monitor"] = asyncio.create_task(run_signal_monitor())
    worker_tasks["entry_monitor"] = asyncio.create_task(run_entry_monitor())
    worker_tasks["telegram_bot"] = asyncio.create_task(run_telegram_bot())

    logger.info("✅ All workers started as asyncio tasks")


@app.on_event("shutdown")
async def shutdown_all():
    """Shutdown all workers and DB"""
    for name, task in worker_tasks.items():
        task.cancel()
        logger.info(f"Cancelled worker: {name}")
    client.close()
