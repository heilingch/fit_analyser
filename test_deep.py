#!/usr/bin/env python3
"""Deep test: simulate the full UI data pipeline for every .fit file."""
import os
import sys
import traceback
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from data_model import FitAnalyzer

test_dir = os.path.join(os.path.dirname(__file__), "test_data")
fit_files = sorted([f for f in os.listdir(test_dir) if f.lower().endswith('.fit')])

print(f"Found {len(fit_files)} .fit files to deep-test\n")

passed = []
failed = []

for fname in fit_files:
    fpath = os.path.join(test_dir, fname)
    errors = []
    try:
        analyzer = FitAnalyzer()
        result = analyzer.load_fit_file(fpath)
        if not result:
            failed.append((fname, "load_fit_file returned False"))
            continue

        # 1. Test get_plot_data for both axes
        for axis in ['elapsed_time', 'distance']:
            x, y = analyzer.get_plot_data(x_axis=axis)
            if x is None:
                errors.append(f"get_plot_data({axis}) returned None x")
                continue
            if np.any(np.isnan(x)):
                errors.append(f"get_plot_data({axis}): x contains NaN")
            if np.any(np.isinf(x)):
                errors.append(f"get_plot_data({axis}): x contains Inf")
            for key, arr in y.items():
                if arr is None:
                    errors.append(f"get_plot_data({axis}): y[{key}] is None")
                elif np.any(np.isnan(arr)):
                    errors.append(f"get_plot_data({axis}): y[{key}] has NaN")
                elif np.any(np.isinf(arr)):
                    errors.append(f"get_plot_data({axis}): y[{key}] has Inf")

        # 2. Test get_map_track
        track = analyzer.get_map_track()
        if track:
            for i, pt in enumerate(track):
                if len(pt) != 2:
                    errors.append(f"map track point {i} has {len(pt)} elements")
                    break
                if pt[0] is None or pt[1] is None:
                    errors.append(f"map track point {i} has None coords")
                    break

        # 3. Test dashboard fields
        s = analyzer.summary
        for key in ['total_distance_km', 'total_timer_time', 'elevation_gain',
                     'avg_heart_rate', 'max_heart_rate', 'hr_zones',
                     'avg_power', 'normalized_power', 'calories']:
            if key not in s:
                errors.append(f"summary missing key: {key}")

        # 4. Test that heart_rate ffill doesn't crash with all-NaN
        hr = analyzer.data.get('heart_rate')
        if hr is not None:
            hr_filled = hr.ffill()  # simulate what plot does

        # 5. Simulate crosshair hover at multiple x positions
        x, y = analyzer.get_plot_data(x_axis='elapsed_time')
        if x is not None and len(x) > 0:
            for test_x in [x[0], x[len(x)//2], x[-1]]:
                idx = (np.abs(x - test_x)).argmin()
                for key, arr in y.items():
                    if arr is not None and len(arr) > idx:
                        val = arr[idx]
                        # Check it's a valid number
                        if not np.isfinite(val):
                            errors.append(f"crosshair y[{key}][{idx}] = {val} (not finite)")

        if errors:
            failed.append((fname, "\n".join(errors)))
            print(f" WARN {fname}: {len(errors)} issues")
            for e in errors:
                print(f"       - {e}")
        else:
            passed.append(fname)
            print(f"  OK  {fname}")

    except Exception as e:
        tb = traceback.format_exc()
        failed.append((fname, tb))
        print(f" FAIL {fname}: {e}")

print(f"\n{'='*60}")
print(f"PASSED: {len(passed)}/{len(fit_files)}")
print(f"FAILED/WARN: {len(failed)}/{len(fit_files)}")

if failed:
    print(f"\n{'='*60}")
    print("FAILURE DETAILS:\n")
    for fname, detail in failed:
        print(f"--- {fname} ---")
        print(detail)
        print()
