# pyrefly: ignore [missing-import]
import json
import os
import tempfile
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from services.risk_engine import run_risk_assessment, load_json
from ml_service.predictor import predict_rainfall, InvalidSatelliteImageError
from ml_service.live_weather import fetch_live_weather
from ml_service.outage_risk import _CITY_COORDS

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


@api_view(['GET'])
def get_assets(request):
    """
    GET /api/assets/
    Reads src/backend/data/grid_assets.json and returns raw list.
    """
    try:
        data = load_json("grid_assets.json")
        return Response(data, status=status.HTTP_200_OK)
    except FileNotFoundError:
        return Response(
            {"error": "Grid assets data file not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except json.JSONDecodeError:
        return Response(
            {"error": "Failed to decode grid assets JSON data."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        return Response(
            {"error": f"An unexpected error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_incidents(request):
    """
    GET /api/incidents/
    Returns historical incident records for the audit trail.
    """
    try:
        data = load_json("incident_logs.json")
        if not isinstance(data, list):
            raise ValueError("Incident log data must be a list.")
        return Response(data, status=status.HTTP_200_OK)
    except FileNotFoundError:
        return Response(
            {"error": "Incident log data file not found."},
            status=status.HTTP_404_NOT_FOUND
        )
    except (json.JSONDecodeError, ValueError) as e:
        return Response(
            {"error": f"Invalid incident log data: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        return Response(
            {"error": f"Failed to load incident logs: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_weather(request):
    """GET /api/weather/ returns the forecast dataset for the weather view."""
    try:
        data = load_json("weather_forecast.json")
        if not isinstance(data, list):
            raise ValueError("Weather forecast data must be a list.")
        return Response(data, status=status.HTTP_200_OK)
    except FileNotFoundError:
        return Response({"error": "Weather forecast data file not found."}, status=status.HTTP_404_NOT_FOUND)
    except (json.JSONDecodeError, ValueError) as e:
        return Response({"error": f"Invalid weather forecast data: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Failed to load weather forecasts: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_predictions(request):
    """
    GET /api/predictions/
    Executes risk_engine.py and returns list sorted by risk_score DESC.
    """
    try:
        predictions = run_risk_assessment()
        return Response(predictions, status=status.HTTP_200_OK)
    except FileNotFoundError as e:
        return Response(
            {"error": f"Data file missing for risk assessment: {str(e)}"},
            status=status.HTTP_404_NOT_FOUND
        )
    except (json.JSONDecodeError, ValueError) as e:
        return Response(
            {"error": f"Invalid or malformed data file for risk assessment: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        return Response(
            {"error": f"Failed to compute risk predictions: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_maintenance_plan(request):
    """
    GET /api/maintenance-plan/
    Returns filtered list of HIGH risk assets with crew pre-positioning instructions.
    """
    try:
        predictions = run_risk_assessment()
        high_risk_assets = [
            item for item in predictions if item.get("risk_category") == "HIGH"
        ]

        maintenance_plan = []
        for asset in high_risk_assets:
            plan_entry = {
                "asset_id": asset["asset_id"],
                "urgency_rank": asset.get("urgency_rank"),
                "risk_score": asset["risk_score"],
                "risk_category": asset["risk_category"],
                "root_cause": asset["root_cause"],
                "crew_preposition_zone": asset["crew_preposition_zone"],
                "recommended_action": asset["recommended_action"],
                "dispatch_instructions": (
                    f"PRE-POSITION CREW IN {asset['crew_preposition_zone']}: "
                    f"Immediate deployment required for Asset {asset['asset_id']}. "
                    f"Primary issue: {asset['root_cause']}. "
                    f"Action: {asset['recommended_action']}"
                )
            }
            maintenance_plan.append(plan_entry)

        return Response(
            {
                "total_high_risk_count": len(maintenance_plan),
                "maintenance_plan": maintenance_plan
            },
            status=status.HTTP_200_OK
        )
    except FileNotFoundError as e:
        return Response(
            {"error": f"Data file missing for maintenance plan: {str(e)}"},
            status=status.HTTP_404_NOT_FOUND
        )
    except (json.JSONDecodeError, ValueError) as e:
        return Response(
            {"error": f"Invalid or malformed data file for maintenance plan: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        return Response(
            {"error": f"Failed to generate maintenance plan: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Structured error body returned for any image that fails ML telemetry extraction.
_INVALID_IMAGE_RESPONSE = {
    "status": "error",
    "message": (
        "Invalid or unreadable satellite image layout. "
        "Please upload a clear geographical snapshot."
    ),
}


@api_view(['POST'])
def get_satellite_prediction(request):
    """
    POST /api/satellite-predict/
    Dual-mode: processes either a real file upload or a zip archive reference.

    Mode A — multipart file upload (frontend drag-and-drop):
      Content-Type : multipart/form-data
      Fields       : file (the .tif binary), location (city name)

    Mode B — zip archive fallback (testing / CLI clients):
      Content-Type : application/json
      Fields       : image_path (zip-internal path), location (city name)
      Requires     : settings.ML_ZIP_PATH to point at a valid archive.zip

    Validation:
      - Missing location → 400 with descriptive error.
      - No file AND no image_path → 400.
      - Unreadable, non-raster, or all-NaN image → 400 with structured error body.
      - Unknown city name → 400.
      - archive.zip missing (Mode B only) → 404.
      - All other unexpected failures → 500.
    """
    uploaded_file = request.FILES.get("file")

    # location is sent as POST field in multipart mode, or JSON field in zip mode
    location = (request.POST.get("location") or request.data.get("location") or "").strip()

    if not location:
        return Response(
            {"error": "Missing 'location' field."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ------------------------------------------------------------------
    # Mode A: real file upload
    # ------------------------------------------------------------------
    if uploaded_file is not None:
        tmp_path = None
        try:
            suffix = os.path.splitext(uploaded_file.name)[1] or ".tif"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in uploaded_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            result = predict_rainfall(location, image_file_path=tmp_path)
            return Response(result, status=status.HTTP_200_OK)

        except InvalidSatelliteImageError:
            return Response(_INVALID_IMAGE_RESPONSE, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except FileNotFoundError as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ------------------------------------------------------------------
    # Mode B: zip archive fallback (image_path in JSON body)
    # ------------------------------------------------------------------
    image_path = (request.data.get("image_path") or "").strip()
    if not image_path:
        return Response(
            {"error": "No file uploaded and no 'image_path' provided."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    zip_path = str(settings.ML_ZIP_PATH)
    if not os.path.exists(zip_path):
        return Response(
            {"error": f"Archive not found at configured path: {zip_path}"},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        result = predict_rainfall(location, zip_path=zip_path, image_zip_entry=image_path)
        return Response(result, status=status.HTTP_200_OK)
    except InvalidSatelliteImageError:
        return Response(_INVALID_IMAGE_RESPONSE, status=status.HTTP_400_BAD_REQUEST)
    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except FileNotFoundError as e:
        return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_incidents_enriched(request):
    """
    GET /api/incidents/enriched/
    Returns the full incident log with each record annotated with live
    Open-Meteo ambient conditions for its city's coordinates.

    New keys added per record (all may be None if Open-Meteo is unreachable):
        live_temp_c     : float | None   ambient temperature (°C)
        live_humidity   : float | None   relative humidity (%)
        live_wind_kmh   : float | None   wind speed (km/h)
        live_source     : str            "live" | "unavailable"

    All original incident keys are preserved unchanged.
    """
    try:
        incidents = load_json("incident_logs.json")
        if not isinstance(incidents, list):
            raise ValueError("Incident log data must be a list.")
    except FileNotFoundError:
        return Response({"error": "Incident log data file not found."}, status=status.HTTP_404_NOT_FOUND)
    except (json.JSONDecodeError, ValueError) as e:
        return Response({"error": f"Invalid incident log data: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        return Response({"error": f"Failed to load incident logs: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    enriched = []
    for inc in incidents:
        city = inc.get("city", "")
        coords = _CITY_COORDS.get(city)

        if coords:
            wx = fetch_live_weather(coords[0], coords[1])
        else:
            wx = {"source": "unavailable", "ambient_temp_c": None, "humidity_pct": None, "wind_speed_kmh": None}

        enriched.append({
            **inc,
            "live_temp_c":   wx.get("ambient_temp_c"),
            "live_humidity": wx.get("humidity_pct"),
            "live_wind_kmh": wx.get("wind_speed_kmh"),
            "live_source":   wx.get("source", "unavailable"),
        })

    return Response(enriched, status=status.HTTP_200_OK)
