import json
import math

def analyze_cycling(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)

    session = data['activity']['sessions'][0]
    records = session['laps'][0]['records']

    # Basic stats
    total_distance = session['total_distance'] # km
    total_time = session['total_timer_time'] # s
    avg_hr = session['avg_heart_rate']
    max_hr = session['max_heart_rate']
    
    # Constants for Cycling Power Estimation
    mass_rider = 75 # kg
    mass_bike = 10 # kg
    total_mass = mass_rider + mass_bike
    g = 9.81
    crr = 0.005 # rolling resistance
    cd_a = 0.32 # drag area (road bike hoods)
    rho = 1.225 # air density
    
    # Extract records
    hrs = []
    speeds = []
    altitudes = []
    times = []

    for r in records:
        if all(k in r for k in ['heart_rate', 'speed', 'altitude', 'elapsed_time']):
            hrs.append(r['heart_rate'])
            speeds.append(r['speed'] / 3.6) # m/s
            altitudes.append(r['altitude'] * 1000) # Assuming km to m
            times.append(r['elapsed_time'])

    # Cycling Power Calculation
    powers = []
    elevation_gain = 0
    
    for i in range(1, len(speeds)):
        v = speeds[i]
        dt = times[i] - times[i-1]
        dh = altitudes[i] - altitudes[i-1]
        dist = v * dt
        
        if dt <= 0 or dist <= 0: continue
        
        if dh > 0: elevation_gain += dh
        
        grade = dh / dist
        
        # P_gravity = m * g * sin(arctan(grade)) * v
        p_grav = total_mass * g * math.sin(math.atan(grade)) * v
        # P_rolling = m * g * cos(arctan(grade)) * Crr * v
        p_roll = total_mass * g * math.cos(math.atan(grade)) * crr * v
        # P_drag = 0.5 * CdA * rho * v^3
        p_drag = 0.5 * cd_a * rho * (v**3)
        
        # Total Power (ignoring acceleration and drivetrain loss for simplicity)
        p_total = p_grav + p_roll + p_drag
        # Power is at least 0 (no coasting/braking negative power shown)
        powers.append(max(0, p_total))

    avg_power = sum(powers) / len(powers) if powers else 0
    norm_power = (sum([p**4 for p in powers]) / len(powers))**0.25 if powers else 0
    
    print(f"--- Cycling Activity Analysis ---")
    print(f"Distance: {total_distance:.2f} km")
    print(f"Duration: {total_time // 60}m {total_time % 60}s")
    print(f"Elevation Gain: {elevation_gain:.1f} m")
    print(f"Avg Speed: {session['avg_speed']:.2f} km/h")
    print(f"Max Speed: {session['max_speed']:.2f} km/h")
    print(f"Avg HR: {avg_hr} bpm")
    print(f"Max HR: {max_hr} bpm")
    print(f"\n--- Power Estimation (Estimated 85kg total) ---")
    print(f"Estimated Avg Power: {avg_power:.1f} W")
    print(f"Estimated Normalized Power (NP): {norm_power:.1f} W")
    print(f"Estimated W/kg (Rider): {avg_power / mass_rider:.2f} W/kg")

    # HR Zones
    zones = {'Z1 (<120)': 0, 'Z2 (120-140)': 0, 'Z3 (140-160)': 0, 'Z4 (160-175)': 0, 'Z5 (>175)': 0}
    for hr in hrs:
        if hr < 120: zones['Z1 (<120)'] += 1
        elif hr < 140: zones['Z2 (120-140)'] += 1
        elif hr < 160: zones['Z3 (140-160)'] += 1
        elif hr < 175: zones['Z4 (160-175)'] += 1
        else: zones['Z5 (>175)'] += 1
    
    print("\n--- HR Zones ---")
    for z, s in zones.items():
        print(f"{z}: {s}s")

if __name__ == "__main__":
    analyze_cycling('temp_fit_parser/activity.json')
