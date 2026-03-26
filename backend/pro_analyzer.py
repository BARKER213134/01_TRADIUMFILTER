#!/usr/bin/env python3
"""
Professional Signal Analyzer
Deep analysis: news, social sentiment, technical analysis, on-chain data
"""

import asyncio
import os
import re
import json
import logging
import aiohttp
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from binance.um_futures import UMFutures
import pandas as pd
import ta
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logger = logging.getLogger(__name__)

# Binance client
binance_client = UMFutures()


async def search_web(query: str) -> str:
    """Search web for news and sentiment"""
    try:
        async with aiohttp.ClientSession() as session:
            # Use DuckDuckGo HTML search (no API key needed)
            url = f"https://html.duckduckgo.com/html/?q={query}"
            headers = {"User-Agent": "Mozilla/5.0"}
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    # Extract snippets
                    snippets = re.findall(r'class="result__snippet">(.*?)</a>', text, re.DOTALL)
                    results = []
                    for s in snippets[:5]:
                        clean = re.sub(r'<[^>]+>', '', s).strip()
                        if clean:
                            results.append(clean)
                    return " | ".join(results)[:1500]
    except Exception as e:
        logger.error(f"Web search error: {e}")
    return ""


async def get_crypto_news(symbol: str) -> str:
    """Get latest news about the crypto"""
    coin = symbol.replace("USDT", "").replace("PERP", "")
    query = f"{coin} crypto news today"
    return await search_web(query)


async def get_social_sentiment(symbol: str) -> str:
    """Get Twitter/social sentiment"""
    coin = symbol.replace("USDT", "").replace("PERP", "")
    query = f"{coin} crypto twitter sentiment"
    return await search_web(query)


def get_advanced_technicals(symbol: str) -> dict:
    """Get comprehensive technical analysis"""
    try:
        # Get multiple timeframes
        klines_1h = binance_client.klines(symbol=symbol, interval='1h', limit=100)
        klines_4h = binance_client.klines(symbol=symbol, interval='4h', limit=100)
        klines_1d = binance_client.klines(symbol=symbol, interval='1d', limit=50)
        
        def analyze_tf(klines, tf_name):
            if not klines:
                return {}
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            # RSI
            rsi = ta.momentum.RSIIndicator(df['close'], window=14).rsi().iloc[-1]
            
            # MACD
            macd = ta.trend.MACD(df['close'])
            macd_line = macd.macd().iloc[-1]
            macd_signal = macd.macd_signal().iloc[-1]
            macd_hist = macd.macd_diff().iloc[-1]
            
            # Bollinger Bands
            bb = ta.volatility.BollingerBands(df['close'], window=20)
            bb_upper = bb.bollinger_hband().iloc[-1]
            bb_lower = bb.bollinger_lband().iloc[-1]
            bb_mid = bb.bollinger_mavg().iloc[-1]
            
            # EMAs
            ema9 = ta.trend.EMAIndicator(df['close'], window=9).ema_indicator().iloc[-1]
            ema21 = ta.trend.EMAIndicator(df['close'], window=21).ema_indicator().iloc[-1]
            ema50 = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator().iloc[-1]
            ema200 = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator().iloc[-1] if len(df) >= 200 else None
            
            # ATR (volatility)
            atr = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range().iloc[-1]
            
            # Volume analysis
            vol_sma = df['volume'].rolling(20).mean().iloc[-1]
            vol_ratio = df['volume'].iloc[-1] / vol_sma if vol_sma > 0 else 1
            
            # Stochastic RSI
            stoch = ta.momentum.StochRSIIndicator(df['close'])
            stoch_k = stoch.stochrsi_k().iloc[-1]
            stoch_d = stoch.stochrsi_d().iloc[-1]
            
            # Support/Resistance
            recent_high = df['high'].tail(20).max()
            recent_low = df['low'].tail(20).min()
            
            # Price position
            current_price = df['close'].iloc[-1]
            price_change_24h = ((current_price - df['close'].iloc[-24]) / df['close'].iloc[-24] * 100) if len(df) >= 24 else 0
            
            # Trend determination
            if ema9 > ema21 > ema50:
                trend = "STRONG_BULLISH"
            elif ema9 > ema21:
                trend = "BULLISH"
            elif ema9 < ema21 < ema50:
                trend = "STRONG_BEARISH"
            elif ema9 < ema21:
                trend = "BEARISH"
            else:
                trend = "NEUTRAL"
            
            return {
                "timeframe": tf_name,
                "price": round(current_price, 6),
                "price_change_24h": round(price_change_24h, 2),
                "trend": trend,
                "rsi": round(rsi, 1) if pd.notna(rsi) else 50,
                "macd": round(macd_line, 6) if pd.notna(macd_line) else 0,
                "macd_signal": round(macd_signal, 6) if pd.notna(macd_signal) else 0,
                "macd_histogram": round(macd_hist, 6) if pd.notna(macd_hist) else 0,
                "bb_upper": round(bb_upper, 6) if pd.notna(bb_upper) else 0,
                "bb_lower": round(bb_lower, 6) if pd.notna(bb_lower) else 0,
                "bb_position": "ABOVE" if current_price > bb_upper else ("BELOW" if current_price < bb_lower else "INSIDE"),
                "ema9": round(ema9, 6) if pd.notna(ema9) else 0,
                "ema21": round(ema21, 6) if pd.notna(ema21) else 0,
                "ema50": round(ema50, 6) if pd.notna(ema50) else 0,
                "ema200": round(ema200, 6) if ema200 and pd.notna(ema200) else None,
                "atr": round(atr, 6) if pd.notna(atr) else 0,
                "volume_ratio": round(vol_ratio, 2),
                "stoch_k": round(stoch_k * 100, 1) if pd.notna(stoch_k) else 50,
                "stoch_d": round(stoch_d * 100, 1) if pd.notna(stoch_d) else 50,
                "support": round(recent_low, 6),
                "resistance": round(recent_high, 6)
            }
        
        return {
            "1h": analyze_tf(klines_1h, "1H"),
            "4h": analyze_tf(klines_4h, "4H"),
            "1d": analyze_tf(klines_1d, "1D")
        }
        
    except Exception as e:
        logger.error(f"Technical analysis error for {symbol}: {e}")
        return {}


