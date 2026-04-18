import fitparse
import sys
from datetime import datetime

fit_file = sys.argv[1]
fitfile = fitparse.FitFile(fit_file, check_crc=False)

records = []
for record in fitfile.get_messages('record'):
    records.append(record.get_values())

if records:
    print(f"First record: {records[0]['timestamp']}")
    print(f"Last record: {records[-1]['timestamp']}")
    
    # Check for any records on April 12th
    april_12 = [r for r in records if r['timestamp'].day == 12]
    print(f"Records on April 12th: {len(april_12)}")
    if april_12:
        print(f"First on April 12th: {april_12[0]['timestamp']}")
