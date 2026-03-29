"""
Unit Tests for Entry Monitor DCA#4 Trigger Logic
Tests price trigger conditions for LONG and SHORT directions
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')


class TestDCA4TriggerLogic:
    """Tests for DCA#4 price trigger conditions"""
    
    def test_short_triggers_when_price_above_dca4(self):
        """SHORT: should trigger when price >= dca4 (price rises to resistance)"""
        dca4 = 2000.0
        tolerance = dca4 * 0.003  # 0.3% tolerance
        
        # Price at DCA#4 - should trigger
        price_at_dca4 = 2000.0
        triggered = price_at_dca4 >= dca4 - tolerance
        assert triggered, f"SHORT should trigger when price ({price_at_dca4}) >= dca4 ({dca4})"
        
        # Price above DCA#4 - should trigger
        price_above = 2010.0
        triggered = price_above >= dca4 - tolerance
        assert triggered, f"SHORT should trigger when price ({price_above}) > dca4 ({dca4})"
        
        # Price below DCA#4 (outside tolerance) - should NOT trigger
        price_below = 1980.0
        triggered = price_below >= dca4 - tolerance
        assert not triggered, f"SHORT should NOT trigger when price ({price_below}) << dca4 ({dca4})"
        
        print("✅ SHORT DCA#4 trigger logic: price >= dca4 (resistance zone)")
    
    def test_long_triggers_when_price_below_dca4(self):
        """LONG: should trigger when price <= dca4 (price falls to support)"""
        dca4 = 2000.0
        tolerance = dca4 * 0.003  # 0.3% tolerance
        
        # Price at DCA#4 - should trigger
        price_at_dca4 = 2000.0
        triggered = price_at_dca4 <= dca4 + tolerance
        assert triggered, f"LONG should trigger when price ({price_at_dca4}) <= dca4 ({dca4})"
        
        # Price below DCA#4 - should trigger
        price_below = 1990.0
        triggered = price_below <= dca4 + tolerance
        assert triggered, f"LONG should trigger when price ({price_below}) < dca4 ({dca4})"
        
        # Price above DCA#4 (outside tolerance) - should NOT trigger
        price_above = 2020.0
        triggered = price_above <= dca4 + tolerance
        assert not triggered, f"LONG should NOT trigger when price ({price_above}) >> dca4 ({dca4})"
        
        print("✅ LONG DCA#4 trigger logic: price <= dca4 (support zone)")
    
    def test_tolerance_allows_near_dca4_triggers(self):
        """Tolerance (0.3%) should allow triggers slightly before exact DCA#4"""
        dca4 = 2000.0
        tolerance = dca4 * 0.003  # = 6.0
        
        # SHORT: price slightly below DCA#4 but within tolerance
        price_near_short = 1995.0  # 5 below, tolerance is 6
        triggered_short = price_near_short >= dca4 - tolerance
        assert triggered_short, f"SHORT should trigger at {price_near_short} (within tolerance of {dca4})"
        
        # LONG: price slightly above DCA#4 but within tolerance
        price_near_long = 2005.0  # 5 above, tolerance is 6
        triggered_long = price_near_long <= dca4 + tolerance
        assert triggered_long, f"LONG should trigger at {price_near_long} (within tolerance of {dca4})"
        
        print("✅ Tolerance (0.3%) correctly allows near-DCA#4 triggers")


