import sys

packages = ["fitparse", "pandas", "numpy", "matplotlib", "PySide6", "pyqtgraph", "scipy"]
missing = []

print("Checking dependencies...")
for pkg in packages:
    try:
        __import__(pkg)
        print(f"[OK] {pkg}")
    except ImportError:
        print(f"[MISSING] {pkg}")
        missing.append(pkg)

if missing:
    print("\nMissing packages found. I will need to set up a venv for these.")
    sys.exit(1)
else:
    print("\nAll dependencies met!")
    sys.exit(0)
