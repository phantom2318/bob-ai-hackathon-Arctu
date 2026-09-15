"""
Risk Engine Service
Calculates composite risk scores for Gujarat power grid assets by combining
asset degradation metrics with weather impact multipliers.
Outputs city-level, zone-level risk assessments with crew pre-positioning directives.
"""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# Risk thresholds
HIGH_RISK_THRESHOLD = 75
MEDIUM_RISK_THRESHOLD = 40

# Recommended actions by risk category
RECOMMENDED_ACTIONS = {
    "HIGH": "Dispatch crew immediately for emergency inspection and preventive maintenance.",
    "MEDIUM": "Schedule maintenance within 48 hours. Monitor telemetry closely.",
    "LOW": "Continue routine monitoring. No immediate action required.",
}

HISTORY_ASSET_FACTOR = 0.12
HISTORY_CITY_FACTOR = 0.04
HISTORY_ZONE_FACTOR = 0.02

RISK_WEIGHTS = {
    "temperature": 0.35,
    "oil_level": 0.06,
    "grid_load": 0.05,
    "infrastructure_age": 0.04,
    "humidity": 0.02,
    "vibration": 0.14,
    "oil_quality": 0.18,
    "partial_discharge": 0.16,
}

# Root-cause detection weights (the dominant contributor drives the label)
METRIC_LABELS = {
    "temperature": "Thermal stress - elevated winding temperature",
    "vibration": "Mechanical degradation - abnormal vibration pattern",
    "oil_quality": "Dielectric breakdown risk - deteriorated oil quality",
    "partial_discharge": "Insulation defect - elevated partial discharge activity",
}


def load_json(filename):
    """
    Load a JSON file from the data directory.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains malformed or unparseable JSON.
    """
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Required data file '{filename}' was not found at: {filepath}")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise json.JSONDecodeError(
            f"Malformed JSON in file '{filename}': {exc.msg}",
            exc.doc,
            exc.pos
        ) from exc


