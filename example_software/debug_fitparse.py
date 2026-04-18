import fitparse
import sys

fit_file = sys.argv[1]
try:
    fitfile = fitparse.FitFile(fit_file, check_crc=False)
    count = 0
    for record in fitfile.get_messages():
        count += 1
    print(f"Total messages read: {count}")
except Exception as e:
    print(f"Error while reading: {e}")
