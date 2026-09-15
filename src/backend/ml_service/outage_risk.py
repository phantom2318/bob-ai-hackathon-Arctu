"""
ml_service/outage_risk.py

Composite Power Outage Risk Engine
===================================
Combines live satellite weather metrics (rainfall mm, pixel intensity as a
proxy for storm cloud cover) with historical infrastructure telemetry from
grid_assets.json to produce a 0–100 outage risk percentage and a labelled
risk tier for a given Gujarat city.

Location Fallback Strategy
---------------------------
If the requested city has no assets in the JSON dataset, the engine finds the
geographically nearest city (Haversine distance against GUJARAT_LOCATIONS) that
does have assets, and uses that city's infrastructure profile instead.  The
`risk_source` key in the return dict tells the caller whether the match was
exact or a proximity fallback.

Public API
----------
    from ml_service.outage_risk import assess_outage_risk

    result = assess_outage_risk(
        city_name        = "Junagadh",
        predicted_mm     = 12.5,
        pixel_intensity  = 847.3,
    )
    # result keys:
    #   risk_score_pct  : int   0–100
    #   risk_label      : str   "Low Risk" | "Medium Risk" | "High Alert"
    #   risk_source     : str   "Junagadh Core Dataset"
    #                        or "Nearest Proximity Fallback [Rajkot]"
    #   matched_city    : str   canonical city name used for infrastructure lookup
    #   asset_count     : int   number of assets averaged for the profile
"""

import json
import math
import os

# ---------------------------------------------------------------------------
# Path to JSON data — anchored relative to this file (backend/ml_service/)
# ---------------------------------------------------------------------------
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_ASSETS_PATH = os.path.normpath(os.path.join(_DATA_DIR, "grid_assets.json"))

# ---------------------------------------------------------------------------
# Gujarat city coordinates (mirrors predictor.GUJARAT_LOCATIONS — kept local
# here so outage_risk.py has no import dependency on predictor.py)
# ---------------------------------------------------------------------------
_CITY_COORDS = {
    # Central Gujarat
    "Ahmedabad":   (23.0225, 72.5714),
    "Vadodara":    (22.3072, 73.1812),
    "Anand":       (22.5645, 72.9289),
    "Gandhinagar": (23.2156, 72.6369),
    # South Gujarat
    "Surat":       (21.1702, 72.8311),
    "Bharuch":     (21.7051, 72.9959),
    "Navsari":     (20.9467, 72.9520),
    "Vapi":        (20.3719, 72.9068),
    "Valsad":      (20.5992, 72.9342),
    # Saurashtra
    "Rajkot":      (22.3039, 70.8022),
    "Bhavnagar":   (21.7645, 72.1519),
    "Jamnagar":    (22.4707, 70.0577),
    "Junagadh":    (21.5222, 70.4579),
    # North Gujarat
    "Mehsana":     (23.5880, 72.3693),
    "Palanpur":    (24.1725, 72.4382),
    "Patan":       (23.8493, 72.1266),
    # Kutch
    "Bhuj":        (23.2420, 69.6669),
    "Gandhidham":  (23.0753, 70.1337),
}

# ---------------------------------------------------------------------------
# Risk scoring weights
# ---------------------------------------------------------------------------
# Infrastructure degradation component (0–100 each, weighted sum → 0–100)
_INFRA_WEIGHTS = {
    "partial_discharge_pc":    0.30,   # dominant failure predictor
    "infrastructure_age_years": 0.22,  # long-lived assets are more fragile
    "vibration_mms":           0.18,   # mechanical stress
    "oil_quality_score":       0.15,   # dielectric integrity (inverted)
    "grid_load_percentage":    0.15,   # operational stress
}

# Storm / weather component weight vs infrastructure weight in final score
_WEATHER_WEIGHT = 0.40
_INFRA_WEIGHT   = 0.60

