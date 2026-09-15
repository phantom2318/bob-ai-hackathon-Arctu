"""
Unit tests for the Risk Engine service.
Verifies risk scoring bounds under high-temperature and high-storm scenarios.
"""

import json
import os
import sys
import unittest

# Add the backend directory to the path so we can import the service
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.risk_engine import (
    DATA_DIR,
    _calculate_asset_degrade_score,
    _get_weather_multiplier,
    _identify_root_cause,
    calculate_risk,
    categorize_risk,
    load_json,
    run_risk_assessment,
)


class TestAssetDegradeScore(unittest.TestCase):
    """Tests for the asset degradation score formula."""

    def test_minimum_degradation(self):
        """Lowest-risk telemetry should produce a low degrade score."""
        telemetry = {
            "temperature_c": 50,
            "vibration_mms": 0.1,
            "oil_quality_score": 100,
            "partial_discharge_pc": 10,
        }
        score = _calculate_asset_degrade_score(telemetry)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_maximum_degradation(self):
        """Highest-risk telemetry should produce a high degrade score."""
        telemetry = {
            "temperature_c": 110,
            "vibration_mms": 5.0,
            "oil_quality_score": 0,
            "partial_discharge_pc": 500,
        }
        score = _calculate_asset_degrade_score(telemetry)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


class TestWeatherMultiplier(unittest.TestCase):
    """Tests for the weather impact multiplier."""

    def test_calm_weather(self):
        """Storm severity 1 gives a mild multiplier."""
        self.assertAlmostEqual(_get_weather_multiplier(1), 1.15)

    def test_severe_storm(self):
        """Storm severity 5 gives the maximum multiplier."""
        self.assertAlmostEqual(_get_weather_multiplier(5), 1.75)


class TestCategorizeRisk(unittest.TestCase):
    """Tests for risk category classification."""

    def test_high_risk(self):
        self.assertEqual(categorize_risk(75), "HIGH")
        self.assertEqual(categorize_risk(100), "HIGH")

    def test_medium_risk(self):
        self.assertEqual(categorize_risk(40), "MEDIUM")
        self.assertEqual(categorize_risk(74), "MEDIUM")

    def test_low_risk(self):
        self.assertEqual(categorize_risk(0), "LOW")
        self.assertEqual(categorize_risk(39), "LOW")

    def test_boundary_high_medium(self):
        self.assertEqual(categorize_risk(74.99), "MEDIUM")
        self.assertEqual(categorize_risk(75.0), "HIGH")

    def test_boundary_medium_low(self):
        self.assertEqual(categorize_risk(39.99), "LOW")
        self.assertEqual(categorize_risk(40.0), "MEDIUM")


class TestHighTemperatureScenario(unittest.TestCase):
    """Verifies that a high-temperature asset is flagged as HIGH risk."""

    def test_high_temp_produces_high_risk(self):
        asset = {
            "asset_id": "AHM-SUBSTATION-01",
            "city": "Ahmedabad",
            "zone": "Central Gujarat",
            "grid_hub": "Vadodara Grid Hub",
            "telemetry": {
                "temperature_c": 110,
                "vibration_mms": 4.0,
                "oil_quality_score": 10,
                "partial_discharge_pc": 400,
            },
        }
        weather_by_zone = {
            "Central Gujarat": {"storm_severity_scale": 3},
        }
        result = calculate_risk(asset, weather_by_zone)

        self.assertGreaterEqual(result["risk_score"], 75)
        self.assertEqual(result["risk_category"], "HIGH")
        self.assertEqual(result["city_name"], "Ahmedabad")
        self.assertEqual(result["zone_name"], "Central Gujarat")
        self.assertIn("Vadodara Grid Hub", result["crew_preposition_zone"])
        self.assertIn("asset_id", result)
        self.assertIn("recommended_action", result)
        self.assertIn("root_cause", result)

    def test_high_temp_root_cause_is_thermal(self):
        """When temperature dominates, root cause should be thermal stress."""
        asset = {
            "asset_id": "TRF-TEST-HT2",
            "zone": "Zone-B",
            "telemetry": {
                "temperature_c": 110,
                "vibration_mms": 0.1,
                "oil_quality_score": 95,
                "partial_discharge_pc": 10,
            },
        }
        weather_by_zone = {"Zone-B": {"storm_severity_scale": 1}}
        result = calculate_risk(asset, weather_by_zone)

        self.assertIn("Thermal stress", result["root_cause"])


class TestHighStormScenario(unittest.TestCase):
    """Verifies that a severe storm amplifies risk into HIGH territory."""

    def test_storm_pushes_medium_to_high(self):
        """A borderline-medium asset should be pushed to HIGH by a severe storm."""
        asset = {
            "asset_id": "TRF-TEST-STORM",
            "zone": "Zone-C",
            "telemetry": {
                "temperature_c": 85,
                "vibration_mms": 2.5,
                "oil_quality_score": 30,
                "partial_discharge_pc": 200,
            },
        }
        # Without storm (severity=1): degrade * 1.15
        weather_calm = {"Zone-C": {"storm_severity_scale": 1}}
        result_calm = calculate_risk(asset, weather_calm)

        # With max storm (severity=5): degrade * 1.75
        weather_severe = {"Zone-C": {"storm_severity_scale": 5}}
        result_severe = calculate_risk(asset, weather_severe)

        self.assertGreater(result_severe["risk_score"], result_calm["risk_score"])
        self.assertEqual(result_severe["risk_category"], "HIGH")

    def test_risk_score_capped_at_100(self):
        """Even worst-case inputs should never exceed a score of 100."""
        asset = {
            "asset_id": "TRF-TEST-CAP",
            "zone": "Zone-A",
            "telemetry": {
                "temperature_c": 110,
                "vibration_mms": 5.0,
                "oil_quality_score": 0,
                "partial_discharge_pc": 500,
            },
        }
        weather_by_zone = {"Zone-A": {"storm_severity_scale": 5}}
        result = calculate_risk(asset, weather_by_zone)

        self.assertLessEqual(result["risk_score"], 100)


