"""
ml_service/predictor.py

Pure prediction logic distilled from predict.py.
Loads the pre-trained .pkl model once at module import time using a
__file__-relative path.  No Flask, no sys.exit, no training code.

Accepts either:
  - a plain on-disk file path to a .tif image, or
  - a (zip_path, image_path) pair for archive-based access (zip fallback mode).
"""

import io
import os
import re
import zipfile

import joblib
import numpy as np
import pandas as pd
from PIL import Image

from ml_service.live_weather import fetch_live_weather
from ml_service.outage_risk import assess_outage_risk

# ---------------------------------------------------------------------------
# Custom exception — raised for images that cannot yield valid telemetry arrays
# ---------------------------------------------------------------------------
class InvalidSatelliteImageError(ValueError):
    """
    Raised when an uploaded or referenced image cannot be processed as a valid
    INSAT-3D satellite raster (wrong format, empty, 1-D, all-NaN pixel data, etc.).
    """


# ---------------------------------------------------------------------------
# Model — loaded once at import time, path anchored to this file's directory
# ---------------------------------------------------------------------------
MODEL_PATH = os.path.join(os.path.dirname(__file__), "weather_rainfall_model.pkl")
model = joblib.load(MODEL_PATH)

# ---------------------------------------------------------------------------
# Spatial projection constants for INSAT-3D
# ---------------------------------------------------------------------------
TOP_LAT = 38.02897834557538
LEFT_LON = 62.9883746791066
PIXEL_SCALE = 0.03353227354064445

# ---------------------------------------------------------------------------
# Gujarat location coordinate table  (sourced from predict.py lines 26-39)
# ---------------------------------------------------------------------------
GUJARAT_LOCATIONS = {
    # Central Gujarat
    'Ahmedabad':  (23.0225, 72.5714),
    'Vadodara':   (22.3072, 73.1812),
    'Anand':      (22.5645, 72.9289),
    'Gandhinagar':(23.2156, 72.6369),
    # South Gujarat
    'Surat':      (21.1702, 72.8311),
    'Bharuch':    (21.7051, 72.9959),
    'Navsari':    (20.9467, 72.9520),
    'Vapi':       (20.3719, 72.9068),
    'Valsad':     (20.5992, 72.9342),
    # Saurashtra
    'Rajkot':     (22.3039, 70.8022),
    'Bhavnagar':  (21.7645, 72.1519),
    'Jamnagar':   (22.4707, 70.0577),
    'Junagadh':   (21.5222, 70.4579),
    # North Gujarat
    'Mehsana':    (23.5880, 72.3693),
    'Palanpur':   (24.1725, 72.4382),
    'Patan':      (23.8493, 72.1266),
    # Kutch
    'Bhuj':       (23.2420, 69.6669),
    'Gandhidham': (23.0753, 70.1337),
}


def _load_array_from_file(image_file_path: str) -> np.ndarray:
    """Open a .tif (or any PIL-readable raster) from disk and return its numpy array."""
    try:
        img = Image.open(image_file_path)
        arr = np.array(img)
    except Exception as exc:
        raise InvalidSatelliteImageError(
            "Invalid or unreadable satellite image layout. "
            "Please upload a clear geographical snapshot."
        ) from exc
    _validate_array(arr)
    return arr