# ---------------------------------------------------------------------------
# Normalisation band definitions  (safe_min → critical_max → 0–100 risk band)
# ---------------------------------------------------------------------------
_BANDS = {
    "partial_discharge_pc":    (20.0,  500.0),
    "infrastructure_age_years":(10.0,   45.0),
    "vibration_mms":           (0.5,     5.0),
    "oil_quality_score":       (0.0,   100.0),   # inverted below
    "grid_load_percentage":    (70.0,  110.0),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in km between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _band(value: float, safe_min: float, critical_max: float) -> float:
    """Map a reading to a 0–100 risk band; clamp at boundaries."""
    span = critical_max - safe_min
    if span <= 0:
        return 0.0
    return max(0.0, min(100.0, (value - safe_min) / span * 100.0))


def _load_assets() -> list:
    """Load grid_assets.json; returns empty list on any IO/parse failure."""
    try:
        with open(_ASSETS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def _build_city_profiles(assets: list) -> dict:
    """
    Aggregate per-city average telemetry from the asset list.
    Returns { city_name: {telemetry field averages, asset_count} }.
    """
    buckets: dict = {}
    for asset in assets:
        city = asset.get("city", "")
        tel  = asset.get("telemetry") or {}
        if not city or not isinstance(tel, dict):
            continue
        if city not in buckets:
            buckets[city] = {k: [] for k in _INFRA_WEIGHTS}
            buckets[city]["_count"] = 0
        for field in _INFRA_WEIGHTS:
            val = tel.get(field)
            if val is not None:
                try:
                    buckets[city][field].append(float(val))
                except (TypeError, ValueError):
                    pass
        buckets[city]["_count"] += 1

    profiles: dict = {}
    for city, data in buckets.items():
        avg = {}
        for field in _INFRA_WEIGHTS:
            vals = data[field]
            avg[field] = sum(vals) / len(vals) if vals else 0.0
        profiles[city] = {"telemetry": avg, "asset_count": data["_count"]}
    return profiles


def _infra_risk_score(tel_avg: dict) -> float:
    """
    Compute a 0–100 infrastructure degradation score from averaged telemetry.
    oil_quality_score is inverted: lower quality = higher risk.
    """
    score = 0.0
    for field, weight in _INFRA_WEIGHTS.items():
        val = tel_avg.get(field, 0.0)
        safe_min, crit_max = _BANDS[field]
        if field == "oil_quality_score":
            # Invert: quality 100 = 0 risk, quality 0 = 100 risk
            component = _band(100.0 - val, 0.0, 100.0)
        else:
            component = _band(val, safe_min, crit_max)
        score += component * weight
    return min(score, 100.0)


def _weather_risk_score(predicted_mm: float, pixel_intensity: float) -> float:
    """
    Derive a 0–100 storm severity score from satellite weather outputs only
    (no live API data).  Used as fallback when live_weather is unavailable.

    - Rainfall band: 0 mm → 0, ≥ 65 mm → 100 (maps the 5-tier rainfall scale)
    - Pixel intensity band: low brightness = clear (INSAT TIR bands: higher DN
      values correspond to warmer/clearer surfaces; dense cloud cover produces
      lower DN).  Band 300–900: lower = stormier.
    - Combined as a simple average.
    """
    rain_score  = _band(predicted_mm, 0.0, 65.0)

    # Invert pixel intensity: low DN (cold cloud tops) = high storm risk
    pixel_score = _band(900.0 - max(0.0, min(900.0, pixel_intensity)), 0.0, 600.0)

    return (rain_score + pixel_score) / 2.0


def _live_weather_risk_score(
    predicted_mm: float,
    pixel_intensity: float,
    live_weather: dict,
) -> float:
    """
    Enhanced storm severity score that blends satellite outputs with live
    Open-Meteo ambient conditions.

    Live signals added (each normalised to 0–100 contribution):
        temperature_c  — extreme heat amplifies transformer thermal stress
                         band: 25 °C (safe) → 50 °C (critical)
        humidity_pct   — high humidity accelerates insulation degradation
                         band: 60 % (safe) → 100 %
        wind_speed_kmh — high wind speeds compound mechanical load
                         band: 20 km/h (safe) → 90 km/h

    Weighting: satellite signals 55 %, live ambient signals 45 %.
    """
    # Satellite component (same as base scorer)
    rain_score  = _band(predicted_mm, 0.0, 65.0)
    pixel_score = _band(900.0 - max(0.0, min(900.0, pixel_intensity)), 0.0, 600.0)
    satellite   = (rain_score + pixel_score) / 2.0

    # Live ambient component — each term defaults to 0 if None
    temp  = live_weather.get("ambient_temp_c")
    humid = live_weather.get("humidity_pct")
    wind  = live_weather.get("wind_speed_kmh")

    temp_score  = _band(float(temp),  25.0, 50.0) if temp  is not None else 0.0
    humid_score = _band(float(humid), 60.0, 100.0) if humid is not None else 0.0
    wind_score  = _band(float(wind),  20.0, 90.0)  if wind  is not None else 0.0

    # Average only the terms that actually have data
    live_terms = [s for s, v in [
        (temp_score, temp), (humid_score, humid), (wind_score, wind)
    ] if v is not None]
    live_ambient = sum(live_terms) / len(live_terms) if live_terms else 0.0

    return (0.55 * satellite) + (0.45 * live_ambient)


def _find_nearest_city(city_name: str, available_cities: set) -> str:
    """
    Return the city in ``available_cities`` nearest to ``city_name`` by
    Haversine distance.  Falls back to the first available city if neither
    the query city nor any available city has known coordinates.
    """
    if city_name not in _CITY_COORDS:
        return next(iter(available_cities))

    query_lat, query_lon = _CITY_COORDS[city_name]
    best_city, best_dist = None, float("inf")

    for candidate in available_cities:
        if candidate not in _CITY_COORDS:
            continue
        clat, clon = _CITY_COORDS[candidate]
        dist = _haversine_km(query_lat, query_lon, clat, clon)
        if dist < best_dist:
            best_dist, best_city = dist, candidate

    return best_city or next(iter(available_cities))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assess_outage_risk(
    city_name: str,
    predicted_mm: float,
    pixel_intensity: float,
    live_weather: dict = None,
) -> dict:
    """
    Calculate a composite Power Outage Risk score for a Gujarat city.

    Parameters
    ----------
    city_name : str
        Requested city (case-sensitive, must match GUJARAT_LOCATIONS spelling).
    predicted_mm : float
        ML-predicted rainfall in mm from the satellite image.
    pixel_intensity : float
        Raw pixel DN value extracted from the satellite image.
    live_weather : dict, optional
        Output of fetch_live_weather() — if provided and source=="live", the
        ambient temperature, humidity, and wind speed are incorporated into the
        weather risk score via _live_weather_risk_score().  If None or source
        is "unavailable", falls back to satellite-only scoring.

    Returns
    -------
    dict with keys:
        risk_score_pct  : int   Composite outage risk 0–100
        risk_label      : str   "Low Risk" | "Medium Risk" | "High Alert"
        risk_source     : str   Source attribution string for UI badge
        matched_city    : str   City profile actually used
        asset_count     : int   Assets averaged for the infrastructure profile
        weather_mode    : str   "live+satellite" | "satellite-only"
    """
    assets   = _load_assets()
    profiles = _build_city_profiles(assets)

    # Decide which weather scorer to use
    use_live = (
        isinstance(live_weather, dict)
        and live_weather.get("source") == "live"
    )
    if use_live:
        weather_score = _live_weather_risk_score(predicted_mm, pixel_intensity, live_weather)
        weather_mode  = "live+satellite"
    else:
        weather_score = _weather_risk_score(predicted_mm, pixel_intensity)
        weather_mode  = "satellite-only"

    # ── City lookup with proximity fallback ─────────────────────────────────
    if city_name in profiles:
        matched_city = city_name
        is_fallback  = False
    elif profiles:
        matched_city = _find_nearest_city(city_name, set(profiles.keys()))
        is_fallback  = True
    else:
        # No asset data at all — return a weather-only estimate
        risk_pct = int(round(weather_score))
        return {
            "risk_score_pct": risk_pct,
            "risk_label":     _label(risk_pct),
            "risk_source":    "Weather Data Only (no infrastructure dataset)",
            "matched_city":   city_name,
            "asset_count":    0,
            "weather_mode":   weather_mode,
        }

    profile     = profiles[matched_city]
    infra_score = _infra_risk_score(profile["telemetry"])

    composite = (_INFRA_WEIGHT * infra_score) + (_WEATHER_WEIGHT * weather_score)
    risk_pct  = int(round(min(composite, 100.0)))

    if is_fallback:
        source = f"Nearest Proximity Fallback [{matched_city}]"
    else:
        source = f"{matched_city} Core Dataset"

    return {
        "risk_score_pct": risk_pct,
        "risk_label":     _label(risk_pct),
        "risk_source":    source,
        "matched_city":   matched_city,
        "asset_count":    profile["asset_count"],
        "weather_mode":   weather_mode,
    }


def _label(score: int) -> str:
    if score >= 65:
        return "High Alert"
    if score >= 35:
        return "Medium Risk"
    return "Low Risk"