class TestOutputStructure(unittest.TestCase):
    """Verifies the output JSON structure per asset."""

    def test_output_keys(self):
        asset = {
            "asset_id": "TRF-TEST-STRUCT",
            "city": "Rajkot",
            "zone": "Saurashtra",
            "grid_hub": "Rajkot Grid Hub",
            "telemetry": {
                "temperature_c": 70,
                "vibration_mms": 1.0,
                "oil_quality_score": 60,
                "partial_discharge_pc": 100,
            },
        }
        weather_by_zone = {"Saurashtra": {"storm_severity_scale": 2}}
        result = calculate_risk(asset, weather_by_zone)

        expected_keys = {
            "asset_id",
            "city_name",
            "zone_name",
            "risk_score",
            "risk_category",
            "root_cause",
            "recommended_action",
            "crew_preposition_zone",
            "next_action_description",
            "historical_incident_count",
            "historical_downtime_hours",
            "historical_outage_factor",
            "telemetry",
            "degrade_score",
            "storm_severity",
            "weather_multiplier",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_risk_score_is_numeric(self):
        asset = {
            "asset_id": "TRF-TEST-NUM",
            "zone": "Zone-B",
            "telemetry": {
                "temperature_c": 60,
                "vibration_mms": 0.5,
                "oil_quality_score": 80,
                "partial_discharge_pc": 50,
            },
        }
        weather_by_zone = {"Zone-B": {"storm_severity_scale": 1}}
        result = calculate_risk(asset, weather_by_zone)

        self.assertIsInstance(result["risk_score"], (int, float))
        self.assertGreaterEqual(result["risk_score"], 0)
        self.assertLessEqual(result["risk_score"], 100)

    def test_requested_telemetry_changes_risk(self):
        baseline = {
            "temperature_c": 70,
            "oil_level_percent": 96,
            "grid_load_percentage": 60,
            "infrastructure_age_years": 8,
            "humidity_percentage": 50,
            "vibration_mms": 0.5,
            "oil_quality_score": 90,
            "partial_discharge_pc": 20,
        }
        stressed = dict(baseline)
        stressed.update({
            "temperature_c": 105,
            "oil_level_percent": 62,
            "grid_load_percentage": 104,
            "infrastructure_age_years": 36,
            "humidity_percentage": 94,
        })
        weather = {"Zone-B": {"storm_severity_scale": 1}}
        low = calculate_risk({"asset_id": "LOW", "zone": "Zone-B", "telemetry": baseline}, weather)
        high = calculate_risk({"asset_id": "HIGH", "zone": "Zone-B", "telemetry": stressed}, weather)
        self.assertGreater(high["risk_score"], low["risk_score"])
        self.assertEqual(high["risk_score"], round(high["risk_score"], 2))


class TestRiskEngineExceptionHandling(unittest.TestCase):
    """Verifies exception handling for missing, malformed, or corrupt JSON data."""

    def test_missing_file_raises_filenotfound(self):
        """load_json should raise FileNotFoundError with a clear message for nonexistent files."""
        with self.assertRaises(FileNotFoundError) as ctx:
            load_json("nonexistent_data_file_9999.json")
        self.assertIn("nonexistent_data_file_9999.json", str(ctx.exception))

    def test_malformed_json_raises_jsondecodeerror(self):
        """load_json should raise json.JSONDecodeError when parsing corrupted JSON."""
        bad_filename = "test_corrupt_temp.json"
        bad_filepath = os.path.join(DATA_DIR, bad_filename)
        try:
            with open(bad_filepath, "w", encoding="utf-8") as f:
                f.write("{ invalid_json_syntax: true, unclosed }")

            with self.assertRaises(json.JSONDecodeError) as ctx:
                load_json(bad_filename)
            self.assertIn(bad_filename, str(ctx.exception))
        finally:
            if os.path.exists(bad_filepath):
                os.remove(bad_filepath)

    def test_non_list_json_raises_valueerror(self):
        """run_risk_assessment should raise ValueError if JSON root is not a list."""
        dict_filename = "test_dict_temp.json"
        dict_filepath = os.path.join(DATA_DIR, dict_filename)
        try:
            with open(dict_filepath, "w", encoding="utf-8") as f:
                json.dump({"error": "not a list"}, f)

            with self.assertRaises(ValueError) as ctx:
                run_risk_assessment(assets_file=dict_filename)
            self.assertIn("Expected a list of assets", str(ctx.exception))
        finally:
            if os.path.exists(dict_filepath):
                os.remove(dict_filepath)

    def test_missing_and_corrupt_telemetry_tolerated(self):
        """calculate_risk should tolerate empty, None, or string telemetry values using safe defaults."""
        asset_corrupt = {
            "asset_id": "TRF-CORRUPT",
            "zone": "Zone-A",
            "telemetry": {
                "temperature_c": "invalid_temp",
                "vibration_mms": None,
                # oil_quality_score and partial_discharge_pc completely missing
            }
        }
        weather = {"Zone-A": {"storm_severity_scale": "corrupt_scale"}}
        result = calculate_risk(asset_corrupt, weather)

        self.assertEqual(result["asset_id"], "TRF-CORRUPT")
        self.assertIsInstance(result["risk_score"], (int, float))
        self.assertIn(result["risk_category"], ["HIGH", "MEDIUM", "LOW"])
        self.assertIn("root_cause", result)


if __name__ == "__main__":
    unittest.main()