def _number(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _risk_band(value, safe_min, critical_max):
    """Convert a physical reading into a bounded 0-100 risk contribution."""
    return max(0.0, min(100.0, ((value - safe_min) / (critical_max - safe_min)) * 100))


def _calculate_asset_degrade_score(telemetry):
    """Calculate a weighted 0-100 degradation score from asset telemetry."""
    if not isinstance(telemetry, dict):
        telemetry = {}

    components = _get_risk_components(telemetry)
    return sum(components[name] * weight for name, weight in RISK_WEIGHTS.items())


def _get_risk_components(telemetry):
    """Return normalized component risks for the dashboard and root-cause logic."""
    if not isinstance(telemetry, dict):
        telemetry = {}

    temperature = _number(telemetry.get("temperature_c"), 65.0)
    oil_level = _number(telemetry.get("oil_level_percent"), 92.0)
    grid_load = _number(telemetry.get("grid_load_percentage"), 65.0)
    infrastructure_age = _number(telemetry.get("infrastructure_age_years"), 12.0)
    humidity = _number(telemetry.get("humidity_percentage"), 55.0)
    vibration = _number(telemetry.get("vibration_mms"), 0.5)
    oil_quality = _number(telemetry.get("oil_quality_score"), 90.0)
    partial_discharge = _number(telemetry.get("partial_discharge_pc"), 20.0)

    return {
        "temperature": _risk_band(temperature, 60.0, 110.0),
        "oil_level": _risk_band(100.0 - oil_level, 0.0, 45.0),
        "grid_load": _risk_band(grid_load, 70.0, 110.0),
        "infrastructure_age": _risk_band(infrastructure_age, 10.0, 45.0),
        "humidity": _risk_band(humidity, 65.0, 100.0),
        "vibration": _risk_band(vibration, 0.5, 5.0),
        "oil_quality": _risk_band(100.0 - oil_quality, 0.0, 100.0),
        "partial_discharge": _risk_band(partial_discharge, 20.0, 500.0),
    }


def _identify_root_cause(telemetry):
    """Identify the dominant metric contributing to degradation."""
    if not isinstance(telemetry, dict):
        telemetry = {}

    components = _get_risk_components(telemetry)
    contributions = {
        "temperature": components["temperature"] * RISK_WEIGHTS["temperature"],
        "vibration": components["vibration"] * RISK_WEIGHTS["vibration"],
        "oil_quality": components["oil_quality"] * RISK_WEIGHTS["oil_quality"],
        "partial_discharge": components["partial_discharge"] * RISK_WEIGHTS["partial_discharge"],
    }
    dominant = max(contributions, key=contributions.get)
    return METRIC_LABELS[dominant]


def _get_weather_multiplier(storm_severity):
    """Weather Impact Multiplier = 1.0 + (storm_severity * 0.15)"""
    try:
        severity = float(storm_severity)
    except (TypeError, ValueError):
        severity = 1.0
    return 1.0 + (severity * 0.15)


def categorize_risk(score):
    """Categorize risk score into HIGH, MEDIUM, or LOW."""
    if score >= HIGH_RISK_THRESHOLD:
        return "HIGH"
    elif score >= MEDIUM_RISK_THRESHOLD:
        return "MEDIUM"
    else:
        return "LOW"


def _build_incident_index(incidents):
    """Index outage history by asset, city, and zone for fast scoring."""
    index = {"asset": {}, "city": {}, "zone": {}}
    if not isinstance(incidents, list):
        return index

    for incident in incidents:
        if not isinstance(incident, dict):
            continue
        for field in index:
            value = incident.get("asset_id" if field == "asset" else field)
            if value:
                index[field].setdefault(value, []).append(incident)
    return index


def _get_history_metrics(asset, incident_index):
    """Return prior outage impact and a bounded multiplier for one asset."""
    if not isinstance(asset, dict) or not isinstance(incident_index, dict):
        return {"count": 0, "downtime_hours": 0.0, "factor": 1.0}

    asset_id = asset.get("asset_id")
    city = asset.get("city")
    zone = asset.get("zone")
    asset_incidents = incident_index.get("asset", {}).get(asset_id, [])
    city_incidents = incident_index.get("city", {}).get(city, [])
    zone_incidents = incident_index.get("zone", {}).get(zone, [])
    incidents = list({id(item): item for item in asset_incidents + city_incidents + zone_incidents}.values())
    count = len(incidents)
    downtime = sum(float(item.get("downtime_hours", 0) or 0) for item in incidents)
    factor = 1.0
    if asset_incidents:
        factor += HISTORY_ASSET_FACTOR
    if city_incidents:
        factor += HISTORY_CITY_FACTOR
    if zone_incidents:
        factor += min(len(zone_incidents) * HISTORY_ZONE_FACTOR, 0.08)

    return {
        "count": count,
        "downtime_hours": round(downtime, 1),
        "factor": round(factor, 2),
    }


def _build_crew_directive(asset, category, root_cause, history):
    """
    Build a human-readable crew pre-positioning directive
    based on asset location and risk category.
    """
    if not isinstance(asset, dict):
        asset = {}

    city = asset.get("city", "Unknown City")
    zone = asset.get("zone", "Unknown Zone")
    grid_hub = asset.get("grid_hub", f"{zone} Grid Hub")
    asset_id = asset.get("asset_id", "UNKNOWN")
    incident_count = history.get("count", 0)
    downtime_hours = history.get("downtime_hours", 0.0)
    history_note = (
        f"Historical record: {incident_count} related outage(s), {downtime_hours:.1f} hours downtime."
        if incident_count
        else "No prior outage recorded for this asset, city, or zone."
    )

    if category == "HIGH":
        return (
            f"Dispatch from {grid_hub} to {asset_id} in {city} ({zone}); "
            f"isolate and repair {root_cause.lower()} in about 12 hours. "
            f"After electrical sign-off, crew returns to {grid_hub}; estimated power restoration: 14 hours. "
            f"{history_note}"
        )
    elif category == "MEDIUM":
        return (
            f"Stage crew at {grid_hub}, then inspect {asset_id} in {city} within 48 hours; "
            f"allow about 8 hours for {root_cause.lower()} repair. "
            f"Crew returns to {grid_hub} after sign-off; estimated power restoration: 10 hours. "
            f"{history_note}"
        )
    else:
        return (
            f"Keep {asset_id} under routine monitoring in {city}; no crew dispatch required. "
            f"If repair is triggered, route from {grid_hub}, allow about 4 hours, and restore power after sign-off. "
            f"{history_note}"
        )


def calculate_risk(asset, weather_by_zone, incident_index=None):
    """
    Calculate the composite risk score for a single asset.

    Parameters:
        asset (dict): Asset record with telemetry data.
        weather_by_zone (dict): Weather forecast keyed by zone name.

    Returns:
        dict: Risk assessment result for the asset including
              city_name, zone_name, and crew_preposition_zone.
    """
    if not isinstance(asset, dict):
        asset = {}

    telemetry = asset.get("telemetry", {})
    zone = asset.get("zone", "Unknown Zone")
    city = asset.get("city", "Unknown City")
    grid_hub = asset.get("grid_hub", f"{zone} Grid Hub")

    # Asset degradation
    degrade_score = _calculate_asset_degrade_score(telemetry)

    # Weather impact
    weather = weather_by_zone.get(zone, {}) if isinstance(weather_by_zone, dict) else {}
    storm_severity = weather.get("storm_severity_scale", 1) if isinstance(weather, dict) else 1
    weather_multiplier = _get_weather_multiplier(storm_severity)

    history = _get_history_metrics(asset, incident_index or {})

    # Final risk (capped at 100)
    risk_score = min(round(degrade_score * weather_multiplier * history["factor"], 2), 100.0)

    # Classification
    category = categorize_risk(risk_score)
    root_cause = _identify_root_cause(telemetry)

    # Crew pre-positioning directive
    crew_directive = _build_crew_directive(asset, category, root_cause, history)

    return {
        "asset_id": asset.get("asset_id", "UNKNOWN"),
        "city_name": city,
        "zone_name": zone,
        "risk_score": float(f"{risk_score:.2f}"),
        "risk_category": category,
        "root_cause": root_cause,
        "recommended_action": crew_directive,
        "next_action_description": crew_directive,
        "crew_preposition_zone": grid_hub,
        "historical_incident_count": history["count"],
        "historical_downtime_hours": history["downtime_hours"],
        "historical_outage_factor": history["factor"],
        "telemetry": {
            "temperature_c": float(telemetry.get("temperature_c", 0.0) or 0.0) if isinstance(telemetry.get("temperature_c"), (int, float)) else 0.0,
            "vibration_mms": float(telemetry.get("vibration_mms", 0.0) or 0.0) if isinstance(telemetry.get("vibration_mms"), (int, float)) else 0.0,
            "oil_quality_score": float(telemetry.get("oil_quality_score", 0.0) or 0.0) if isinstance(telemetry.get("oil_quality_score"), (int, float)) else 0.0,
            "partial_discharge_pc": float(telemetry.get("partial_discharge_pc", 0.0) or 0.0) if isinstance(telemetry.get("partial_discharge_pc"), (int, float)) else 0.0,
            "oil_level_percent": round(_number(telemetry.get("oil_level_percent"), 92.0), 2),
            "grid_load_percentage": round(_number(telemetry.get("grid_load_percentage"), 65.0), 2),
            "infrastructure_age_years": round(_number(telemetry.get("infrastructure_age_years"), 12.0), 2),
            "humidity_percentage": round(_number(telemetry.get("humidity_percentage"), 55.0), 2),
        },
        "degrade_score": round(degrade_score, 2),
        "storm_severity": storm_severity,
        "weather_multiplier": round(weather_multiplier, 2),
    }


def run_risk_assessment(
    assets_file="grid_assets.json",
    weather_file="weather_forecast.json",
    incidents_file="incident_logs.json",
):
    """
    Run the full risk assessment pipeline.

    Loads asset and weather data from JSON files, scores every asset,
    ranks them by severity, and returns the sorted results.

    Parameters:
        assets_file (str): Filename of the assets JSON file.
        weather_file (str): Filename of the weather forecast JSON file.

    Returns:
        list[dict]: Sorted list of risk assessments (highest risk first).

    Raises:
        FileNotFoundError: If asset or weather file is missing.
        json.JSONDecodeError: If asset or weather file contains malformed JSON.
        ValueError: If file content structure is invalid (not a list).
    """
    assets = load_json(assets_file)
    weather_data = load_json(weather_file)
    incidents = load_json(incidents_file)

    if not isinstance(assets, list):
        raise ValueError(f"Expected a list of assets in '{assets_file}', got {type(assets).__name__}")
    if not isinstance(weather_data, list):
        raise ValueError(f"Expected a list of weather forecasts in '{weather_file}', got {type(weather_data).__name__}")
    if not isinstance(incidents, list):
        raise ValueError(f"Expected a list of incident records in '{incidents_file}', got {type(incidents).__name__}")

    # Index weather by zone for O(1) lookup
    weather_by_zone = {}
    for entry in weather_data:
        if isinstance(entry, dict) and "zone" in entry:
            weather_by_zone[entry["zone"]] = entry.get("forecast", {})

    incident_index = _build_incident_index(incidents)

    results = []
    for asset in assets:
        if not isinstance(asset, dict) or "asset_id" not in asset:
            continue
        result = calculate_risk(asset, weather_by_zone, incident_index)
        results.append(result)

    # Sort by risk_score descending and assign urgency rank
    results.sort(key=lambda r: r["risk_score"], reverse=True)
    for rank, result in enumerate(results, start=1):
        result["urgency_rank"] = rank

    return results


if __name__ == "__main__":
    assessments = run_risk_assessment()
    print(json.dumps(assessments, indent=4))
