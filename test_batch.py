#!/usr/bin/env python3
"""Batch test: load every .fit file in test_data and report failures."""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
from data_model import FitAnalyzer

test_dir = os.path.join(os.path.dirname(__file__), "test_data")
fit_files = sorted([f for f in os.listdir(test_dir) if f.lower().endswith('.fit')])

print(f"Found {len(fit_files)} .fit files to test\n")

passed = []
failed = []

for fname in fit_files:
    fpath = os.path.join(test_dir, fname)
    try:
        analyzer = FitAnalyzer()
        result = analyzer.load_fit_file(fpath)
        if not result:
            failed.append((fname, "load_fit_file returned False"))
            continue
        # Also test get_plot_data and get_map_track
        x, y = analyzer.get_plot_data(x_axis='elapsed_time')
        x2, y2 = analyzer.get_plot_data(x_axis='distance')
        track = analyzer.get_map_track()
        passed.append(fname)
        sport = analyzer.sport
        n = len(analyzer.data)
        dist = analyzer.summary.get('total_distance_km', 0)
        print(f"  OK  {fname}  sport={sport}  records={n}  dist={dist:.1f}km")
    except Exception as e:
        tb = traceback.format_exc()
        failed.append((fname, tb))
        print(f" FAIL {fname}: {e}")

print(f"\n{'='*60}")
print(f"PASSED: {len(passed)}/{len(fit_files)}")
print(f"FAILED: {len(failed)}/{len(fit_files)}")

if failed:
    print(f"\n{'='*60}")
    print("FAILURE DETAILS:\n")
    for fname, tb in failed:
        print(f"--- {fname} ---")
        print(tb)
        print()