def _load_array_from_zip(zip_path: str, image_path: str) -> np.ndarray:
    """Open a .tif from inside a zip archive and return its numpy array."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            img_bytes = z.read(image_path)
            img = Image.open(io.BytesIO(img_bytes))
            arr = np.array(img)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise InvalidSatelliteImageError(
            "Invalid or unreadable satellite image layout. "
            "Please upload a clear geographical snapshot."
        ) from exc
    except Exception as exc:
        raise InvalidSatelliteImageError(
            "Invalid or unreadable satellite image layout. "
            "Please upload a clear geographical snapshot."
        ) from exc
    _validate_array(arr)
    return arr


def _validate_array(arr: np.ndarray) -> None:
    """
    Raise InvalidSatelliteImageError if the array cannot yield valid telemetry.
    Checks:
      - Array must be at least 2-dimensional (spatial raster, not a 1-D vector).
      - Array must have at least one non-NaN, finite numeric value.
    """
    if arr.ndim < 2:
        raise InvalidSatelliteImageError(
            "Invalid or unreadable satellite image layout. "
            "Please upload a clear geographical snapshot."
        )
    numeric = arr.astype(float)
    if not np.any(np.isfinite(numeric)):
        raise InvalidSatelliteImageError(
            "Invalid or unreadable satellite image layout. "
            "Please upload a clear geographical snapshot."
        )


def predict_rainfall(
    location_name: str,
    image_file_path: str = None,
    zip_path: str = None,
    image_zip_entry: str = None,
) -> dict:
    """
    Predict rainfall for a Gujarat location from a satellite image.

    Exactly one of the two image sources must be provided:
      - ``image_file_path`` : absolute path to a .tif on disk  (upload mode)
      - ``zip_path`` + ``image_zip_entry`` : archive path + entry  (zip fallback mode)

    Parameters
    ----------
    location_name : str
        City name (case-insensitive).  Must be one of the GUJARAT_LOCATIONS keys.
    image_file_path : str, optional
        Absolute path to the .tif image file on disk.
    zip_path : str, optional
        Absolute path to the zip archive.
    image_zip_entry : str, optional
        Path of the image file *within* the zip archive.

    Returns
    -------
    dict
        Keys: location, coordinates, image, pixel_value,
              predicted_rainfall_mm, weather_condition.

    Raises
    ------
    ValueError
        If ``location_name`` is not found in GUJARAT_LOCATIONS, or if neither
        image source is provided.
    InvalidSatelliteImageError
        If the image cannot be decoded or does not contain valid raster data.
    FileNotFoundError
        If ``image_file_path`` or ``zip_path`` does not exist on disk.
    """
    # ------------------------------------------------------------------
    # 1. Case-insensitive location lookup
    # ------------------------------------------------------------------
    lower_map = {k.lower(): k for k in GUJARAT_LOCATIONS}
    norm_name = location_name.strip().lower()
    if norm_name not in lower_map:
        raise ValueError(
            f"Location '{location_name}' not recognised. "
            f"Available locations: {list(GUJARAT_LOCATIONS.keys())}"
        )
    canonical_name = lower_map[norm_name]
    lat, lon = GUJARAT_LOCATIONS[canonical_name]

    # ------------------------------------------------------------------
    # 2. Load image array from the appropriate source
    # ------------------------------------------------------------------
    if image_file_path is not None:
        arr = _load_array_from_file(image_file_path)
        display_name = os.path.basename(image_file_path)
        name_for_regex = image_file_path
    elif zip_path is not None and image_zip_entry is not None:
        arr = _load_array_from_zip(zip_path, image_zip_entry)
        display_name = os.path.basename(image_zip_entry)
        name_for_regex = image_zip_entry
    else:
        raise ValueError(
            "Provide either 'image_file_path' (upload mode) "
            "or both 'zip_path' and 'image_zip_entry' (zip fallback mode)."
        )

    # ------------------------------------------------------------------
    # 3. Pixel coordinate lookup + 3x3 average
    # ------------------------------------------------------------------
    px = max(0, min(arr.shape[1] - 1, int(round((lon - LEFT_LON) / PIXEL_SCALE))))
    py = max(0, min(arr.shape[0] - 1, int(round((TOP_LAT - lat) / PIXEL_SCALE))))

    sub_arr = arr[max(0, py - 1):py + 2, max(0, px - 1):px + 2]
    pixel_value = float(np.nanmean(sub_arr))

    # ------------------------------------------------------------------
    # 4. Time & sensor extraction from filename
    # ------------------------------------------------------------------
    m = re.search(r'3DIMG_\d{2}[A-Z]{3}\d{4}_(\d{2})', name_for_regex)
    hour = int(m.group(1)) if m else 12
    sensor_code = 1 if 'VIS' in name_for_regex else 0

    # ------------------------------------------------------------------
    # 5. Build input DataFrame and run model
    # ------------------------------------------------------------------
    X_input = pd.DataFrame([{
        'latitude':    lat,
        'longitude':   lon,
        'pixel_value': pixel_value,
        'hour':        hour,
        'sensor_code': sensor_code,
    }])
    predicted_mm = max(0.0, round(float(model.predict(X_input)[0]), 2))

    # ------------------------------------------------------------------
    # 6. Map predicted_mm to a weather description (5-band logic)
    # ------------------------------------------------------------------
    if predicted_mm == 0.0:
        desc = "Clear / Dry Weather"
    elif predicted_mm < 7.5:
        desc = "Light Rain / Drizzle"
    elif predicted_mm < 35.5:
        desc = "Moderate Rain"
    elif predicted_mm < 64.5:
        desc = "Heavy Rain"
    else:
        desc = "Very Heavy Rainfall"

    # ------------------------------------------------------------------
    # 7. Fetch live ambient weather for the exact coordinate pair
    # ------------------------------------------------------------------
    live_wx = fetch_live_weather(lat, lon)

    # ------------------------------------------------------------------
    # 8. Composite outage risk assessment (live weather injected when available)
    # ------------------------------------------------------------------
    risk = assess_outage_risk(
        city_name       = canonical_name,
        predicted_mm    = predicted_mm,
        pixel_intensity = pixel_value,
        live_weather    = live_wx,
    )

    return {
        'location':               canonical_name,
        'coordinates':            f"{lat} N, {lon} E",
        'image':                  display_name,
        'pixel_value':            round(pixel_value, 2),
        'predicted_rainfall_mm':  predicted_mm,
        'weather_condition':      desc,
        # Live ambient conditions from Open-Meteo
        'live_temp_c':            live_wx.get('ambient_temp_c'),
        'live_humidity_pct':      live_wx.get('humidity_pct'),
        'live_wind_kmh':          live_wx.get('wind_speed_kmh'),
        'live_precip_mm':         live_wx.get('live_precipitation_mm'),
        'live_weather_source':    live_wx.get('source', 'unavailable'),
        # Risk assessment keys
        'risk_score_pct':         risk['risk_score_pct'],
        'risk_label':             risk['risk_label'],
        'risk_source':            risk['risk_source'],
        'weather_mode':           risk['weather_mode'],
    }


if __name__ == "__main__":
    import sys
    # Quick manual smoke-test (upload mode):
    #   python predictor.py <image_file_path> <city>
    # Example:
    #   python predictor.py /path/to/3DIMG_07NOV2019_0600_L1C_SGP.tif Ahmedabad
    if len(sys.argv) != 3:
        print("Usage: python predictor.py <image_file_path> <city>")
        sys.exit(1)
    result = predict_rainfall(sys.argv[2], image_file_path=sys.argv[1])
    for k, v in result.items():
        print(f"{k}: {v}")
