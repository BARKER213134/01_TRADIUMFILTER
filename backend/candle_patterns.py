#!/usr/bin/env python3
"""
Candle Pattern Detector
Detects reversal candlestick patterns from OHLCV data via CCXT.
Patterns: Hammer, Inverted Hammer, Doji, Engulfing, Morning/Evening Star, Pin Bar
"""

import logging
import ccxt
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)

exchange = ccxt.kraken({'enableRateLimit': True})


def fetch_candles(symbol: str, timeframe: str = '4h', limit: int = 20) -> Optional[pd.DataFrame]:
    """Fetch OHLCV candles from exchange"""
    base = symbol.replace("USDT", "").replace("PERP", "").upper()

    for sym in [f"{base}/USD", f"{base}/USDT"]:
        try:
            ohlcv = exchange.fetch_ohlcv(sym, timeframe, limit=limit)
            if ohlcv and len(ohlcv) >= 5:
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col])
                return df
        except Exception:
            continue

    try:
        okx = ccxt.okx({'enableRateLimit': True})
        ohlcv = okx.fetch_ohlcv(f"{base}/USDT", timeframe, limit=limit)
        if ohlcv and len(ohlcv) >= 5:
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            return df
    except Exception:
        pass

    return None


def _body(row) -> float:
    return abs(row['close'] - row['open'])


def _upper_shadow(row) -> float:
    return row['high'] - max(row['open'], row['close'])


def _lower_shadow(row) -> float:
    return min(row['open'], row['close']) - row['low']


def _candle_range(row) -> float:
    return row['high'] - row['low']


def _is_bullish(row) -> bool:
    return row['close'] > row['open']


def _is_bearish(row) -> bool:
    return row['close'] < row['open']


def detect_hammer(candles: pd.DataFrame) -> Optional[dict]:
    """Hammer (bullish reversal): small body at top, long lower shadow"""
    c = candles.iloc[-1]
    r = _candle_range(c)
    if r == 0:
        return None

    body = _body(c)
    lower = _lower_shadow(c)
    upper = _upper_shadow(c)

    if lower >= body * 2 and upper <= body * 0.5 and body / r < 0.35:
        return {"pattern": "Молот (Hammer)", "type": "bullish", "strength": 0.75}
    return None


def detect_inverted_hammer(candles: pd.DataFrame) -> Optional[dict]:
    """Inverted Hammer / Shooting Star (bearish reversal): small body at bottom, long upper shadow"""
    c = candles.iloc[-1]
    r = _candle_range(c)
    if r == 0:
        return None

    body = _body(c)
    upper = _upper_shadow(c)
    lower = _lower_shadow(c)

    if upper >= body * 2 and lower <= body * 0.5 and body / r < 0.35:
        return {"pattern": "Падающая звезда (Shooting Star)", "type": "bearish", "strength": 0.75}
    return None


def detect_doji(candles: pd.DataFrame) -> Optional[dict]:
    """Doji: open ≈ close, indicates indecision/reversal"""
    c = candles.iloc[-1]
    r = _candle_range(c)
    if r == 0:
        return None

    body = _body(c)
    if body / r <= 0.1:
        upper = _upper_shadow(c)
        lower = _lower_shadow(c)

        if upper > 0 and lower > 0:
            ratio = max(upper, lower) / min(upper, lower) if min(upper, lower) > 0 else 10
            if ratio > 2.5:
                if lower > upper:
                    return {"pattern": "Доджи-стрекоза (Dragonfly Doji)", "type": "bullish", "strength": 0.7}
                else:
                    return {"pattern": "Доджи-надгробие (Gravestone Doji)", "type": "bearish", "strength": 0.7}
            return {"pattern": "Доджи (Doji)", "type": "neutral", "strength": 0.5}
    return None


def detect_bullish_engulfing(candles: pd.DataFrame) -> Optional[dict]:
    """Bullish Engulfing: bearish candle followed by larger bullish candle"""
    if len(candles) < 2:
        return None

    prev = candles.iloc[-2]
    curr = candles.iloc[-1]

    if _is_bearish(prev) and _is_bullish(curr):
        if curr['open'] <= prev['close'] and curr['close'] >= prev['open']:
            if _body(curr) > _body(prev) * 1.2:
                return {"pattern": "Бычье поглощение (Bullish Engulfing)", "type": "bullish", "strength": 0.85}
    return None


