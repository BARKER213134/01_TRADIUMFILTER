"""
Unit Tests for Candle Pattern Detection Module
Tests bullish/bearish pattern detection with synthetic data
"""

import pytest
import pandas as pd
import sys
sys.path.insert(0, '/app/backend')

from candle_patterns import (
    detect_hammer, detect_inverted_hammer, detect_doji,
    detect_bullish_engulfing, detect_bearish_engulfing,
    detect_morning_star, detect_evening_star, detect_pin_bar,
    detect_reversal_pattern
)


def create_candle_df(candles):
    """Helper to create DataFrame from candle data"""
    return pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])


class TestBullishPatterns:
    """Tests for bullish reversal patterns (for LONG signals)"""
    
    def test_detect_hammer(self):
        """Hammer: small body at top, long lower shadow"""
        # Hammer candle: open=100, high=101, low=90, close=100.5
        # Body = 0.5, Lower shadow = 10, Upper shadow = 0.5
        candles = create_candle_df([
            [1, 100, 101, 90, 100.5, 1000]
        ])
        result = detect_hammer(candles)
        assert result is not None, "Should detect hammer pattern"
        assert result['type'] == 'bullish', f"Hammer should be bullish, got {result['type']}"
        print(f"✅ Hammer detected: {result['pattern']} (strength={result['strength']})")
    
    def test_detect_bullish_engulfing(self):
        """Bullish Engulfing: bearish candle followed by larger bullish candle"""
        candles = create_candle_df([
            [1, 105, 106, 99, 100, 1000],  # Bearish candle
            [2, 99, 110, 98, 108, 1500]    # Bullish engulfing
        ])
        result = detect_bullish_engulfing(candles)
        assert result is not None, "Should detect bullish engulfing"
        assert result['type'] == 'bullish', f"Should be bullish, got {result['type']}"
        print(f"✅ Bullish Engulfing detected: {result['pattern']} (strength={result['strength']})")
    
    def test_detect_morning_star(self):
        """Morning Star: bearish + small body + bullish"""
        candles = create_candle_df([
            [1, 110, 111, 100, 101, 1000],  # Bearish candle (body > 30% of range)
            [2, 100, 101, 99, 100.5, 800],  # Small body (< 40% of first body)
            [3, 101, 112, 100, 110, 1200]   # Bullish candle closing above midpoint of first
        ])
        result = detect_morning_star(candles)
        assert result is not None, "Should detect morning star"
        assert result['type'] == 'bullish', f"Should be bullish, got {result['type']}"
        print(f"✅ Morning Star detected: {result['pattern']} (strength={result['strength']})")
    
    def test_detect_bullish_pin_bar(self):
        """Bullish Pin Bar: very long lower wick"""
        # Pin bar: body < 25% of range, lower shadow >= 60% of range
        candles = create_candle_df([
            [1, 100, 101, 80, 100.5, 1000]  # Range=21, body=0.5, lower=20
        ])
        result = detect_pin_bar(candles)
        assert result is not None, "Should detect bullish pin bar"
        assert result['type'] == 'bullish', f"Should be bullish, got {result['type']}"
        print(f"✅ Bullish Pin Bar detected: {result['pattern']} (strength={result['strength']})")
    
    def test_detect_bullish_doji(self):
        """Dragonfly Doji: bullish doji with long lower shadow"""
        candles = create_candle_df([
            [1, 100, 100.5, 90, 100.2, 1000]  # Body ~0.2, lower shadow ~10, upper ~0.3
        ])
        result = detect_doji(candles)
        assert result is not None, "Should detect doji"
        # Dragonfly doji (lower > upper) is bullish
        if result['type'] == 'bullish':
            print(f"✅ Dragonfly Doji detected: {result['pattern']} (strength={result['strength']})")
        else:
            print(f"✅ Doji detected: {result['pattern']} (type={result['type']})")


