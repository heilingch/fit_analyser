import json
import math

def analyze_activity(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)

    session = data['activity']['sessions'][0]
    records = session['laps'][0]['records']

    # Basic stats
    total_distance = session['total_distance'] # km
    total_time = session['total_timer_time'] # s
    avg_hr = session['avg_heart_rate']
    max_hr = session['max_heart_rate']
    
    # Extract records
    times = []
    hrs = []
    speeds = []
    altitudes = []
    distances = []

    for r in records:
        if 'heart_rate' in r:
            hrs.append(r['heart_rate'])
        if 'speed' in r:
            speeds.append(r['speed'])
        if 'altitude' in r:
            altitudes.append(r['altitude'])
        if 'distance' in r:
            distances.append(r['distance'])
        if 'elapsed_time' in r:
            times.append(r['elapsed_time'])

    # Units check: fit-file-parser with speedUnit: 'km/h' and lengthUnit: 'km'
    # Speed is in km/h, distance in km, altitude in km (likely meters if 0.313 is 313m)
    # Wait, in the JSON snippet: "altitude": 0.31379999999999997
    # If it's km, it's 313.8m.
    
    # Calculate more stats
    avg_speed = sum(speeds) / len(speeds) if speeds else 0
    max_speed_calc = max(speeds) if speeds else 0
    
    # Elevation gain
    elevation_gain = 0
    for i in range(1, len(altitudes)):
        diff = altitudes[i] - altitudes[i-1]
        if diff > 0:
            elevation_gain += diff
    
    # Running Power Estimation (if we assume it's running)
    # Simple model: P = 1.04 * mass * speed (m/s)
    # We'll assume mass = 75kg
    mass = 75
    powers = []
    for s in speeds:
        s_ms = s / 3.6
        p = 1.04 * mass * s_ms
        powers.append(p)
    
    avg_power = sum(powers) / len(powers) if powers else 0

    # Fitness Feedback
    # Based on HR and Speed. 
    # Pace: 14.5 km/h is ~4:08 min/km. 
    # 119 bpm for that pace is EXTREMELY good if it's running. 
    # It would indicate an elite athlete.
    # If it's cycling, 14.5 km/h is very slow for 119 bpm.
    
    print(f"--- Activity Analysis ---")
    print(f"Sport: {session.get('sport', 'unknown')}")
    print(f"Distance: {total_distance:.2f} km")
    print(f"Duration: {total_time // 60}m {total_time % 60}s")
    print(f"Avg HR: {avg_hr} bpm")
    print(f"Max HR: {max_hr} bpm")
    print(f"Avg Speed: {avg_speed:.2f} km/h")
    print(f"Max Speed: {max_speed_calc:.2f} km/h")
    print(f"Elevation Gain: {elevation_gain * 1000:.1f} m") # Assuming altitude is in km
    print(f"Estimated Avg Power (Run, 75kg): {avg_power:.1f} W")
    
    # HR Zones (Estimate max HR as 220-age, or use 190 as default)
    zones = {
        'Zone 1 (<130)': 0,
        'Zone 2 (130-150)': 0,
        'Zone 3 (150-170)': 0,
        'Zone 4 (170-185)': 0,
        'Zone 5 (>185)': 0
    }
    for hr in hrs:
        if hr < 130: zones['Zone 1 (<130)'] += 1
        elif hr < 150: zones['Zone 2 (130-150)'] += 1
        elif hr < 170: zones['Zone 3 (150-170)'] += 1
        elif hr < 185: zones['Zone 4 (170-185)'] += 1
        else: zones['Zone 5 (>185)'] += 1
    
    print("\n--- Heart Rate Zones (Time in seconds) ---")
    for z, count in zones.items():
        print(f"{z}: {count}s")

if __name__ == "__main__":
    analyze_activity('temp_fit_parser/activity.json')
