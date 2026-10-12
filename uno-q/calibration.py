"""Persistent cardinal-heading calibration for NightSky Whisperer.

The calibration estimates a constant heading offset from measured true-azimuth
readings captured while the phone's selected pointing axis is aimed horizontally
at independently verified true cardinal directions.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from pathlib import Path
from typing import Any

CARDINAL_AZIMUTHS = {"north": 0.0, "east": 90.0, "south": 180.0, "west": 270.0}
MIN_DIRECTIONS = 3
MAX_RESIDUAL_DEG = 12.0


def wrap180(angle: float) -> float:
    return (float(angle) + 180.0) % 360.0 - 180.0


def circular_mean_deg(angles: list[float]) -> tuple[float, float]:
    """Return circular mean in [0,360) and resultant length [0,1]."""
    if not angles:
        raise ValueError("at least one angle is required")
    radians = [math.radians(float(a)) for a in angles]
    sx = sum(math.cos(a) for a in radians)
    sy = sum(math.sin(a) for a in radians)
    strength = math.hypot(sx, sy) / len(radians)
    if strength < 1e-6:
        raise ValueError("angles have no stable circular mean")
    return math.degrees(math.atan2(sy, sx)) % 360.0, strength


class HeadingCalibration:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.captures: dict[str, dict[str, Any]] = {}
        # Guards captures dict and the on-disk write. RLock so that
        # add_capture can hold it across a nested status() call.
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("version") == 1 and isinstance(data.get("captures"), dict):
                for label, capture in data["captures"].items():
                    if label in CARDINAL_AZIMUTHS and isinstance(capture, dict):
                        self.captures[label] = capture
        except (OSError, ValueError, TypeError):
            # A corrupt calibration must never stop the phone bridge from starting.
            self.captures = {}

    def _save(self) -> None:
        # Caller must hold self._lock.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "captures": self.captures}
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temp_path, self.path)

    def reset(self) -> None:
        with self._lock:
            self.captures = {}
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                self._save()

    def add_capture(
        self,
        direction: str,
        measured_true_azimuth_deg: float,
        elevation_deg: float,
        sample_count: int,
        spread_deg: float,
    ) -> dict[str, Any]:
        label = direction.strip().lower()
        if label not in CARDINAL_AZIMUTHS:
            raise ValueError("direction must be one of: north, east, south, west")
        values = (measured_true_azimuth_deg, elevation_deg, spread_deg)
        if not all(math.isfinite(float(v)) for v in values):
            raise ValueError("calibration values must be finite numbers")
        if abs(float(elevation_deg)) > 10.0:
            raise ValueError("keep the phone's top edge horizontal (elevation within ±10°) before capturing")
        if int(sample_count) < 5:
            raise ValueError("not enough recent sensor samples; keep the phone connected and still for 2–3 seconds")
        if float(spread_deg) > 8.0:
            raise ValueError("heading is moving or unstable; hold the phone still and capture again")

        with self._lock:
            self.captures[label] = {
                "direction": label,
                "known_true_azimuth_deg": CARDINAL_AZIMUTHS[label],
                "measured_true_azimuth_deg": round(float(measured_true_azimuth_deg) % 360.0, 3),
                "elevation_deg": round(float(elevation_deg), 3),
                "sample_count": int(sample_count),
                "spread_deg": round(float(spread_deg), 3),
                "captured_at_unix": round(time.time(), 3),
            }
            self._save()
            return self._status_locked()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_locked()

    def _status_locked(self) -> dict[str, Any]:
        # Caller must hold self._lock.
        labels = [label for label in CARDINAL_AZIMUTHS if label in self.captures]
        missing = [label for label in CARDINAL_AZIMUTHS if label not in self.captures]
        offsets = [
            wrap180(self.captures[label]["known_true_azimuth_deg"] - self.captures[label]["measured_true_azimuth_deg"])
            for label in labels
        ]
        offset = None
        resultant = None
        residuals: dict[str, float] = {}
        max_residual = None
        status = "needs_more_directions"
        if offsets:
            try:
                mean_0_360, resultant = circular_mean_deg(offsets)
                offset = wrap180(mean_0_360)
                residuals = {
                    label: round(wrap180(
                        self.captures[label]["measured_true_azimuth_deg"] + offset
                        - self.captures[label]["known_true_azimuth_deg"]
                    ), 3)
                    for label in labels
                }
                max_residual = round(max(abs(v) for v in residuals.values()), 3)
            except (ValueError, KeyError, TypeError):
                offset = None

        if len(labels) >= MIN_DIRECTIONS and offset is not None:
            if resultant is not None and resultant >= 0.85 and max_residual is not None and max_residual <= MAX_RESIDUAL_DEG:
                status = "validated"
            else:
                status = "needs_review"
        elif labels:
            status = "needs_more_directions"

        return {
            "available": True,
            "status": status,
            "calibrated": status == "validated",
            "capture_count": len(labels),
            "required_directions": list(CARDINAL_AZIMUTHS.keys()),
            "minimum_directions": MIN_DIRECTIONS,
            "captured_directions": labels,
            "missing_directions": missing,
            "heading_offset_deg": round(offset, 3) if offset is not None else None,
            "max_residual_deg": max_residual,
            "offset_consistency": round(resultant, 4) if resultant is not None else None,
            "residuals_by_direction_deg": residuals,
            "max_allowed_residual_deg": MAX_RESIDUAL_DEG,
            "captures": {label: self.captures[label] for label in labels},
            "message": (
                "Heading correction is active. Recheck outdoors with the assembled device before relying on acquisition."
                if status == "validated" else
                "Capture at least three different cardinal directions; four is recommended. Use an independent true-north reference."
                if status == "needs_more_directions" else
                "Cardinal measurements disagree too much for a single offset. Move away from magnetic interference and recapture."
            ),
        }

    def valid_offset(self) -> float | None:
        status = self.status()
        if status["calibrated"]:
            value = status["heading_offset_deg"]
            return float(value) if value is not None else None
        return None