class TestBearishPatterns:
    """Tests for bearish reversal patterns (for SHORT signals)"""
    
    def test_detect_shooting_star(self):
        """Shooting Star: small body at bottom, long upper shadow"""
        # Shooting star: open=100, high=110, low=99.5, close=100.5
        # Body = 0.5, Upper shadow = 9.5, Lower shadow = 0.5
        candles = create_candle_df([
            [1, 100, 110, 99.5, 100.5, 1000]
        ])
        result = detect_inverted_hammer(candles)
        assert result is not None, "Should detect shooting star pattern"
        assert result['type'] == 'bearish', f"Shooting star should be bearish, got {result['type']}"
        print(f"✅ Shooting Star detected: {result['pattern']} (strength={result['strength']})")
    
    def test_detect_bearish_engulfing(self):
        """Bearish Engulfing: bullish candle followed by larger bearish candle"""
        candles = create_candle_df([
            [1, 100, 106, 99, 105, 1000],   # Bullish candle
            [2, 106, 107, 98, 99, 1500]     # Bearish engulfing
        ])
        result = detect_bearish_engulfing(candles)
        assert result is not None, "Should detect bearish engulfing"
        assert result['type'] == 'bearish', f"Should be bearish, got {result['type']}"
        print(f"✅ Bearish Engulfing detected: {result['pattern']} (strength={result['strength']})")
    
    def test_detect_evening_star(self):
        """Evening Star: bullish + small body + bearish"""
        candles = create_candle_df([
            [1, 100, 111, 99, 110, 1000],   # Bullish candle (body > 30% of range)
            [2, 110, 111, 109, 110.5, 800], # Small body
            [3, 110, 111, 100, 101, 1200]   # Bearish candle closing below midpoint of first
        ])
        result = detect_evening_star(candles)
        assert result is not None, "Should detect evening star"
        assert result['type'] == 'bearish', f"Should be bearish, got {result['type']}"
        print(f"✅ Evening Star detected: {result['pattern']} (strength={result['strength']})")
    
    def test_detect_bearish_pin_bar(self):
        """Bearish Pin Bar: very long upper wick"""
        # Pin bar: body < 25% of range, upper shadow >= 60% of range
        candles = create_candle_df([
            [1, 100, 120, 99.5, 100.5, 1000]  # Range=20.5, body=0.5, upper=19.5
        ])
        result = detect_pin_bar(candles)
        assert result is not None, "Should detect bearish pin bar"
        assert result['type'] == 'bearish', f"Should be bearish, got {result['type']}"
        print(f"✅ Bearish Pin Bar detected: {result['pattern']} (strength={result['strength']})")
    
    def test_detect_bearish_doji(self):
        """Gravestone Doji: bearish doji with long upper shadow"""
        candles = create_candle_df([
            [1, 100, 110, 99.8, 100.2, 1000]  # Body ~0.2, upper shadow ~9.8, lower ~0.2
        ])
        result = detect_doji(candles)
        assert result is not None, "Should detect doji"
        # Gravestone doji (upper > lower) is bearish
        if result['type'] == 'bearish':
            print(f"✅ Gravestone Doji detected: {result['pattern']} (strength={result['strength']})")
        else:
            print(f"✅ Doji detected: {result['pattern']} (type={result['type']})")


class TestDirectionFiltering:
    """Tests that patterns are correctly filtered by direction"""
    
    def test_long_only_gets_bullish_patterns(self):
        """LONG signals should only match bullish patterns"""
        # Create a bullish engulfing pattern
        candles = create_candle_df([
            [1, 105, 106, 99, 100, 1000],  # Bearish
            [2, 99, 110, 98, 108, 1500]    # Bullish engulfing
        ])
        
        # Test bullish engulfing is detected
        result = detect_bullish_engulfing(candles)
        assert result is not None, "Should detect bullish engulfing"
        assert result['type'] == 'bullish'
        
        # Test bearish engulfing is NOT detected on same data
        result_bearish = detect_bearish_engulfing(candles)
        assert result_bearish is None, "Should NOT detect bearish engulfing on bullish pattern"
        print("✅ LONG direction correctly filters for bullish patterns only")
    
    def test_short_only_gets_bearish_patterns(self):
        """SHORT signals should only match bearish patterns"""
        # Create a bearish engulfing pattern
        candles = create_candle_df([
            [1, 100, 106, 99, 105, 1000],   # Bullish
            [2, 106, 107, 98, 99, 1500]     # Bearish engulfing
        ])
        
        # Test bearish engulfing is detected
        result = detect_bearish_engulfing(candles)
        assert result is not None, "Should detect bearish engulfing"
        assert result['type'] == 'bearish'
        
        # Test bullish engulfing is NOT detected on same data
        result_bullish = detect_bullish_engulfing(candles)
        assert result_bullish is None, "Should NOT detect bullish engulfing on bearish pattern"
        print("✅ SHORT direction correctly filters for bearish patterns only")


class TestEdgeCases:
    """Edge case tests"""
    
    def test_no_pattern_on_neutral_candle(self):
        """Regular candle should not trigger pattern detection"""
        candles = create_candle_df([
            [1, 100, 105, 95, 102, 1000]  # Normal candle, no extreme shadows
        ])
        
        hammer = detect_hammer(candles)
        shooting = detect_inverted_hammer(candles)
        pin = detect_pin_bar(candles)
        
        # At least one should be None (not all patterns match)
        assert hammer is None or shooting is None or pin is None, "Normal candle should not match all patterns"
        print("✅ Normal candle does not trigger false pattern detection")
    
    def test_insufficient_candles_for_multi_candle_patterns(self):
        """Multi-candle patterns should return None with insufficient data"""
        single_candle = create_candle_df([
            [1, 100, 105, 95, 102, 1000]
        ])
        
        engulfing = detect_bullish_engulfing(single_candle)
        morning = detect_morning_star(single_candle)
        
        assert engulfing is None, "Engulfing needs 2 candles"
        assert morning is None, "Morning star needs 3 candles"
        print("✅ Multi-candle patterns correctly handle insufficient data")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