async def deep_analyze_signal(signal: dict) -> dict:
    """
    Professional-grade signal analysis
    Combines: Technical Analysis, News, Social Sentiment
    """
    symbol = signal['symbol']
    
    # Gather all data in parallel
    news_task = asyncio.create_task(get_crypto_news(symbol))
    sentiment_task = asyncio.create_task(get_social_sentiment(symbol))
    
    # Get technical analysis (sync)
    technicals = get_advanced_technicals(symbol)
    
    # Wait for async tasks
    news = await news_task
    sentiment = await sentiment_task
    
    # Build comprehensive prompt for AI
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    if not api_key:
        return {"decision": "SKIP", "reasoning": "API ключ не настроен", "confidence": 0}
    
    chat = LlmChat(
        api_key=api_key,
        session_id=f"deep-{symbol}-{datetime.now().timestamp()}",
        system_message="""Ты — лучший криптотрейдер мира с 15-летним опытом. Анализируй сигналы комплексно.

Твой анализ должен включать:
1. ТЕХНИЧЕСКИЙ АНАЛИЗ — RSI, MACD, тренд по EMA, уровни поддержки/сопротивления, объёмы
2. НОВОСТНОЙ ФОН — влияние последних новостей на цену
3. СОЦИАЛЬНЫЕ НАСТРОЕНИЯ — что говорят в Twitter/соцсетях
4. РИСК-МЕНЕДЖМЕНТ — оценка R:R, расположение SL/TP
5. ИТОГОВАЯ РЕКОМЕНДАЦИЯ — входить или нет

Отвечай структурированно на русском языке в формате JSON:
{
    "decision": "ACCEPT" или "REJECT",
    "confidence": 0-100,
    "summary": "Краткий вердикт 1 предложение",
    "technical_analysis": "Анализ графика 2-3 предложения",
    "news_impact": "Влияние новостей 1-2 предложения", 
    "sentiment": "Настроения рынка 1 предложение",
    "risk_assessment": "Оценка рисков 1-2 предложения",
    "recommendation": "Финальная рекомендация с конкретными действиями"
}"""
    ).with_model("openai", "gpt-5.2")
    
    # Format technical data
    tech_1h = technicals.get('1h', {})
    tech_4h = technicals.get('4h', {})
    tech_1d = technicals.get('1d', {})
    
    prompt = f"""
=== СИГНАЛ ===
Монета: {signal['symbol']}
Направление: {signal['direction']}
Вход: {signal['entry_price']}
Take Profit: {signal['take_profit']}
Stop Loss: {signal['stop_loss']}
R:R Ratio: {signal['rr_ratio']}
Тип: {signal.get('signal_type', 'standard')}
Уровень пробоя: {signal.get('level', 'N/A')}

=== ТЕХНИЧЕСКИЙ АНАЛИЗ ===

📊 1H Таймфрейм:
• Цена: {tech_1h.get('price', 'N/A')} | Изменение 24ч: {tech_1h.get('price_change_24h', 'N/A')}%
• Тренд: {tech_1h.get('trend', 'N/A')}
• RSI: {tech_1h.get('rsi', 'N/A')} | Stoch RSI: K={tech_1h.get('stoch_k', 'N/A')}, D={tech_1h.get('stoch_d', 'N/A')}
• MACD: {tech_1h.get('macd', 'N/A')} | Signal: {tech_1h.get('macd_signal', 'N/A')} | Hist: {tech_1h.get('macd_histogram', 'N/A')}
• EMA: 9={tech_1h.get('ema9', 'N/A')}, 21={tech_1h.get('ema21', 'N/A')}, 50={tech_1h.get('ema50', 'N/A')}
• Bollinger: {tech_1h.get('bb_position', 'N/A')} (Upper: {tech_1h.get('bb_upper', 'N/A')}, Lower: {tech_1h.get('bb_lower', 'N/A')})
• Объём: {tech_1h.get('volume_ratio', 'N/A')}x от среднего
• ATR: {tech_1h.get('atr', 'N/A')}
• Поддержка: {tech_1h.get('support', 'N/A')} | Сопротивление: {tech_1h.get('resistance', 'N/A')}

📊 4H Таймфрейм:
• Тренд: {tech_4h.get('trend', 'N/A')} | RSI: {tech_4h.get('rsi', 'N/A')}
• MACD Histogram: {tech_4h.get('macd_histogram', 'N/A')}
• Объём: {tech_4h.get('volume_ratio', 'N/A')}x

📊 1D Таймфрейм:
• Тренд: {tech_1d.get('trend', 'N/A')} | RSI: {tech_1d.get('rsi', 'N/A')}
• EMA200: {tech_1d.get('ema200', 'N/A')}

=== НОВОСТИ ===
{news if news else 'Новости не найдены'}

=== СОЦИАЛЬНЫЕ НАСТРОЕНИЯ ===
{sentiment if sentiment else 'Данные о настроениях недоступны'}

=== КРИТЕРИИ ОЦЕНКИ ===
• Минимальный R:R: 2.0
• Требуется совпадение направления с трендом
• RSI: избегать перекупленности (>70) для лонгов, перепроданности (<30) для шортов

Проанализируй ВСЁ и дай рекомендацию как лучший трейдер мира. JSON:"""

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        
        # Parse JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            result['technicals'] = technicals
            return result
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
    
    return {
        "decision": "SKIP",
        "reasoning": "Ошибка анализа",
        "confidence": 0
    }


