"""Local equirectangular projection helpers (metres) for Shapely maths."""
import math
from shapely.geometry import LineString
R = 6371000.0

def haversine(a, b) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1]); dp = p2 - p1
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(h))

def path_length(geom) -> float:
    return sum(haversine(geom[i], geom[i+1]) for i in range(len(geom)-1))

def to_xy(lat, lon, lat0):
    return (math.radians(lon)*R*math.cos(math.radians(lat0)), math.radians(lat)*R)

def from_xy(x, y, lat0):
    return (math.degrees(y/R), math.degrees(x/(R*math.cos(math.radians(lat0)))))

def to_line(geom):
    lat0 = geom[0][0]
    return LineString([to_xy(la, lo, lat0) for la, lo in geom]), lat0

def point_at(geom, dist_m):
    ln, lat0 = to_line(geom)
    p = ln.interpolate(min(max(dist_m, 0), ln.length))
    return from_xy(p.x, p.y, lat0)
