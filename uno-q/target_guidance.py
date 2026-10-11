"""Coarse sky-relative guidance for the NightSky Whisperer prototype.

This intentionally reports world azimuth/elevation directions first. Mapping these
labels to the physical LED matrix requires verifying how the matrix is mounted.
"""
from __future__ import annotations
import math
from typing import Any


def wrap180(degrees: float) -> float:
    return (float(degrees) + 180.0) % 360.0 - 180.0


def _vector(azimuth_deg: float, altitude_deg: float) -> tuple[float, float, float]:
    az = math.radians(azimuth_deg)
    alt = math.radians(altitude_deg)
    return (math.cos(alt) * math.sin(az), math.cos(alt) * math.cos(az), math.sin(alt))


def angular_separation_deg(az1: float, alt1: float, az2: float, alt2: float) -> float:
    a = _vector(az1, alt1)
    b = _vector(az2, alt2)
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))
    return math.degrees(math.acos(dot))


def calculate_guidance(
    current_azimuth_deg: float,
    current_altitude_deg: float,
    target_azimuth_deg: float,
    target_altitude_deg: float,
    acquisition_radius_deg: float = 2.0,
) -> dict[str, Any]:
    values = (current_azimuth_deg, current_altitude_deg, target_azimuth_deg,
              target_altitude_deg, acquisition_radius_deg)
    if not all(math.isfinite(float(v)) for v in values):
        raise ValueError("pointing and target coordinates must be finite")
    if not -90.0 <= float(current_altitude_deg) <= 90.0:
        raise ValueError("current altitude must be between -90 and 90 degrees")
    if not -90.0 <= float(target_altitude_deg) <= 90.0:
        raise ValueError("target altitude must be between -90 and 90 degrees")
    if not 0.0 < float(acquisition_radius_deg) <= 10.0:
        raise ValueError("acquisition radius must be greater than 0 and at most 10 degrees")

    az_delta = wrap180(float(target_azimuth_deg) - float(current_azimuth_deg))
    alt_delta = float(target_altitude_deg) - float(current_altitude_deg)
    separation = angular_separation_deg(current_azimuth_deg, current_altitude_deg,
                                        target_azimuth_deg, target_altitude_deg)
    # Azimuth lines converge near the zenith. Scale the horizontal angular
    # difference by cos(altitude) for a more reasonable coarse 2D steering choice.
    horizontal_delta = az_delta * math.cos(math.radians(float(current_altitude_deg)))
    if separation <= acquisition_radius_deg:
        direction, arrow, acquired = "target_acquired", "✦", True
    elif separation >= 90.0:
        direction, arrow, acquired = "turn_around", "↻", False
    elif abs(horizontal_delta) >= abs(alt_delta):
        if abs(horizontal_delta) < 0.25:
            direction, arrow, acquired = "hold", "·", False
        elif az_delta > 0.0:
            direction, arrow, acquired = "right", "→", False
        else:
            direction, arrow, acquired = "left", "←", False
    else:
        if abs(alt_delta) < 0.25:
            direction, arrow, acquired = "hold", "·", False
        elif alt_delta > 0.0:
            direction, arrow, acquired = "up", "↑", False
        else:
            direction, arrow, acquired = "down", "↓", False

    return {
        "direction": direction,
        "arrow": arrow,
        "acquired": acquired,
        "angular_separation_deg": round(separation, 3),
        "acquisition_radius_deg": round(float(acquisition_radius_deg), 3),
        "azimuth_delta_deg": round(az_delta, 3),
        "altitude_delta_deg": round(alt_delta, 3),
        "horizontal_delta_scaled_deg": round(horizontal_delta, 3),
    }
