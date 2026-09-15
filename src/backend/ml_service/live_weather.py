"""
ml_service/live_weather.py

Open-Meteo Live Weather Fetcher
=================================
Queries the free, no-auth Open-Meteo forecast API for current ambient
conditions at a given lat/lon coordinate pair.

Variables fetched (current-hour slice of the hourly forecast):
    temperature_2m          → ambient_temp_c      (°C)
    relativehumidity_2m     → humidity_pct         (%)
    windspeed_10m           → wind_speed_kmh       (km/h)
    precipitation           → live_precipitation_mm (mm)

Failure contract
-----------------
fetch_live_weather() NEVER raises.  On any network error, timeout, or
unexpected API shape it returns a fallback dict with source="unavailable"
so the calling code can always proceed.

Usage
-----
    from ml_service.live_weather import fetch_live_weather

    wx = fetch_live_weather(23.0225, 72.5714)   # Ahmedabad
    # wx keys:
    #   ambient_temp_c        : float | None
    #   humidity_pct          : float | None
    #   wind_speed_kmh        : float | None
    #   live_precipitation_mm : float | None
    #   source                : "live" | "unavailable"
    #   error                 : str | None   (only present when source=="unavailable")
"""

import logging

import requests

logger = logging.getLogger(__name__)

# Open-Meteo free endpoint — no API key required
_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Request timeout in seconds — kept short so a slow network never stalls Django
_TIMEOUT = 5

# Fallback returned when the live call cannot be completed
_UNAVAILABLE: dict = {
    "ambient_temp_c":        None,
    "humidity_pct":          None,
    "wind_speed_kmh":        None,
    "live_precipitation_mm": None,
    "source":                "unavailable",
}


def fetch_live_weather(lat: float, lon: float) -> dict:
    """
    Fetch current ambient weather for a coordinate pair from Open-Meteo.

    Parameters
    ----------
    lat : float   Latitude  (decimal degrees, WGS-84)
    lon : float   Longitude (decimal degrees, WGS-84)

    Returns
    -------
    dict with keys:
        ambient_temp_c        : float | None
        humidity_pct          : float | None
        wind_speed_kmh        : float | None
        live_precipitation_mm : float | None
        source                : "live" | "unavailable"
        error                 : str   (only present when source=="unavailable")
    """
    params = {
        "latitude":        round(lat, 4),
        "longitude":       round(lon, 4),
        "hourly":          "temperature_2m,relativehumidity_2m,windspeed_10m,precipitation",
        "forecast_days":   1,
        "timezone":        "Asia/Kolkata",
    }

    try:
        response = requests.get(_OPEN_METEO_URL, params=params, timeout=_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.Timeout:
        logger.warning("Open-Meteo request timed out for lat=%s lon=%s", lat, lon)
        return {**_UNAVAILABLE, "error": "Request timed out"}
    except requests.exceptions.RequestException as exc:
        logger.warning("Open-Meteo request failed: %s", exc)
        return {**_UNAVAILABLE, "error": str(exc)}
    except ValueError as exc:
        # JSON decode failure
        logger.warning("Open-Meteo returned non-JSON response: %s", exc)
        return {**_UNAVAILABLE, "error": "Invalid JSON response"}

    try:
        hourly = payload.get("hourly", {})
        # Take the first non-None value from the hourly arrays (index 0 = 00:00 local)
        # If index 0 is None (data gap), scan forward up to 6 hours
        def _first_valid(series):
            if not isinstance(series, list):
                return None
            for v in series[:6]:
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        continue
            return None

        temp    = _first_valid(hourly.get("temperature_2m"))
        humid   = _first_valid(hourly.get("relativehumidity_2m"))
        wind    = _first_valid(hourly.get("windspeed_10m"))
        precip  = _first_valid(hourly.get("precipitation"))

        return {
            "ambient_temp_c":        temp,
            "humidity_pct":          humid,
            "wind_speed_kmh":        wind,
            "live_precipitation_mm": precip,
            "source":                "live",
        }

    except Exception as exc:
        logger.warning("Failed to parse Open-Meteo response: %s", exc)
        return {**_UNAVAILABLE, "error": f"Parse error: {exc}"}
