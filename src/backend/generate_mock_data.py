"""
Mock Data Generator for GridGuard
Generates Gujarat-specific grid asset telemetry, weather forecasts,
and historical incident records mapped to real power zones and cities.
"""

import json
import os
import random
import uuid
from datetime import datetime, timedelta

# Gujarat Power Grid Zone Definitions
GUJARAT_ZONES = {
    "Central Gujarat": {
        "cities": ["Ahmedabad", "Vadodara", "Gandhinagar", "Anand"],
        "prefix": "CG",
        "grid_hub": "Vadodara Grid Hub",
    },
    "South Gujarat": {
        "cities": ["Surat", "Navsari", "Vapi", "Bharuch"],
        "prefix": "SG",
        "grid_hub": "Surat Grid Hub",
    },
    "Saurashtra": {
        "cities": ["Rajkot", "Bhavnagar", "Jamnagar", "Junagadh"],
        "prefix": "SAU",
        "grid_hub": "Rajkot Grid Hub",
    },
    "North Gujarat": {
        "cities": ["Mehsana", "Palanpur", "Patan"],
        "prefix": "NG",
        "grid_hub": "Mehsana Grid Hub",
    },
    "Kutch": {
        "cities": ["Bhuj", "Gandhidham"],
        "prefix": "KCH",
        "grid_hub": "Bhuj Grid Hub",
    },
}

# City code mapping for substation IDs
CITY_CODES = {
    "Ahmedabad": "AHM",
    "Vadodara": "VDR",
    "Gandhinagar": "GDN",
    "Anand": "AND",
    "Surat": "SRT",
    "Navsari": "NVS",
    "Vapi": "VPI",
    "Bharuch": "BRC",
    "Rajkot": "RJK",
    "Bhavnagar": "BHV",
    "Jamnagar": "JMN",
    "Junagadh": "JND",
    "Mehsana": "MHS",
    "Palanpur": "PLN",
    "Patan": "PTN",
    "Bhuj": "BHJ",
    "Gandhidham": "GDM",
}

# Substation types for realistic naming
SUBSTATION_TYPES = ["SUBSTATION", "GRID-XFMR", "DIST-XFMR"]

CITY_ASSET_COUNTS = {
    city: 3
    for city in [
        "Ahmedabad", "Vadodara", "Gandhinagar", "Anand", "Surat",
        "Navsari", "Vapi", "Bharuch", "Rajkot", "Bhavnagar",
        "Jamnagar", "Junagadh", "Mehsana", "Palanpur", "Patan",
    ]
}
CITY_ASSET_COUNTS.update({"Bhuj": 2, "Gandhidham": 2})


def generate_grid_assets():
    """
    Generate transformer and substation assets mapped to Gujarat cities.
    Each city gets 2-3 substations with realistic telemetry.
    """
    random.seed(20260914)
    transformers = []

    for zone_name, zone_info in GUJARAT_ZONES.items():
        for city in zone_info["cities"]:
            code = CITY_CODES[city]
            num_substations = CITY_ASSET_COUNTS[city]

            for i in range(1, num_substations + 1):
                sub_type = random.choice(SUBSTATION_TYPES)
                asset_id = f"{code}-{sub_type}-{i:02d}"

                # Use correlated, region-aware values instead of independent random noise.
                if zone_name in ("Kutch", "Saurashtra"):
                    temperature_range = (72.0, 101.0)
                    humidity_range = (38.0, 68.0)
                    load_range = (62.0, 94.0)
                elif zone_name == "South Gujarat":
                    temperature_range = (66.0, 94.0)
                    humidity_range = (70.0, 96.0)
                    load_range = (68.0, 98.0)
                elif zone_name == "North Gujarat":
                    temperature_range = (62.0, 88.0)
                    humidity_range = (35.0, 62.0)
                    load_range = (55.0, 88.0)
                else:
                    temperature_range = (64.0, 92.0)
                    humidity_range = (48.0, 78.0)
                    load_range = (60.0, 92.0)

                age_years = random.uniform(5.0, 38.0)
                grid_load = random.uniform(*load_range)
                temperature = random.uniform(*temperature_range) + max(grid_load - 80.0, 0.0) * 0.08
                humidity = random.uniform(*humidity_range)
                oil_level = max(58.0, 99.0 - age_years * 0.45 - random.uniform(0.0, 7.0))
                oil_quality = max(42.0, 99.0 - age_years * 0.9 - random.uniform(0.0, 14.0))
                vibration = min(4.8, 0.25 + age_years / 28.0 + random.uniform(0.0, 1.8))
                partial_discharge = min(460.0, 12.0 + age_years * 4.2 + random.uniform(0.0, 115.0))

                # Keep three clearly different high-risk assets in the fixture.
                high_risk_profiles = {
                    "AHM-DIST-XFMR-01": (108.0, 4.6, 18.0, 470.0),
                    "SRT-DIST-XFMR-01": (103.0, 4.2, 22.0, 430.0),
                    "RJK-GRID-XFMR-01": (106.0, 4.4, 15.0, 450.0),
                }
                if asset_id in high_risk_profiles:
                    temperature, vibration, oil_quality, partial_discharge = high_risk_profiles[asset_id]
                else:
                    # Keep normal assets varied, but below the emergency band.
                    temperature = min(temperature, 88.0)
                    vibration = min(vibration, 2.2)
                    oil_quality = max(oil_quality, 65.0)
                    partial_discharge = min(partial_discharge, 200.0)
                    age_years = min(age_years, 25.0)

                transformers.append({
                    "asset_id": asset_id,
                    "type": "transformer",
                    "city": city,
                    "zone": zone_name,
                    "grid_hub": zone_info["grid_hub"],
                    "telemetry": {
                        "temperature_c": round(temperature, 2),
                        "oil_level_percent": round(oil_level, 2),
                        "grid_load_percentage": round(grid_load, 2),
                        "infrastructure_age_years": round(age_years, 2),
                        "humidity_percentage": round(humidity, 2),
                        "vibration_mms": round(vibration, 2),
                        "oil_quality_score": round(oil_quality, 2),
                        "partial_discharge_pc": round(partial_discharge, 2),
                    },
                })

    return transformers


