#!/usr/bin/env python3
"""
Backend API Testing for AI Trading Signal Screener
Tests all endpoints and core functionality
"""

import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any

class TradingSignalAPITester:
    def __init__(self, base_url="https://ai-signal-screener.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})

    def log_test(self, name: str, success: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
        if details:
            print(f"    {details}")
        
        if success:
            self.tests_passed += 1
        else:
            self.failed_tests.append({"test": name, "details": details})

    def test_endpoint(self, method: str, endpoint: str, expected_status: int = 200, 
                     data: Dict = None, description: str = "") -> tuple:
        """Test a single endpoint"""
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url)
            elif method.upper() == 'POST':
                response = self.session.post(url, json=data)
            else:
                return False, f"Unsupported method: {method}"

            success = response.status_code == expected_status
            
            if success:
                try:
                    json_data = response.json()
                    details = f"Status: {response.status_code}"
                except:
                    details = f"Status: {response.status_code} (non-JSON response)"
            else:
                details = f"Expected {expected_status}, got {response.status_code}"
                if response.text:
                    details += f" - {response.text[:200]}"

            self.log_test(f"{method} {endpoint}" + (f" - {description}" if description else ""), 
                         success, details)
            
            return success, response.json() if success and response.headers.get('content-type', '').startswith('application/json') else response.text

        except Exception as e:
            self.log_test(f"{method} {endpoint}" + (f" - {description}" if description else ""), 
                         False, f"Exception: {str(e)}")
            return False, str(e)

    def test_root_endpoint(self):
        """Test GET / - root endpoint"""
        success, response = self.test_endpoint('GET', '/', 200, description="API root message")
        return success

    def test_settings_endpoints(self):
        """Test settings endpoints"""
        print("\n🔧 Testing Settings Endpoints...")
        
        # Test GET settings
        success1, settings_data = self.test_endpoint('GET', '/settings', 200, description="Get current settings")
        
        # Test POST settings with sample data
        test_settings = {
            "min_rr_ratio": 2.5,
            "min_volume_multiplier": 1.8,
            "trend_alignment_required": True,
            "send_rejected": False
        }
        success2, _ = self.test_endpoint('POST', '/settings', 200, test_settings, "Update settings")
        
        return success1 and success2

    def test_signal_endpoints(self):
        """Test signal-related endpoints"""
        print("\n📊 Testing Signal Endpoints...")
        
        # Test GET signals
        success1, _ = self.test_endpoint('GET', '/signals', 200, description="List all signals")
        
        # Test GET signals with parameters
        success2, _ = self.test_endpoint('GET', '/signals?limit=10&status=accepted', 200, 
                                       description="List signals with filters")
        
        # Test GET stats
        success3, stats_data = self.test_endpoint('GET', '/signals/stats', 200, description="Get signal statistics")
        
        # Test GET chart data
        success4, _ = self.test_endpoint('GET', '/signals/chart/daily?days=7', 200, 
                                       description="Get daily chart data")
        
        return all([success1, success2, success3, success4])

    def test_signal_analysis(self):
        """Test manual signal analysis"""
        print("\n🤖 Testing Signal Analysis...")
        
        # Test with valid signal format
        test_signal = {
            "text": "BUY BTCUSDT @ 95000, TP: 96000, SL: 94500"
        }
        
        success, response = self.test_endpoint('POST', '/signals/analyze', 200, test_signal, 
                                             "Analyze valid signal")
        
        if success and isinstance(response, dict):
            # Check if response has expected fields
            expected_fields = ['id', 'symbol', 'direction', 'entry_price', 'take_profit', 'stop_loss', 'rr_ratio']
            has_fields = all(field in response for field in expected_fields)
            if has_fields:
                print(f"    Signal parsed: {response.get('symbol')} {response.get('direction')} @ {response.get('entry_price')}")
                print(f"    R:R Ratio: {response.get('rr_ratio')}, Status: {response.get('status')}")
            else:
                print(f"    Missing expected fields in response")
        
        # Test with invalid signal format
        invalid_signal = {"text": "This is not a valid trading signal"}
        success2, _ = self.test_endpoint('POST', '/signals/analyze', 400, invalid_signal, 
                                       "Analyze invalid signal (should fail)")
        
        return success and success2

    def test_bot_endpoints(self):
        """Test bot control endpoints"""
        print("\n🤖 Testing Bot Control Endpoints...")
        
        # Test GET bot status
        success1, status_data = self.test_endpoint('GET', '/bot/status', 200, description="Get bot status")
        
        if success1 and isinstance(status_data, dict):
            print(f"    Bot running: {status_data.get('is_running')}")
            print(f"    Telethon connected: {status_data.get('telethon_connected')}")
            print(f"    Signals today: {status_data.get('signals_today', 0)}")
        
        # Test POST start bot
        success2, _ = self.test_endpoint('POST', '/bot/start', 200, description="Start bot")
        
        # Test POST stop bot
        success3, _ = self.test_endpoint('POST', '/bot/stop', 200, description="Stop bot")
        
        return all([success1, success2, success3])

    def test_market_data_endpoint(self):
        """Test market data endpoint"""
        print("\n📈 Testing Market Data Endpoint...")
        
        # Test with valid symbol
        success1, market_data = self.test_endpoint('GET', '/market/BTCUSDT', 200, 
                                                 description="Get BTCUSDT market data")
        
        if success1 and isinstance(market_data, dict):
            expected_fields = ['current_price', 'rsi', 'trend', 'volume_ratio']
            has_fields = any(field in market_data for field in expected_fields)
            if has_fields:
                print(f"    Current price: {market_data.get('current_price')}")
                print(f"    RSI: {market_data.get('rsi')}")
                print(f"    Trend: {market_data.get('trend')}")
            else:
                print(f"    Market data response may be incomplete")
        
        # Test with invalid symbol (should fail)
        success2, _ = self.test_endpoint('GET', '/market/INVALIDCOIN', 404, 
                                       description="Get invalid symbol (should fail)")
        
        return success1 and success2

    def test_signal_parsing_formats(self):
        """Test different signal parsing formats"""
        print("\n📝 Testing Signal Parsing Formats...")
        
        test_signals = [
            "BUY BTCUSDT @ 95000, TP: 96000, SL: 94500",
            "SELL ETHUSDT @ 3500, TP: 3400, SL: 3600",
            "LONG ADAUSDT Entry: 0.45 TP: 0.48 SL: 0.42",
            "SHORT BNBUSDT 600-580-620"
        ]
        
        success_count = 0
        for i, signal_text in enumerate(test_signals, 1):
            test_data = {"text": signal_text}
            success, response = self.test_endpoint('POST', '/signals/analyze', 200, test_data, 
                                                 f"Parse format {i}: {signal_text[:30]}...")
            if success:
                success_count += 1
        
        return success_count >= 3  # At least 3 out of 4 should work

    def run_all_tests(self):
        """Run all tests"""
        print("🚀 Starting AI Trading Signal Screener API Tests")
        print(f"🌐 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Test root endpoint
        print("\n🏠 Testing Root Endpoint...")
        self.test_root_endpoint()
        
        # Test all endpoint categories
        self.test_settings_endpoints()
        self.test_signal_endpoints()
        self.test_signal_analysis()
        self.test_bot_endpoints()
        self.test_market_data_endpoint()
        self.test_signal_parsing_formats()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {len(self.failed_tests)}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in self.failed_tests:
                print(f"  - {test['test']}: {test['details']}")
        
        return len(self.failed_tests) == 0

def main():
    """Main test execution"""
    tester = TradingSignalAPITester()
    success = tester.run_all_tests()
    
    print(f"\n🏁 Testing completed. {'All tests passed!' if success else 'Some tests failed.'}")
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())