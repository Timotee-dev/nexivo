"""
Lightweight geolocation helpers for 'nearby events' search.
Uses the haversine formula directly in Python for SQLite/dev portability;
on PostgreSQL in production this can be swapped for PostGIS or the
ST_DistanceSphere function for better performance at scale, but the public
function signature (annotate_distance / nearby_queryset) stays the same so
callers don't need to change.
"""

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearby_event_ids(queryset, latitude, longitude, radius_km=50):
    """
    Returns a list of (event_id, distance_km) tuples for events within
    radius_km of the given point, sorted by distance ascending.
    Filters in Python after a coarse bounding-box DB filter, which is
    efficient enough for a reasonable number of physical events per city.
    """
    lat, lon = float(latitude), float(longitude)

    # Coarse bounding box (~1 degree latitude ≈ 111km) to cut down rows before
    # computing exact great-circle distance in Python.
    deg_radius = radius_km / 111.0
    coarse_qs = queryset.filter(
        latitude__isnull=False,
        longitude__isnull=False,
        latitude__gte=lat - deg_radius,
        latitude__lte=lat + deg_radius,
        longitude__gte=lon - deg_radius,
        longitude__lte=lon + deg_radius,
    )

    results = []
    for event in coarse_qs:
        distance = haversine_km(lat, lon, event.latitude, event.longitude)
        if distance <= radius_km:
            results.append((event.id, round(distance, 2)))

    results.sort(key=lambda pair: pair[1])
    return results