def generate_weather_forecasts():
    """
    Generate realistic weather forecasts for Gujarat's 5 power zones.
    Reflects regional climate patterns: monsoon in South Gujarat,
    extreme heat in Kutch/Saurashtra, moderate elsewhere.
    """
    weather_data = []

    zone_weather_profiles = {
        "Central Gujarat": {
            "ambient_temperature_range": (27.0, 36.0),
            "humidity_range": (48.0, 78.0),
            "wind_speed_range": (5.0, 55.0),
            "precipitation_range": (0.0, 35.0),
            "storm_severity_range": (1, 3),
            "condition": "Partly cloudy with occasional thundershowers",
        },
        "South Gujarat": {
            "ambient_temperature_range": (25.0, 33.0),
            "humidity_range": (72.0, 96.0),
            "wind_speed_range": (15.0, 90.0),
            "precipitation_range": (10.0, 50.0),
            "storm_severity_range": (2, 5),
            "condition": "Heavy monsoon rainfall with gusty winds",
        },
        "Saurashtra": {
            "ambient_temperature_range": (29.0, 39.0),
            "humidity_range": (42.0, 70.0),
            "wind_speed_range": (10.0, 75.0),
            "precipitation_range": (0.0, 25.0),
            "storm_severity_range": (1, 4),
            "condition": "Hot and dry with coastal wind surges",
        },
        "North Gujarat": {
            "ambient_temperature_range": (26.0, 38.0),
            "humidity_range": (35.0, 62.0),
            "wind_speed_range": (5.0, 45.0),
            "precipitation_range": (0.0, 20.0),
            "storm_severity_range": (1, 3),
            "condition": "Clear skies with moderate temperatures",
        },
        "Kutch": {
            "ambient_temperature_range": (30.0, 42.0),
            "humidity_range": (28.0, 58.0),
            "wind_speed_range": (10.0, 100.0),
            "precipitation_range": (0.0, 15.0),
            "storm_severity_range": (1, 5),
            "condition": "Extreme heat with dust storms and high winds",
        },
    }

    for zone_name, profile in zone_weather_profiles.items():
        weather_data.append({
            "zone": zone_name,
            "forecast": {
                "ambient_temperature_c": round(random.uniform(*profile["ambient_temperature_range"]), 2),
                "humidity_percentage": round(random.uniform(*profile["humidity_range"]), 2),
                "wind_speed_kmh": round(
                    random.uniform(*profile["wind_speed_range"]), 2
                ),
                "precipitation_mm": round(
                    random.uniform(*profile["precipitation_range"]), 2
                ),
                "storm_severity_scale": random.randint(
                    *profile["storm_severity_range"]
                ),
                "condition": profile["condition"],
            },
        })

    return weather_data


def generate_incident_logs(assets):
    """
    Generate 10 historical failure records linked to real asset IDs.
    """
    failure_types = [
        "Overheating",
        "Insulation Failure",
        "Bushing Failure",
        "Oil Leak",
        "Winding Fault",
        "Lightning Strike Damage",
        "Transformer Explosion",
        "Cooling System Failure",
    ]

    incident_logs = []
    sampled_assets = random.sample(assets, min(10, len(assets)))

    for asset in sampled_assets:
        incident_logs.append({
            "incident_id": f"INC-{uuid.uuid4().hex[:8].upper()}",
            "asset_id": asset["asset_id"],
            "city": asset["city"],
            "zone": asset["zone"],
            "date": (
                datetime.now() - timedelta(days=random.randint(1, 365))
            ).strftime("%Y-%m-%d"),
            "failure_type": random.choice(failure_types),
            "downtime_hours": round(random.uniform(1.0, 72.0), 1),
            "affected_consumers": random.randint(500, 50000),
        })

    return incident_logs


def generate_mock_data():
    """Main entry point: generates all 3 JSON files into src/backend/data/."""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    # 1. Grid Assets
    assets = generate_grid_assets()
    with open(os.path.join(data_dir, "grid_assets.json"), "w", encoding="utf-8") as f:
        json.dump(assets, f, indent=4, ensure_ascii=False)
    print(f"  Generated {len(assets)} grid assets across 5 Gujarat zones.")

    # 2. Weather Forecasts
    weather = generate_weather_forecasts()
    with open(os.path.join(data_dir, "weather_forecast.json"), "w", encoding="utf-8") as f:
        json.dump(weather, f, indent=4, ensure_ascii=False)
    print(f"  Generated weather forecasts for {len(weather)} zones.")

    # 3. Incident Logs
    incidents = generate_incident_logs(assets)
    with open(os.path.join(data_dir, "incident_logs.json"), "w", encoding="utf-8") as f:
        json.dump(incidents, f, indent=4, ensure_ascii=False)
    print(f"  Generated {len(incidents)} historical incident records.")


if __name__ == "__main__":
    print("GridGuard AI - Gujarat Power Grid Mock Data Generator")
    print("=" * 55)
    generate_mock_data()
    print("=" * 55)
    print("Successfully generated mock data in src/backend/data/")
