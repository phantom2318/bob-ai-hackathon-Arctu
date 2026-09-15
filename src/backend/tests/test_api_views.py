"""
Unit tests for Django API endpoints.
"""

# pyrefly: ignore [missing-import]
import os
import sys
import unittest

# Ensure src/backend is in sys.path when running tests directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

import django
from django.apps import apps
if not apps.ready:
    django.setup()

from unittest import mock
from django.test import Client, RequestFactory
from api.views import (
    get_assets,
    get_incidents,
    get_predictions,
    get_weather,
    get_maintenance_plan,
)


class TestApiViews(unittest.TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.client = Client()

    def test_get_assets_endpoint(self):
        """Test GET /api/assets/ returns 200 OK and a list of grid assets."""
        request = self.factory.get('/api/assets/')
        response = get_assets(request)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertGreater(len(response.data), 0)
        self.assertIn("asset_id", response.data[0])

    def test_get_predictions_endpoint(self):
        """Test GET /api/predictions/ returns 200 OK sorted by risk_score DESC."""
        request = self.factory.get('/api/predictions/')
        response = get_predictions(request)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertGreater(len(response.data), 0)

        # Verify sorting DESC by risk_score
        scores = [item["risk_score"] for item in response.data]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_get_incidents_endpoint(self):
        """Test GET /api/incidents/ returns historical incident records."""
        request = self.factory.get('/api/incidents/')
        response = get_incidents(request)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertGreater(len(response.data), 0)
        self.assertIn("incident_id", response.data[0])

    def test_get_weather_endpoint(self):
        """Test GET /api/weather/ returns forecast records."""
        response = get_weather(self.factory.get('/api/weather/'))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertGreater(len(response.data), 0)
        self.assertIn("forecast", response.data[0])

    def test_get_maintenance_plan_endpoint(self):
        """Test GET /api/maintenance-plan/ returns HIGH risk assets with crew instructions."""
        request = self.factory.get('/api/maintenance-plan/')
        response = get_maintenance_plan(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("total_high_risk_count", response.data)
        self.assertIn("maintenance_plan", response.data)

        plan = response.data["maintenance_plan"]
        for entry in plan:
            self.assertEqual(entry["risk_category"], "HIGH")
            self.assertIn("dispatch_instructions", entry)
            self.assertIn("crew_preposition_zone", entry)

    def test_cors_headers_wildcard(self):
        """Verify CORS middleware returns wildcard origin header for frontend callers."""
        response = self.client.get('/api/predictions/', HTTP_ORIGIN='http://127.0.0.1:3000')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")

    def test_cors_preflight_options(self):
        """Verify CORS OPTIONS preflight request succeeds with Access-Control-Allow-Origin: *."""
        response = self.client.options(
            '/api/predictions/',
            HTTP_ORIGIN='http://localhost:5500',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")

    @mock.patch("api.views.load_json", side_effect=FileNotFoundError("Data file not found"))
    def test_get_assets_file_not_found(self, _mock_load):
        """Test GET /api/assets/ returns 404 when grid_assets.json is missing."""
        request = self.factory.get('/api/assets/')
        response = get_assets(request)
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.data)

    @mock.patch("api.views.run_risk_assessment", side_effect=FileNotFoundError("Prediction data missing"))
    def test_get_predictions_file_not_found(self, _mock_engine):
        """Test GET /api/predictions/ returns 404 when data files are missing."""
        request = self.factory.get('/api/predictions/')
        response = get_predictions(request)
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.data)


if __name__ == '__main__':
    unittest.main()
