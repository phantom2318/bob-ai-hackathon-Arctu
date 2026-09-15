import zipfile
import io
import os
import re
import sys
import joblib
import numpy as np
import pandas as pd
from PIL import Image

# ---------------------------------------------------------
# CONSTANTS & MODEL LOADING
# ---------------------------------------------------------
MODEL_PATH = "weather_rainfall_model.pkl"
ZIP_PATH = "archive.zip"

if not os.path.exists(MODEL_PATH):
    print(f"Error: Model file '{MODEL_PATH}' not found. Please run 'python model.py' first.")
    sys.exit(1)

model = joblib.load(MODEL_PATH)

# INSAT-3D Geo-referencing bounds
TOP_LAT = 38.02897834557538
LEFT_LON = 62.9883746791066
PIXEL_SCALE = 0.03353227354064445

# 33 Districts and major locations of Gujarat with coordinates
GUJARAT_LOCATIONS = {
    'Ahmedabad': (23.0225, 72.5714),
    'Surat': (21.1702, 72.8311),
    'Vadodara': (22.3072, 73.1812),
    'Rajkot': (22.3039, 70.8022),
    'Bhavnagar': (21.7645, 72.1519),
    'Jamnagar': (22.4707, 70.0577),
    'Junagadh': (21.5222, 70.4579),
    'Gandhinagar': (23.2156, 72.6369),
    'Anand': (22.5645, 72.9289),
    'Kutch (Bhuj)': (23.2420, 69.6669),
    'Bharuch': (21.7051, 72.9959),
    'Mehsana': (23.5880, 72.3693),
    'Amreli': (21.6032, 71.2221),
    'Porbandar': (21.6417, 69.6293),
    'Morbi': (22.8173, 70.8368),
    'Navsari': (20.9467, 72.9520),
    'Valsad': (20.5992, 72.9342),
    'Patan': (23.8493, 72.1266),
    'Banaskantha': (24.1724, 72.4346),
    'Sabarkantha': (23.5977, 72.9688),
    'Panchmahal': (22.7780, 73.6143),
    'Dahod': (22.8347, 74.2552),
    'Narmada': (21.8719, 73.5028),
    'Tapi': (21.1147, 73.3986),
    'Gir Somnath': (20.9042, 70.3644),
    'Devbhumi Dwarka': (22.2078, 69.6582),
    'Botad': (22.1704, 71.6662),
    'Chhota Udepur': (22.3108, 74.0125),
    'Mahisagar': (23.1311, 73.6009),
    'Aravalli': (23.4619, 73.3039),
    'Surendranagar': (22.7274, 71.6370),
    'Dang': (20.7554, 73.6873),
    'Kheda': (22.6916, 72.8634)
}

def get_available_images():
    """Returns sorted list of satellite tif images inside zip archive."""
    if not os.path.exists(ZIP_PATH):
        return []
    with zipfile.ZipFile(ZIP_PATH) as z:
        return sorted([f for f in z.namelist() if f.endswith('.tif')])

def predict_weather_for_location(location_name, image_path=None):
    """
    Automated Weather Prediction System:
    Takes location_name from user, automatically fetches satellite image & metadata,
    extracts features, and predicts weather.
    """
    # 1. Resolve Location Coordinates
    location_name_clean = location_name.strip().title()
    matched_loc = None
    for loc_key in GUJARAT_LOCATIONS:
        if location_name_clean in loc_key or loc_key in location_name_clean:
            matched_loc = loc_key
            break
            
    if not matched_loc:
        matched_loc = 'Ahmedabad'  # Default fallback
        print(f"Location '{location_name}' matched to default '{matched_loc}'")
    else:
        print(f"Location resolved: {matched_loc}")

    lat, lon = GUJARAT_LOCATIONS[matched_loc]

    # 2. Automatically select satellite image if not provided
    available_images = get_available_images()
    if not available_images:
        print("Error: No satellite images found in archive.zip.")
        return None
        
    if not image_path:
        # Automatically pick latest / representative TIR1 satellite image
        tir_images = [img for img in available_images if 'TIR1' in img]
        image_path = tir_images[12] if len(tir_images) > 12 else tir_images[0]
        print(f"Automatically retrieved satellite image: {os.path.basename(image_path)}")

    # 3. Read image & extract features
    with zipfile.ZipFile(ZIP_PATH) as z:
        img_bytes = z.read(image_path)
        img = Image.open(io.BytesIO(img_bytes))
        arr = np.array(img)

    # Pixel location lookup
    px = max(0, min(arr.shape[1] - 1, int(round((lon - LEFT_LON) / PIXEL_SCALE))))
    py = max(0, min(arr.shape[0] - 1, int(round((TOP_LAT - lat) / PIXEL_SCALE))))

    # Extract 3x3 local neighborhood average
    sub_arr = arr[max(0, py-1):py+2, max(0, px-1):px+2]
    pixel_val = float(np.nanmean(sub_arr))

    # Time & Sensor extraction
    m = re.search(r'3DIMG_(\d{2})([A-Z]{3})(\d{4})_(\d{2})(\d{2})_', image_path)
    if m:
        day, month, year, hh, mm = m.groups()
        time_str = f"{day}-{month}-{year} {hh}:{mm} UTC"
        hour = int(hh)
    else:
        time_str = "07-NOV-2019 12:00 UTC"
        hour = 12

    sensor_code = 1 if 'VIS' in image_path else 0
    sensor_name = "INSAT-3D VIS" if sensor_code == 1 else "INSAT-3D TIR1"

    # 4. Predict using Scikit-Learn model
    input_df = pd.DataFrame([{
        'latitude': lat,
        'longitude': lon,
        'pixel_value': pixel_val,
        'hour': hour,
        'sensor_code': sensor_code
    }])

    predicted_rainfall_mm = max(0.0, round(float(model.predict(input_df)[0]), 2))

    # Weather Classification
    if predicted_rainfall_mm == 0.0:
        condition = "Clear / Sunny Weather"
        recommendation = "Dry weather expected. Great day for outdoor activities."
    elif predicted_rainfall_mm < 7.5:
        condition = "Light Rain / Drizzle"
        recommendation = "Light scattered showers expected. Carry a light umbrella."
    elif predicted_rainfall_mm < 35.5:
        condition = "Moderate Rainfall"
        recommendation = "Steady rain expected. Expect slight traffic delays."
    elif predicted_rainfall_mm < 64.5:
        condition = "Heavy Rain"
        recommendation = "Heavy rain warning! Stay indoors and drive carefully."
    else:
        condition = "Very Heavy Rainfall / Severe Storm"
        recommendation = "High alert! Waterlogging possible. Avoid unnecessary travel."

    return {
        'Location': matched_loc,
        'State': 'Gujarat',
        'Coordinates': f"{lat} N, {lon} E",
        'Satellite_Image': os.path.basename(image_path),
        'Sensor_Channel': sensor_name,
        'Observation_Time': time_str,
        'Cloud_Intensity_Count': round(pixel_val, 2),
        'Predicted_Rainfall_mm': predicted_rainfall_mm,
        'Weather_Condition': condition,
        'Advisory': recommendation
    }

