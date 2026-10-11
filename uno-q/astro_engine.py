"""Small, offline first astronomy engine for NightSky Whisperer.

Milestone 3 prototype: transforms a curated bright-star catalog from ICRS-like
RA/Dec coordinates into local horizontal coordinates and ranks them against the
phone's calibrated pointing direction. This is intentionally dependency-free.

Limitations:
- This first catalog contains bright stars, not full constellation boundaries.
- Proper motion, precession/nutation, atmospheric refraction, and high-precision
  Earth-orientation corrections are not applied.
- Do not use nearest-star matches for acquisition until compass/cardinal
  calibration has been physically validated.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

# Coordinates are approximate catalog positions in degrees (RA, Dec).
# This compact list is for validating the end-to-end pointing pipeline.
BRIGHT_STARS: list[dict[str, Any]] = [
    {"id": "sirius", "name": "Sirius", "ra_deg": 101.287155, "dec_deg": -16.716116, "magnitude": -1.46, "constellation": "Canis Major"},
    {"id": "canopus", "name": "Canopus", "ra_deg": 95.987878, "dec_deg": -52.695661, "magnitude": -0.74, "constellation": "Carina"},
    {"id": "arcturus", "name": "Arcturus", "ra_deg": 213.915300, "dec_deg": 19.182410, "magnitude": -0.05, "constellation": "Boötes"},
    {"id": "vega", "name": "Vega", "ra_deg": 279.234735, "dec_deg": 38.783689, "magnitude": 0.03, "constellation": "Lyra"},
    {"id": "capella", "name": "Capella", "ra_deg": 79.172327, "dec_deg": 45.997991, "magnitude": 0.08, "constellation": "Auriga"},
    {"id": "rigel", "name": "Rigel", "ra_deg": 78.634467, "dec_deg": -8.201639, "magnitude": 0.13, "constellation": "Orion"},
    {"id": "procyon", "name": "Procyon", "ra_deg": 114.825493, "dec_deg": 5.224993, "magnitude": 0.34, "constellation": "Canis Minor"},
    {"id": "betelgeuse", "name": "Betelgeuse", "ra_deg": 88.792939, "dec_deg": 7.407064, "magnitude": 0.42, "constellation": "Orion"},
    {"id": "achernar", "name": "Achernar", "ra_deg": 24.428523, "dec_deg": -57.236753, "magnitude": 0.46, "constellation": "Eridanus"},
    {"id": "hadar", "name": "Hadar", "ra_deg": 210.955856, "dec_deg": -60.373039, "magnitude": 0.61, "constellation": "Centaurus"},
    {"id": "altair", "name": "Altair", "ra_deg": 297.695827, "dec_deg": 8.868322, "magnitude": 0.77, "constellation": "Aquila"},
    {"id": "aldebaran", "name": "Aldebaran", "ra_deg": 68.980163, "dec_deg": 16.509302, "magnitude": 0.85, "constellation": "Taurus"},
    {"id": "spica", "name": "Spica", "ra_deg": 201.298247, "dec_deg": -11.161322, "magnitude": 0.97, "constellation": "Virgo"},
    {"id": "antares", "name": "Antares", "ra_deg": 247.351915, "dec_deg": -26.432002, "magnitude": 1.06, "constellation": "Scorpius"},
    {"id": "pollux", "name": "Pollux", "ra_deg": 116.328958, "dec_deg": 28.026199, "magnitude": 1.14, "constellation": "Gemini"},
    {"id": "fomalhaut", "name": "Fomalhaut", "ra_deg": 344.412750, "dec_deg": -29.622236, "magnitude": 1.16, "constellation": "Piscis Austrinus"},
    {"id": "deneb", "name": "Deneb", "ra_deg": 310.357979, "dec_deg": 45.280338, "magnitude": 1.25, "constellation": "Cygnus"},
    {"id": "regulus", "name": "Regulus", "ra_deg": 152.092962, "dec_deg": 11.967209, "magnitude": 1.35, "constellation": "Leo"},
    {"id": "castor", "name": "Castor", "ra_deg": 113.649428, "dec_deg": 31.888276, "magnitude": 1.58, "constellation": "Gemini"},
    {"id": "bellatrix", "name": "Bellatrix", "ra_deg": 81.282764, "dec_deg": 6.349703, "magnitude": 1.64, "constellation": "Orion"},
    {"id": "alnilam", "name": "Alnilam", "ra_deg": 84.053389, "dec_deg": -1.201917, "magnitude": 1.69, "constellation": "Orion"},
    {"id": "alnitak", "name": "Alnitak", "ra_deg": 85.189694, "dec_deg": -1.942572, "magnitude": 1.74, "constellation": "Orion"},
    {"id": "mintaka", "name": "Mintaka", "ra_deg": 83.001667, "dec_deg": -0.299095, "magnitude": 2.23, "constellation": "Orion"},
    {"id": "polaris", "name": "Polaris", "ra_deg": 37.954560, "dec_deg": 89.264109, "magnitude": 1.98, "constellation": "Ursa Minor"},
    {"id": "dubhe", "name": "Dubhe", "ra_deg": 165.932000, "dec_deg": 61.751000, "magnitude": 1.79, "constellation": "Ursa Major"},
    {"id": "mizar", "name": "Mizar", "ra_deg": 200.981429, "dec_deg": 54.925362, "magnitude": 2.23, "constellation": "Ursa Major"},
]


def _wrap180(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def julian_date(unix_seconds: float) -> float:
    return float(unix_seconds) / 86400.0 + 2440587.5


def greenwich_mean_sidereal_time_deg(unix_seconds: float) -> float:
    jd = julian_date(unix_seconds)
    d = jd - 2451545.0
    t = d / 36525.0
    return (280.46061837 + 360.98564736629 * d + 0.000387933 * t * t - (t * t * t) / 38710000.0) % 360.0


def radec_to_altaz(ra_deg: float, dec_deg: float, latitude_deg: float,
                   longitude_deg: float, unix_seconds: float) -> dict[str, float]:
    """Convert a star's RA/Dec to local geometric altitude/azimuth.

    Azimuth is measured from true north through east; longitude is positive east.
    """
    values = (ra_deg, dec_deg, latitude_deg, longitude_deg, unix_seconds)
    if not all(math.isfinite(float(v)) for v in values):
        raise ValueError("coordinate inputs must be finite numbers")
    if not -90.0 <= latitude_deg <= 90.0:
        raise ValueError("latitude must be between -90 and 90 degrees")
    if not -90.0 <= dec_deg <= 90.0:
        raise ValueError("declination must be between -90 and 90 degrees")

    lst_deg = (greenwich_mean_sidereal_time_deg(unix_seconds) + longitude_deg) % 360.0
    hour_angle_deg = _wrap180(lst_deg - (ra_deg % 360.0))
    phi = math.radians(latitude_deg)
    dec = math.radians(dec_deg)
    hour_angle = math.radians(hour_angle_deg)

    east = -math.cos(dec) * math.sin(hour_angle)
    north = math.sin(dec) * math.cos(phi) - math.cos(dec) * math.cos(hour_angle) * math.sin(phi)
    up = math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(hour_angle)
    norm = math.sqrt(east * east + north * north + up * up)
    east, north, up = east / norm, north / norm, up / norm
    altitude = math.degrees(math.asin(max(-1.0, min(1.0, up))))
    azimuth = math.degrees(math.atan2(east, north)) % 360.0
    return {
        "azimuth_deg": round(azimuth, 3),
        "altitude_deg": round(altitude, 3),
        "hour_angle_deg": round(hour_angle_deg, 3),
    }


def _horizontal_vector(azimuth_deg: float, altitude_deg: float) -> tuple[float, float, float]:
    az = math.radians(azimuth_deg)
    alt = math.radians(altitude_deg)
    return (math.cos(alt) * math.sin(az), math.cos(alt) * math.cos(az), math.sin(alt))


def _angular_separation_deg(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    dot = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))
    return math.degrees(math.acos(dot))


def visible_bright_stars(latitude_deg: float, longitude_deg: float, unix_seconds: float) -> list[dict[str, Any]]:
    """Return catalog stars geometrically above the horizon, brightest first."""
    visible: list[dict[str, Any]] = []
    for star in BRIGHT_STARS:
        horizontal = radec_to_altaz(star["ra_deg"], star["dec_deg"], latitude_deg, longitude_deg, unix_seconds)
        if horizontal["altitude_deg"] >= 0.0:
            visible.append({**star, **horizontal, "visible_geometrically": True})
    visible.sort(key=lambda item: item["magnitude"])
    return visible


def nearest_bright_stars(latitude_deg: float, longitude_deg: float, unix_seconds: float,
                         pointing_azimuth_deg: float, pointing_altitude_deg: float,
                         limit: int = 5) -> dict[str, Any]:
    """Rank bright-star directions by angular separation from the phone's aim axis."""
    if not all(math.isfinite(float(v)) for v in (latitude_deg, longitude_deg, unix_seconds,
                                                  pointing_azimuth_deg, pointing_altitude_deg)):
        raise ValueError("location, time, and pointing must be finite numbers")
    if not -90.0 <= latitude_deg <= 90.0:
        raise ValueError("latitude must be between -90 and 90 degrees")
    if not -90.0 <= pointing_altitude_deg <= 90.0:
        raise ValueError("pointing elevation must be between -90 and 90 degrees")
    limit = max(1, min(int(limit), 10))
    aim = _horizontal_vector(pointing_azimuth_deg, pointing_altitude_deg)
    ranked: list[dict[str, Any]] = []
    for star in BRIGHT_STARS:
        horizontal = radec_to_altaz(star["ra_deg"], star["dec_deg"], latitude_deg, longitude_deg, unix_seconds)
        star_vec = _horizontal_vector(horizontal["azimuth_deg"], horizontal["altitude_deg"])
        separation = _angular_separation_deg(aim, star_vec)
        ranked.append({
            **star,
            **horizontal,
            "angular_separation_deg": round(separation, 3),
            "visible_geometrically": horizontal["altitude_deg"] >= 0.0,
        })
    ranked.sort(key=lambda item: item["angular_separation_deg"])
    visible_ranked = [row for row in ranked if row["visible_geometrically"]]
    return {
        "catalog_type": "curated_bright_stars_v1",
        "catalog_count": len(BRIGHT_STARS),
        "pointing": {
            "azimuth_deg": round(pointing_azimuth_deg % 360.0, 3),
            "altitude_deg": round(pointing_altitude_deg, 3),
        },
        "nearest_anywhere": ranked[:limit],
        "nearest_visible": visible_ranked[:limit],
        "calibration_required": True,
        "warning": (
            "Diagnostic only: validate cardinal heading and magnetic interference in the assembled "
            "phone+UNO Q setup before trusting target acquisition. This endpoint ranks bright stars "
            "only; it does not yet recognize constellation regions or planets."
        ),
    }