def format_deep_analysis(signal: dict, analysis: dict) -> str:
    """Format deep analysis for Telegram"""
    decision = analysis.get('decision', 'SKIP')
    confidence = analysis.get('confidence', 0)
    
    if decision == 'ACCEPT':
        emoji, status = "✅", "ПРИНЯТ"
    elif decision == 'REJECT':
        emoji, status = "❌", "ОТКЛОНЁН"
    else:
        emoji, status = "⏸️", "ПРОПУЩЕН"
    
    dir_emoji = "🟢 LONG" if signal['direction'] == 'BUY' else "🔴 SHORT"
    
    # Get 1h technicals for quick stats
    tech = analysis.get('technicals', {}).get('1h', {})
    
    signal_type_text = ""
    if signal.get('signal_type') == 'support_breakout':
        signal_type_text = f"📉 Пробой поддержки ({signal.get('level', '')})"
    elif signal.get('signal_type') == 'resistance_breakout':
        signal_type_text = f"📈 Пробой сопротивления ({signal.get('level', '')})"
    
    return f"""{emoji} <b>{status} | {confidence}% уверенность</b>

{dir_emoji} <b>{signal['symbol']}</b>
{signal_type_text}

💰 <b>Сделка:</b>
├ Вход: <code>{signal['entry_price']}</code>
├ TP: <code>{signal['take_profit']}</code>
├ SL: <code>{signal['stop_loss']}</code>
└ R:R: <code>{signal['rr_ratio']}</code>

📊 <b>Технический анализ:</b>
├ Цена: <code>{tech.get('price', 'N/A')}</code>
├ RSI: <code>{tech.get('rsi', 'N/A')}</code> | Тренд: {tech.get('trend', 'N/A')}
├ MACD: <code>{tech.get('macd_histogram', 'N/A')}</code>
└ Объём: <code>{tech.get('volume_ratio', 'N/A')}x</code>

📝 <b>Краткий вердикт:</b>
{analysis.get('summary', 'N/A')}

📈 <b>Анализ графика:</b>
{analysis.get('technical_analysis', 'N/A')}

📰 <b>Новости:</b>
{analysis.get('news_impact', 'Нет данных')}

🐦 <b>Настроения:</b>
{analysis.get('sentiment', 'Нет данных')}

⚠️ <b>Риски:</b>
{analysis.get('risk_assessment', 'N/A')}

🎯 <b>Рекомендация:</b>
{analysis.get('recommendation', 'N/A')}"""


# Export for use in other modules
__all__ = ['deep_analyze_signal', 'format_deep_analysis', 'get_advanced_technicals']
