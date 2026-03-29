"""
Backend API Tests for Tradium Signal Monitor
Tests: /api/signals, /api/entries, /api/entries/stats, /api/charts
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://trade-filter-bot.preview.emergentagent.com')


class TestSignalsAPI:
    """Tests for /api/signals endpoint"""
    
    def test_get_signals_returns_200(self):
        """GET /api/signals should return 200"""
        response = requests.get(f"{BASE_URL}/api/signals")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✅ GET /api/signals returns 200")
    
    def test_get_signals_returns_list(self):
        """GET /api/signals should return a list"""
        response = requests.get(f"{BASE_URL}/api/signals")
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/signals returns list with {len(data)} signals")
    
    def test_signals_no_mongodb_id(self):
        """Signals should not contain MongoDB _id field"""
        response = requests.get(f"{BASE_URL}/api/signals")
        data = response.json()
        for signal in data:
            assert "_id" not in signal, f"Signal contains _id field: {signal.get('id', 'unknown')}"
        print("✅ Signals do not contain _id field")
    
    def test_signals_have_required_fields(self):
        """Signals should have required fields"""
        response = requests.get(f"{BASE_URL}/api/signals")
        data = response.json()
        if data:
            signal = data[0]
            required_fields = ['id', 'symbol', 'direction', 'status']
            for field in required_fields:
                assert field in signal, f"Missing required field: {field}"
            print(f"✅ Signal has required fields: {required_fields}")
        else:
            print("⚠️ No signals to test fields")


class TestEntriesAPI:
    """Tests for /api/entries endpoint"""
    
    def test_get_entries_returns_200(self):
        """GET /api/entries should return 200"""
        response = requests.get(f"{BASE_URL}/api/entries")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✅ GET /api/entries returns 200")
    
    def test_get_entries_returns_list(self):
        """GET /api/entries should return a list"""
        response = requests.get(f"{BASE_URL}/api/entries")
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/entries returns list with {len(data)} entries")
    
    def test_entries_no_mongodb_id(self):
        """Entries should not contain MongoDB _id field"""
        response = requests.get(f"{BASE_URL}/api/entries")
        data = response.json()
        for entry in data:
            assert "_id" not in entry, f"Entry contains _id field: {entry.get('signal_id', 'unknown')}"
        print("✅ Entries do not contain _id field")
    
    def test_entries_have_required_fields(self):
        """Entries should have required fields"""
        response = requests.get(f"{BASE_URL}/api/entries")
        data = response.json()
        if data:
            entry = data[0]
            required_fields = ['signal_id', 'symbol', 'direction', 'status']
            for field in required_fields:
                assert field in entry, f"Missing required field: {field}"
            print(f"✅ Entry has required fields: {required_fields}")
        else:
            print("⚠️ No entries to test fields")


class TestEntriesStatsAPI:
    """Tests for /api/entries/stats endpoint"""
    
    def test_get_entries_stats_returns_200(self):
        """GET /api/entries/stats should return 200"""
        response = requests.get(f"{BASE_URL}/api/entries/stats")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✅ GET /api/entries/stats returns 200")
    
    def test_entries_stats_has_required_fields(self):
        """Stats should have all required fields"""
        response = requests.get(f"{BASE_URL}/api/entries/stats")
        data = response.json()
        required_fields = [
            'total_signals', 'watching', 'dca4_reached', 
            'entered', 'open', 'tp_hit', 'sl_hit', 'win_rate'
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print(f"✅ Stats has all required fields: {required_fields}")
    
    def test_entries_stats_values_are_numbers(self):
        """Stats values should be numbers"""
        response = requests.get(f"{BASE_URL}/api/entries/stats")
        data = response.json()
        for key, value in data.items():
            assert isinstance(value, (int, float)), f"{key} should be a number, got {type(value)}"
        print("✅ All stats values are numbers")
    
    def test_entries_stats_win_rate_valid(self):
        """Win rate should be between 0 and 100"""
        response = requests.get(f"{BASE_URL}/api/entries/stats")
        data = response.json()
        win_rate = data.get('win_rate', 0)
        assert 0 <= win_rate <= 100, f"Win rate should be 0-100, got {win_rate}"
        print(f"✅ Win rate is valid: {win_rate}%")


class TestChartsAPI:
    """Tests for /api/charts/{filename} endpoint"""
    
    def test_get_existing_chart_returns_200(self):
        """GET /api/charts/e2e_atlas_test.jpg should return 200"""
        response = requests.get(f"{BASE_URL}/api/charts/e2e_atlas_test.jpg")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✅ GET /api/charts/e2e_atlas_test.jpg returns 200")
    
    def test_get_existing_chart_returns_image(self):
        """Chart endpoint should return image content type"""
        response = requests.get(f"{BASE_URL}/api/charts/e2e_atlas_test.jpg")
        content_type = response.headers.get('content-type', '')
        assert 'image' in content_type, f"Expected image content type, got {content_type}"
        print(f"✅ Chart returns image content type: {content_type}")
    
    def test_get_nonexistent_chart_returns_404(self):
        """GET /api/charts/nonexistent.jpg should return 404"""
        response = requests.get(f"{BASE_URL}/api/charts/nonexistent.jpg")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✅ GET /api/charts/nonexistent.jpg returns 404")


class TestRootAPI:
    """Tests for root API endpoint"""
    
    def test_root_returns_200(self):
        """GET /api/ should return 200"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✅ GET /api/ returns 200")
    
    def test_root_returns_message(self):
        """Root should return API message"""
        response = requests.get(f"{BASE_URL}/api/")
        data = response.json()
        assert 'message' in data, "Response should contain 'message' field"
        print(f"✅ Root returns message: {data['message']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