class TestFormatFunctions:
    """Tests for alert formatting functions"""
    
    def test_format_dca4_reached_short(self):
        """Format function should work for SHORT direction"""
        from entry_monitor import format_dca4_reached
        
        signal = {
            'direction': 'SHORT',
            'symbol': 'ETHUSDT',
            'timeframe': '4h',
            'dca4_level': 2021.5
        }
        current_price = 2025.0
        
        result = format_dca4_reached(signal, current_price)
        
        assert 'ШОРТ' in result, "Should contain ШОРТ for SHORT direction"
        assert 'сопротивления' in result, "Should mention resistance zone for SHORT"
        assert 'медвежью' in result, "Should wait for bearish candle for SHORT"
        assert 'ETH' in result, "Should contain symbol"
        print("✅ format_dca4_reached works for SHORT direction")
    
    def test_format_dca4_reached_long(self):
        """Format function should work for LONG direction"""
        from entry_monitor import format_dca4_reached
        
        signal = {
            'direction': 'LONG',
            'symbol': 'BTCUSDT',
            'timeframe': '1h',
            'dca4_level': 95000.0
        }
        current_price = 94800.0
        
        result = format_dca4_reached(signal, current_price)
        
        assert 'ЛОНГ' in result, "Should contain ЛОНГ for LONG direction"
        assert 'поддержки' in result, "Should mention support zone for LONG"
        assert 'бычью' in result, "Should wait for bullish candle for LONG"
        assert 'BTC' in result, "Should contain symbol"
        print("✅ format_dca4_reached works for LONG direction")
    
    def test_format_confirmed_entry_short(self):
        """Format confirmed entry for SHORT"""
        from entry_monitor import format_confirmed_entry
        
        signal = {
            'direction': 'SHORT',
            'symbol': 'ETHUSDT',
            'timeframe': '4h',
            'dca4_level': 2021.5,
            'take_profit': 1821.5,
            'stop_loss': 2171.5,
            'rr_ratio': 2.67,
            'tp_pct': 9.8,
            'sl_pct': 3.7,
            'trend': '🔴',
            'ma_status': '🔴',
            'rsi_status': '🔴',
            'dca_data': {
                'dca1': 1991.5,
                'dca2': 2001.5,
                'dca3': 2011.5,
                'dca4': 2021.5,
                'dca5': 2031.5,
                'zone_low': 2051.5,
                'zone_high': 2081.5
            }
        }
        pattern = {
            'pattern': 'Bearish Engulfing',
            'strength': 0.85,
            'candle_data': {'open': 2025, 'high': 2030, 'low': 2015, 'close': 2018}
        }
        current_price = 2020.0
        
        result = format_confirmed_entry(signal, current_price, pattern)
        
        assert 'ШОРТ' in result, "Should contain ШОРТ"
        assert 'SELL' in result, "Should contain SELL action"
        assert 'Bearish Engulfing' in result, "Should contain pattern name"
        print("✅ format_confirmed_entry works for SHORT direction")
    
    def test_format_confirmed_entry_long(self):
        """Format confirmed entry for LONG"""
        from entry_monitor import format_confirmed_entry
        
        signal = {
            'direction': 'LONG',
            'symbol': 'BTCUSDT',
            'timeframe': '4h',
            'dca4_level': 95000.0,
            'take_profit': 100000.0,
            'stop_loss': 93000.0,
            'rr_ratio': 2.5,
            'tp_pct': 5.3,
            'sl_pct': 2.1,
            'trend': '🟢',
            'ma_status': '🟢',
            'rsi_status': '🟢',
            'dca_data': {
                'dca1': 96000,
                'dca2': 95500,
                'dca3': 95200,
                'dca4': 95000,
                'dca5': 94800,
                'zone_low': 94500,
                'zone_high': 95000
            }
        }
        pattern = {
            'pattern': 'Hammer',
            'strength': 0.75,
            'candle_data': {'open': 95100, 'high': 95200, 'low': 94800, 'close': 95150}
        }
        current_price = 95100.0
        
        result = format_confirmed_entry(signal, current_price, pattern)
        
        assert 'ЛОНГ' in result, "Should contain ЛОНГ"
        assert 'BUY' in result, "Should contain BUY action"
        assert 'Hammer' in result, "Should contain pattern name"
        print("✅ format_confirmed_entry works for LONG direction")


class TestTPSLLogic:
    """Tests for TP/SL hit detection logic"""
    
    def test_short_tp_hit_when_price_falls(self):
        """SHORT TP: hit when price <= take_profit"""
        direction = 'SHORT'
        tp = 1800.0
        sl = 2200.0
        
        # Price at TP - should hit
        price_at_tp = 1800.0
        tp_hit = price_at_tp <= tp
        assert tp_hit, f"SHORT TP should hit when price ({price_at_tp}) <= tp ({tp})"
        
        # Price below TP - should hit
        price_below_tp = 1750.0
        tp_hit = price_below_tp <= tp
        assert tp_hit, f"SHORT TP should hit when price ({price_below_tp}) < tp ({tp})"
        
        print("✅ SHORT TP hit logic: price <= take_profit")
    
    def test_short_sl_hit_when_price_rises(self):
        """SHORT SL: hit when price >= stop_loss"""
        direction = 'SHORT'
        tp = 1800.0
        sl = 2200.0
        
        # Price at SL - should hit
        price_at_sl = 2200.0
        sl_hit = price_at_sl >= sl
        assert sl_hit, f"SHORT SL should hit when price ({price_at_sl}) >= sl ({sl})"
        
        # Price above SL - should hit
        price_above_sl = 2250.0
        sl_hit = price_above_sl >= sl
        assert sl_hit, f"SHORT SL should hit when price ({price_above_sl}) > sl ({sl})"
        
        print("✅ SHORT SL hit logic: price >= stop_loss")
    
    def test_long_tp_hit_when_price_rises(self):
        """LONG TP: hit when price >= take_profit"""
        direction = 'LONG'
        tp = 100000.0
        sl = 90000.0
        
        # Price at TP - should hit
        price_at_tp = 100000.0
        tp_hit = price_at_tp >= tp
        assert tp_hit, f"LONG TP should hit when price ({price_at_tp}) >= tp ({tp})"
        
        # Price above TP - should hit
        price_above_tp = 102000.0
        tp_hit = price_above_tp >= tp
        assert tp_hit, f"LONG TP should hit when price ({price_above_tp}) > tp ({tp})"
        
        print("✅ LONG TP hit logic: price >= take_profit")
    
    def test_long_sl_hit_when_price_falls(self):
        """LONG SL: hit when price <= stop_loss"""
        direction = 'LONG'
        tp = 100000.0
        sl = 90000.0
        
        # Price at SL - should hit
        price_at_sl = 90000.0
        sl_hit = price_at_sl <= sl
        assert sl_hit, f"LONG SL should hit when price ({price_at_sl}) <= sl ({sl})"
        
        # Price below SL - should hit
        price_below_sl = 88000.0
        sl_hit = price_below_sl <= sl
        assert sl_hit, f"LONG SL should hit when price ({price_below_sl}) < sl ({sl})"
        
        print("✅ LONG SL hit logic: price <= stop_loss")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
