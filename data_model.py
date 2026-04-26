import json
import math
import os
import pandas as pd
import gpxpy
import gpxpy.gpx
from fitparse import FitFile

def semicircles_to_degrees(semicircles):
    if semicircles is None:
        return None
    return semicircles * (180.0 / (2**31))

class FitAnalyzer:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = self.load_config()
        self.data = pd.DataFrame()
        self.summary = {}
        self.sport = 'unknown'

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {
            "user": {"age": 30, "weight_kg": 75, "max_hr": 190, "resting_hr": 60},
            "equipment": {"bike_weight_kg": 10},
            "settings": {"history_path": "history.json"}
        }

    def save_config(self, config_data):
        with open(self.config_path, 'w') as f:
            json.dump(config_data, f, indent=4)
        self.config = config_data

    def load_fit_file(self, file_path):
        self.summary = {}
        try:
            fitfile = FitFile(file_path)
        except Exception as e:
            print(f"Error loading fit file: {e}")
            return False

        records_list = []
        for record in fitfile.get_messages('record'):
            data = record.get_values()
            
            # Convert semicircles to degrees for lat/long
            if 'position_lat' in data:
                data['position_lat'] = semicircles_to_degrees(data['position_lat'])
            if 'position_long' in data:
                data['position_long'] = semicircles_to_degrees(data['position_long'])
            
            records_list.append(data)

        self.data = pd.DataFrame(records_list)
        
        # Determine sport
        self.sport = 'unknown'
        for session in fitfile.get_messages('session'):
            sport_val = session.get_value('sport')
            if sport_val:
                self.sport = str(sport_val).lower()
                
            # Extract summary stats directly from session if available
            self.summary['total_distance'] = session.get_value('total_distance') # m
            self.summary['total_timer_time'] = session.get_value('total_timer_time') # s
            self.summary['avg_heart_rate'] = session.get_value('avg_heart_rate')
            self.summary['max_heart_rate'] = session.get_value('max_heart_rate')
            self.summary['avg_speed'] = session.get_value('avg_speed')
            self.summary['max_speed'] = session.get_value('max_speed')
            break
            
        self.data['is_synthetic'] = False
        
        # Synthetic Loop Closer
        if not self.data.empty and self.summary.get('total_distance'):
            max_dist = self.data['distance'].max() if 'distance' in self.data.columns else 0
            session_dist = self.summary['total_distance']
            
            # If there's a significant gap (> 2 km)
            if session_dist and pd.notna(max_dist) and session_dist - max_dist > 2000:
                self._synthesize_loop(max_dist, session_dist)
                
        self._calculate_metrics()
        return True
        
    def load_gpx_file(self, file_path):
        self.summary = {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                gpx = gpxpy.parse(f)
        except Exception as e:
            print(f"Error loading gpx file: {e}")
            return False
            
        records_list = []
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    data = {
                        'position_lat': point.latitude,
                        'position_long': point.longitude,
                        'altitude': point.elevation,
                        'timestamp': point.time,
                    }
                    if point.extensions:
                        # try to get hr
                        for ext in point.extensions:
                            # typical Garmin TrackPointExtension
                            if 'TrackPointExtension' in ext.tag:
                                for child in ext:
                                    if 'hr' in child.tag:
                                        data['heart_rate'] = float(child.text)
                                    if 'atemp' in child.tag:
                                        data['temperature'] = float(child.text)
                    records_list.append(data)
                    
        self.data = pd.DataFrame(records_list)
        if self.data.empty:
            return False
            
        self.sport = 'unknown'
        if gpx.tracks and gpx.tracks[0].type:
            self.sport = gpx.tracks[0].type.lower()
            
        # Basic sorting and time difference
        self.data['timestamp'] = pd.to_datetime(self.data['timestamp'])
        self.data = self.data.sort_values(by='timestamp').reset_index(drop=True)
        
        # calculate distance cumulatively
        distances = [0.0]
        for i in range(1, len(self.data)):
            lat1, lon1 = self.data.loc[i-1, 'position_lat'], self.data.loc[i-1, 'position_long']
            lat2, lon2 = self.data.loc[i, 'position_lat'], self.data.loc[i, 'position_long']
            import math
            # Haversine
            R = 6371000 # m
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distances.append(distances[-1] + R * c)
            
        self.data['distance'] = distances
        self.summary['total_distance'] = distances[-1]
        
        if len(self.data) > 1 and pd.notna(self.data.loc[0, 'timestamp']) and pd.notna(self.data.iloc[-1]['timestamp']):
            self.summary['total_timer_time'] = (self.data.iloc[-1]['timestamp'] - self.data.loc[0, 'timestamp']).total_seconds()
        
        self.data['is_synthetic'] = False
        
        # approximate speed from distance and time
        self.data['elapsed_time'] = (self.data['timestamp'] - self.data['timestamp'].iloc[0]).dt.total_seconds()
        dt = self.data['elapsed_time'].diff().fillna(1.0)
        dd = self.data['distance'].diff().fillna(0.0)
        self.data['speed'] = dd / dt
        
        self._calculate_metrics()
        return True
        
    def _synthesize_loop(self, max_dist, session_dist):
        import numpy as np
        if len(self.data) < 2: return
        
        last_record = self.data.iloc[-1].copy()
        first_record = self.data.iloc[0].copy()
        
        missing_dist = session_dist - max_dist
        num_points = 100
        synthetic_records = []
        
        dist_steps = np.linspace(max_dist, session_dist, num_points + 1)[1:]
        
        if 'timestamp' in self.data.columns and pd.notna(last_record.get('timestamp')) and pd.notna(first_record.get('timestamp')):
            total_time = self.summary.get('total_timer_time')
            if total_time:
                elapsed_last = (last_record['timestamp'] - first_record['timestamp']).total_seconds()
                missing_time = total_time - elapsed_last
                if missing_time <= 0:
                    missing_time = missing_dist / max(1.0, self.summary.get('avg_speed', 5.0))
            else:
                missing_time = missing_dist / max(1.0, self.summary.get('avg_speed', 5.0))
            time_steps = np.linspace(0, missing_time, num_points + 1)[1:]
        else:
            time_steps = np.zeros(num_points)
            
        for i in range(num_points):
            frac = (i + 1) / num_points
            new_record = last_record.copy()
            new_record['distance'] = dist_steps[i]
            
            if 'timestamp' in self.data.columns and time_steps[i] > 0:
                new_record['timestamp'] = last_record['timestamp'] + pd.Timedelta(seconds=int(time_steps[i]))
                
            if 'position_lat' in self.data.columns and 'position_long' in self.data.columns:
                lat1, lon1 = last_record.get('position_lat'), last_record.get('position_long')
                lat2, lon2 = first_record.get('position_lat'), first_record.get('position_long')
                if pd.notna(lat1) and pd.notna(lat2):
                    new_record['position_lat'] = lat1 + (lat2 - lat1) * frac
                    new_record['position_long'] = lon1 + (lon2 - lon1) * frac
                    
            if 'altitude' in self.data.columns:
                alt1, alt2 = last_record.get('altitude'), first_record.get('altitude')
                if pd.notna(alt1) and pd.notna(alt2):
                    new_record['altitude'] = alt1 + (alt2 - alt1) * frac
                    
            if 'heart_rate' in self.data.columns:
                new_record['heart_rate'] = self.summary.get('avg_heart_rate', 120)
                
            if 'speed' in self.data.columns:
                new_record['speed'] = self.summary.get('avg_speed', 5.0)
                
            new_record['is_synthetic'] = True
            synthetic_records.append(new_record)
            
        synth_df = pd.DataFrame(synthetic_records)
        self.data = pd.concat([self.data, synth_df], ignore_index=True)

    def _calculate_metrics(self):
        if self.data.empty:
            return

        # Ensure necessary columns exist
        for col in ['heart_rate', 'speed', 'altitude', 'distance', 'timestamp', 'temperature']:
            if col not in self.data.columns:
                self.data[col] = None

        # Ensure is_synthetic column exists
        if 'is_synthetic' not in self.data.columns:
            self.data['is_synthetic'] = False

        # Force numeric types on sensor columns
        for col in ['heart_rate', 'speed', 'altitude', 'distance', 'temperature']:
            self.data[col] = pd.to_numeric(self.data[col], errors='coerce')
            
        # Interpolate missing data (anomalies) for continuous sensors to prevent jumping to zero
        for col in ['heart_rate', 'speed', 'altitude', 'temperature']:
            if col in self.data.columns:
                self.data[col] = self.data[col].interpolate(method='linear')

        # Sort and clean
        self.data = self.data.sort_values(by='timestamp').reset_index(drop=True)
        
        # Calculate time difference
        try:
            self.data['elapsed_time'] = (self.data['timestamp'] - self.data['timestamp'].iloc[0]).dt.total_seconds()
        except Exception:
            # If timestamps are missing or not datetime, generate a sequential index
            self.data['elapsed_time'] = range(len(self.data))
            self.data['elapsed_time'] = self.data['elapsed_time'].astype(float)
        
        # Handle speed (m/s) -> km/h for display purposes, but keep m/s for power
        self.data['speed_ms'] = pd.to_numeric(self.data['speed'], errors='coerce').fillna(0.0)
        self.data['speed_kmh'] = self.data['speed_ms'] * 3.6
            
        # Elevation gain
        self.data['altitude'] = pd.to_numeric(self.data['altitude'], errors='coerce').ffill().bfill().fillna(0.0)
        self.data['altitude_smoothed'] = self.data['altitude'].rolling(window=10, min_periods=1, center=True).mean()
        
        # Distance: fill NaN with 0 and ensure float
        self.data['distance'] = pd.to_numeric(self.data['distance'], errors='coerce').fillna(0.0)
        
        real_mask = ~self.data['is_synthetic'].fillna(False).astype(bool)
        
        alt_diffs = self.data['altitude_smoothed'].diff().fillna(0.0)
        self.summary['elevation_gain'] = alt_diffs[real_mask & (alt_diffs > 0)].sum()
        
        # Calculate Power (if running or cycling)
        self.data['power'] = 0.0
        
        if self.sport in ['cycling', 'running']:
            mass_rider = self.config['user'].get('weight_kg', 75)
            
            if self.sport == 'running':
                # P = 1.04 * mass * speed (m/s)
                self.data['power'] = 1.04 * mass_rider * self.data['speed_ms']
            elif self.sport == 'cycling':
                mass_bike = self.summary.get('track_bike_weight', self.config['equipment'].get('bike_weight_kg', 10))
                total_mass = mass_rider + mass_bike
                g = 9.81
                crr = 0.005 # rolling resistance
                cd_a = 0.32 # drag area
                rho = 1.225 # air density
                
                # We need dt, dh, dist
                dt = self.data['elapsed_time'].diff().fillna(1.0)
                dh = alt_diffs.fillna(0.0)
                dist = self.data['distance'].diff().fillna(0.0)
                
                powers = []
                for i in range(len(self.data)):
                    if i == 0:
                        powers.append(0.0)
                        continue
                    
                    v = self.data.loc[i, 'speed_ms']
                    if v <= 0:
                        powers.append(0.0)
                        continue
                        
                    delta_d = dist.iloc[i]
                    if delta_d <= 0:
                        delta_d = v * dt.iloc[i] # estimate distance if missing
                        if delta_d <= 0:
                            powers.append(0.0)
                            continue
                            
                    grade = dh.iloc[i] / delta_d
                    if grade > 0.25: grade = 0.25
                    elif grade < -0.25: grade = -0.25
                    
                    p_grav = total_mass * g * math.sin(math.atan(grade)) * v
                    p_roll = total_mass * g * math.cos(math.atan(grade)) * crr * v
                    p_drag = 0.5 * cd_a * rho * (v**3)
                    
                    p_total = p_grav + p_roll + p_drag
                    powers.append(max(0.0, p_total))
                    
                self.data['power'] = powers

        # Calculate Power averages
        if 'power' in self.data.columns and self.data['power'].sum() > 0:
            # Smooth power for plot based on user config
            window = self.config.get('settings', {}).get('power_filter_window', 5)
            power_smoothed = self.data['power'].rolling(window=window, min_periods=1, center=True).mean()
            self.data['power'] = power_smoothed
            
            real_power = self.data.loc[real_mask, 'power']
            self.summary['avg_power'] = real_power.mean()
            
            # For Normalized Power (NP), use 30s moving average
            power_30s = real_power.rolling(window=30, min_periods=1).mean()
            self.summary['normalized_power'] = (power_30s.map(lambda x: max(0, x)**4).mean())**0.25
        else:
            self.summary['avg_power'] = None
            self.summary['normalized_power'] = None

        # HR Zones
        zones = {'Z1 (<120)': 0, 'Z2 (120-140)': 0, 'Z3 (140-160)': 0, 'Z4 (160-175)': 0, 'Z5 (>175)': 0}
        if 'heart_rate' in self.data.columns:
            hr_series = pd.to_numeric(self.data['heart_rate'], errors='coerce').dropna()
            # Approximation by counting records if recorded roughly 1/sec
            for hr in hr_series:
                if hr < 120: zones['Z1 (<120)'] += 1
                elif hr < 140: zones['Z2 (120-140)'] += 1
                elif hr < 160: zones['Z3 (140-160)'] += 1
                elif hr < 175: zones['Z4 (160-175)'] += 1
                else: zones['Z5 (>175)'] += 1
        self.summary['hr_zones'] = zones
        
        # Calories
        self.summary['calories'] = 0
        if self.sport == 'running':
            mass_rider = self.config['user'].get('weight_kg', 75)
            self.summary['calories'] = int(1.036 * mass_rider * (self.summary.get('total_distance_km', 0)))
        elif self.sport == 'cycling' and self.summary.get('avg_power'):
            duration_hrs = self.summary.get('total_timer_time', 0) / 3600
            self.summary['calories'] = int(self.summary['avg_power'] * duration_hrs * 3.6)
        
        # Convert total distance to km if it's in meters
        if self.summary.get('total_distance'):
            self.summary['total_distance_km'] = self.summary['total_distance'] / 1000.0
        else:
            # Estimate from data
            if 'distance' in self.data.columns and self.data['distance'].notna().any():
                self.summary['total_distance_km'] = self.data['distance'].max() / 1000.0
            else:
                self.summary['total_distance_km'] = 0.0
                
        # Calculate Fitness Score
        if self.summary.get('avg_power') and self.summary.get('avg_heart_rate') and self.sport in ['cycling', 'running']:
            user_config = self.config.get('user', {})
            age = user_config.get('age', 30)
            weight = user_config.get('weight_kg', 75)
            max_hr = user_config.get('max_hr', 190)
            resting_hr = user_config.get('resting_hr', 60)
            
            avg_hr = self.summary['avg_heart_rate']
            avg_power = self.summary['avg_power']
            
            hr_reserve = max_hr - resting_hr
            if hr_reserve > 0:
                # 1. Heart Rate Reserve Fraction (HRRF)
                raw_hrrf = (avg_hr - resting_hr) / hr_reserve
                hrrf = max(0.3, min(0.95, raw_hrrf)) # Clamp to prevent extreme extrapolation
                
                # 2. Extrapolated Threshold Power (FTP)
                est_ftp = (avg_power / hrrf) * 0.85
                
                # 3. Power-to-Weight Ratio (W/kg)
                w_kg = est_ftp / weight if weight > 0 else 0
                
                # 4. Base Score Mapping
                base_score = (w_kg - 1.0) * 20 + 30
                
                # 5. Age Grading
                age_factor = max(0, age - 30) * 0.6
                
                final_score = base_score + age_factor
                self.summary['fitness_score'] = max(0.0, min(100.0, final_score))

    def _safe_float_array(self, series):
        """Convert a pandas Series to a clean float64 numpy array, replacing
        non-numeric values with NaN so they are ignored by pyqtgraph."""
        import numpy as np
        return pd.to_numeric(series, errors='coerce').astype(np.float64).values

    def get_plot_data(self, x_axis='elapsed_time'):
        """Returns x, and dictionary of y series as clean float64 arrays."""
        import numpy as np
        if self.data.empty:
            return None, {}

        if x_axis not in self.data.columns:
            return None, {}

        x = pd.to_numeric(self.data[x_axis], errors='coerce').fillna(0.0)
        if x_axis == 'elapsed_time':
            x = x / 60.0  # minutes
        elif x_axis == 'distance':
            x = x / 1000.0  # km

        y_data = {
            'heart_rate': self._safe_float_array(
                self.data['heart_rate'].ffill().bfill() if 'heart_rate' in self.data.columns
                else pd.Series(0.0, index=self.data.index)),
            'speed_kmh': self._safe_float_array(
                self.data['speed_kmh'] if 'speed_kmh' in self.data.columns
                else pd.Series(0.0, index=self.data.index)),
            'altitude': self._safe_float_array(
                self.data['altitude'] if 'altitude' in self.data.columns
                else pd.Series(0.0, index=self.data.index)),
            'power': self._safe_float_array(
                self.data['power'] if 'power' in self.data.columns
                else pd.Series(0.0, index=self.data.index)),
            'temperature': self._safe_float_array(
                self.data['temperature'].ffill().bfill() if 'temperature' in self.data.columns
                else pd.Series(0.0, index=self.data.index)),
        }

        return x.astype(np.float64).values, y_data

    def get_map_track(self):
        if self.data.empty or 'position_lat' not in self.data.columns or 'position_long' not in self.data.columns:
            return []

        # Filter valid lat/long — drop rows where either coord is NaN/None
        track = self.data[['position_lat', 'position_long']].copy()
        track['position_lat'] = pd.to_numeric(track['position_lat'], errors='coerce')
        track['position_long'] = pd.to_numeric(track['position_long'], errors='coerce')
        track = track.dropna()
        if track.empty:
            return []
        return track.values.tolist()
