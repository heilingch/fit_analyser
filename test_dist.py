import math
from fitparse import FitFile

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

f = FitFile('2026-04-11-14-10-08_fixed.fit')
pts = []
for r in f.get_messages('record'):
    lat, lon = r.get_value('position_lat'), r.get_value('position_long')
    if lat is not None and lon is not None:
        pts.append((lat * 180.0 / 2**31, lon * 180.0 / 2**31))

dist = 0
for i in range(1, len(pts)):
    dist += haversine(pts[i-1][0], pts[i-1][1], pts[i][0], pts[i][1])

print(f'Geo distance: {dist/1000.0:.2f} km')
print(f'Points count: {len(pts)}')
if pts:
    gap = haversine(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1])
    print(f'Gap to start: {gap/1000.0:.2f} km')