def print_report(res):
    if not res:
        return
    print("\n=======================================================")
    print(f"        WEATHER FORECAST REPORT - {res['Location'].upper()}, GUJARAT")
    print("=======================================================")
    print(f" Location:          {res['Location']} ({res['Coordinates']})")
    print(f" Satellite Image:   {res['Satellite_Image']}")
    print(f" Sensor:            {res['Sensor_Channel']}")
    print(f" Observation Time:  {res['Observation_Time']}")
    print(f" Cloud Top Intensity: {res['Cloud_Intensity_Count']}")
    print(" -------------------------------------------------------")
    print(f" PREDICTED RAINFALL: {res['Predicted_Rainfall_mm']} mm")
    print(f" WEATHER CONDITION:  {res['Weather_Condition']}")
    print(f" ADVISORY:          {res['Advisory']}")
    print("=======================================================\n")

def main():
    print("=======================================================")
    print("   AUTOMATED SATELLITE WEATHER PREDICTION SYSTEM")
    print("   (Powered by Scikit-Learn & INSAT-3D Imagery)")
    print("=======================================================")
    print("Modes:")
    print("1. Enter Location in Gujarat (System automatically fetches satellite image)")
    print("2. Provide Satellite Image Path + Location")
    print("3. Run Full Gujarat State Rainfall Scan")
    print("4. Exit")
    
    while True:
        try:
            choice = input("\nSelect Mode (1-4): ").strip()
            if choice == '1':
                loc = input("Enter Gujarat City/District name (e.g. Ahmedabad, Surat, Rajkot, Bhuj, Valsad): ").strip()
                if not loc:
                    loc = "Ahmedabad"
                res = predict_weather_for_location(loc)
                print_report(res)
            elif choice == '2':
                images = get_available_images()
                print(f"Sample available images ({len(images)} total):")
                for i, img in enumerate(images[:5]):
                    print(f"  [{i+1}] {img}")
                img_input = input("Enter image index (1-5) or image path: ").strip()
                if img_input.isdigit() and 1 <= int(img_input) <= len(images):
                    selected_img = images[int(img_input)-1]
                else:
                    selected_img = images[0]
                loc = input("Enter location in Gujarat: ").strip() or "Ahmedabad"
                res = predict_weather_for_location(loc, image_path=selected_img)
                print_report(res)
            elif choice == '3':
                print("\n--- Running Gujarat State Weather Scan ---")
                images = get_available_images()
                test_img = images[0]
                print(f"Scanning Image: {os.path.basename(test_img)}")
                for city in ['Ahmedabad', 'Surat', 'Vadodara', 'Rajkot', 'Bhavnagar', 'Kutch (Bhuj)', 'Valsad']:
                    res = predict_weather_for_location(city, image_path=test_img)
                    print(f"City: {res['Location']:<14} | Rain: {res['Predicted_Rainfall_mm']:>6.2f} mm | Status: {res['Weather_Condition']}")
            elif choice == '4':
                print("Exiting Satellite Weather Prediction System. Goodbye!")
                break
            else:
                print("Invalid choice. Please enter 1, 2, 3, or 4.")
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    # If run with command arguments e.g. python app.py "Surat"
    if len(sys.argv) > 1:
        loc_arg = sys.argv[1]
        img_arg = sys.argv[2] if len(sys.argv) > 2 else None
        res = predict_weather_for_location(loc_arg, image_path=img_arg)
        print_report(res)
    else:
        main()
