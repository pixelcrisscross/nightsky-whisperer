"""Dependency-free pointing-vector math for NightSky Whisperer.

Android TYPE_ROTATION_VECTOR is (x, y, z[, w]). The Android rotation matrix
uses device axes +X=screen-right, +Y=phone-top-edge, +Z=out of the screen.
The world frame is interpreted as east, north, up. The two likely physical
pointing axes are returned separately; calibration is required before astronomy.
"""
from __future__ import annotations

import math
from typing import Any, Iterable


def _finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _rotation_matrix(rotation_vector: Iterable[float]) -> list[float]:
    # This helper receives only the quaternion portion (x, y, z[, w]); any
    # optional fifth Android value is heading-accuracy metadata, not quaternion data.
    values = [float(v) for v in rotation_vector]
    if len(values) not in (3, 4):
        raise ValueError("quaternion portion must contain 3 or 4 numeric components")
    if not all(math.isfinite(v) for v in values):
        raise ValueError("rotation_vector quaternion contains non-finite values")

    x, y, z = values[:3]
    w = values[3] if len(values) == 4 else math.sqrt(max(0.0, 1.0 - x*x - y*y - z*z))

    # Same row-major quaternion-to-matrix layout used by Android SensorManager.
    return [
        1.0 - 2.0*y*y - 2.0*z*z,
        2.0*x*y - 2.0*z*w,
        2.0*x*z + 2.0*y*w,
        2.0*x*y + 2.0*z*w,
        1.0 - 2.0*x*x - 2.0*z*z,
        2.0*y*z - 2.0*x*w,
        2.0*x*z - 2.0*y*w,
        2.0*y*z + 2.0*x*w,
        1.0 - 2.0*x*x - 2.0*y*y,
    ]


def _axis_alt_az(east: float, north: float, up: float,
                 magnetic_declination_deg: float | None) -> dict[str, Any]:
    norm = math.sqrt(east*east + north*north + up*up)
    if norm <= 1e-12:
        raise ValueError("invalid zero-length pointing vector")
    east, north, up = east/norm, north/norm, up/norm
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, up))))
    sensor_azimuth = math.degrees(math.atan2(east, north)) % 360.0
    true_azimuth = None
    if magnetic_declination_deg is not None:
        # GeomagneticField declination is positive east; true bearing = magnetic + declination.
        true_azimuth = round((sensor_azimuth + magnetic_declination_deg) % 360.0, 3)
    return {
        "vector_enu": {"east": round(east, 6), "north": round(north, 6), "up": round(up, 6)},
        "elevation_deg": round(elevation, 3),
        "magnetic_or_sensor_azimuth_deg": round(sensor_azimuth, 3),
        "true_azimuth_deg": true_azimuth,
    }


def compute_pointing(rotation_vector: Any,
                     magnetic_declination_deg: Any = None) -> dict[str, Any]:
    """Compute top-edge and screen-normal directions from Android telemetry."""
    if not isinstance(rotation_vector, (list, tuple)):
        return {"available": False, "error": "rotation_vector is missing or is not an array"}
    if len(rotation_vector) not in (3, 4, 5):
        return {
            "available": False,
            "error": "rotation_vector must contain 3, 4, or 5 values from Android TYPE_ROTATION_VECTOR",
        }

    # Android TYPE_ROTATION_VECTOR may provide 3 values (x,y,z), 4 values
    # (x,y,z,w), or 5 values (x,y,z,w,estimated heading accuracy in radians).
    # Only the quaternion components belong in the rotation-matrix calculation.
    quaternion = rotation_vector[:4]
    if not all(_finite_number(v) for v in quaternion):
        return {"available": False, "error": "rotation_vector quaternion has invalid components"}

    try:
        matrix = _rotation_matrix(quaternion)
        declination = float(magnetic_declination_deg) if _finite_number(magnetic_declination_deg) else None
        heading_accuracy = None
        if len(rotation_vector) == 5 and _finite_number(rotation_vector[4]):
            heading_accuracy = float(rotation_vector[4])
        # Columns of Android's row-major matrix are device axes expressed in world coordinates.
        top_edge = _axis_alt_az(matrix[1], matrix[4], matrix[7], declination)
        screen_normal = _axis_alt_az(matrix[2], matrix[5], matrix[8], declination)
        return {
            "available": True,
            "coordinate_frame": "ENU (east, north, up)",
            "selected_axis": "top_edge",
            "magnetic_declination_deg": round(declination, 3) if declination is not None else None,
            "android_heading_accuracy_rad": round(heading_accuracy, 6) if heading_accuracy is not None else None,
            "top_edge": top_edge,
            "screen_normal": screen_normal,
            "calibration_required": True,
            "calibration_note": (
                "Aim the phone at a known direction and decide whether its top edge or screen normal "
                "matches the intended pointer axis. Validate several tilts before astronomy matching."
            ),
        }
    except (TypeError, ValueError, OverflowError) as exc:
        return {"available": False, "error": str(exc)}