def detect_bearish_engulfing(candles: pd.DataFrame) -> Optional[dict]:
    """Bearish Engulfing: bullish candle followed by larger bearish candle"""
    if len(candles) < 2:
        return None

    prev = candles.iloc[-2]
    curr = candles.iloc[-1]

    if _is_bullish(prev) and _is_bearish(curr):
        if curr['open'] >= prev['close'] and curr['close'] <= prev['open']:
            if _body(curr) > _body(prev) * 1.2:
                return {"pattern": "Медвежье поглощение (Bearish Engulfing)", "type": "bearish", "strength": 0.85}
    return None


def detect_morning_star(candles: pd.DataFrame) -> Optional[dict]:
    """Morning Star (bullish): bearish + small body + bullish"""
    if len(candles) < 3:
        return None

    c1 = candles.iloc[-3]
    c2 = candles.iloc[-2]
    c3 = candles.iloc[-1]

    if (_is_bearish(c1) and _body(c1) > _candle_range(c1) * 0.3
            and _body(c2) < _body(c1) * 0.4
            and _is_bullish(c3) and _body(c3) > _candle_range(c3) * 0.3
            and c3['close'] > (c1['open'] + c1['close']) / 2):
        return {"pattern": "Утренняя звезда (Morning Star)", "type": "bullish", "strength": 0.9}
    return None


def detect_evening_star(candles: pd.DataFrame) -> Optional[dict]:
    """Evening Star (bearish): bullish + small body + bearish"""
    if len(candles) < 3:
        return None

    c1 = candles.iloc[-3]
    c2 = candles.iloc[-2]
    c3 = candles.iloc[-1]

    if (_is_bullish(c1) and _body(c1) > _candle_range(c1) * 0.3
            and _body(c2) < _body(c1) * 0.4
            and _is_bearish(c3) and _body(c3) > _candle_range(c3) * 0.3
            and c3['close'] < (c1['open'] + c1['close']) / 2):
        return {"pattern": "Вечерняя звезда (Evening Star)", "type": "bearish", "strength": 0.9}
    return None


def detect_pin_bar(candles: pd.DataFrame) -> Optional[dict]:
    """Pin Bar: very long wick showing rejection"""
    c = candles.iloc[-1]
    r = _candle_range(c)
    if r == 0:
        return None

    body = _body(c)
    upper = _upper_shadow(c)
    lower = _lower_shadow(c)

    if body / r < 0.25:
        if lower >= r * 0.6:
            return {"pattern": "Бычий пин-бар (Bullish Pin Bar)", "type": "bullish", "strength": 0.8}
        if upper >= r * 0.6:
            return {"pattern": "Медвежий пин-бар (Bearish Pin Bar)", "type": "bearish", "strength": 0.8}
    return None


def detect_reversal_pattern(symbol: str, timeframe: str, direction: str) -> Optional[dict]:
    """
    Main function: detect reversal pattern appropriate for the signal direction.
    
    For SHORT signals (DCA#4 at resistance) → look for BEARISH reversal
    For LONG signals (DCA#4 at support) → look for BULLISH reversal
    
    Returns: {pattern, type, strength, candle_data} or None
    """
    tf_map = {
        '1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m',
        '1h': '1h', '2h': '2h', '4h': '4h', '6h': '6h',
        '12h': '12h', '1d': '1d', '1D': '1d', '1w': '1w',
    }
    tf = tf_map.get(timeframe, '4h')

    candles = fetch_candles(symbol, tf, limit=20)
    if candles is None or len(candles) < 3:
        logger.warning(f"Cannot fetch candles for {symbol} {tf}")
        return None

    last = candles.iloc[-1]
    candle_info = {
        "open": float(last['open']),
        "high": float(last['high']),
        "low": float(last['low']),
        "close": float(last['close']),
        "volume": float(last['volume']),
    }

    if direction == 'SHORT':
        target_type = 'bearish'
    else:
        target_type = 'bullish'

    detectors = [
        detect_bullish_engulfing,
        detect_bearish_engulfing,
        detect_morning_star,
        detect_evening_star,
        detect_hammer,
        detect_inverted_hammer,
        detect_pin_bar,
        detect_doji,
    ]

    best = None
    for detector in detectors:
        result = detector(candles)
        if result and (result['type'] == target_type or result['type'] == 'neutral'):
            if best is None or result['strength'] > best['strength']:
                best = result

    if best:
        best['candle_data'] = candle_info
        logger.info(f"🕯 {symbol}: {best['pattern']} (strength={best['strength']})")
        return best

    return None
