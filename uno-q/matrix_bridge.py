
"""Minimal MessagePack RPC client for the UNO Q Arduino Router.

The MCU sketch must expose `show_direction(String direction)` with
Bridge.provide_safe("show_direction", show_direction). The API works from a
regular Python process (not only from inside an App Lab Python app).
"""
from __future__ import annotations

import itertools
import os
import socket
import time
from pathlib import Path
from typing import Any

import msgpack

DEFAULT_ROUTER_SOCKET = "/var/run/arduino-router.sock"
_request_ids = itertools.count(1)


class RouterRPCError(RuntimeError):
    """Router socket or remote MCU procedure call failed."""


class RouterRPCClient:
    def __init__(self, path: str | Path | None = None, timeout: float = 1.0):
        self.path = Path(path or os.getenv("NIGHTSKY_ROUTER_SOCKET", DEFAULT_ROUTER_SOCKET))
        self.timeout = max(0.1, float(timeout))

    @staticmethod
    def encode_request(request_id: int, method: str, params: list[Any]) -> bytes:
        # Arduino Router RPC MessagePack request: [type=0, id, method, params]
        return msgpack.packb([0, int(request_id), str(method), params], use_bin_type=True)

    def call(self, method: str, *params: Any) -> Any:
        if not self.path.exists():
            raise RouterRPCError(f"Arduino Router socket not found: {self.path}")
        request_id = next(_request_ids)
        payload = self.encode_request(request_id, method, list(params))
        deadline = time.monotonic() + self.timeout
        unpacker = msgpack.Unpacker(raw=False, strict_map_key=False)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.timeout)
                client.connect(str(self.path))
                client.sendall(payload)
                response = None
                while time.monotonic() < deadline:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    unpacker.feed(chunk)
                    try:
                        response = next(unpacker)
                        break
                    except StopIteration:
                        continue
        except (OSError, TimeoutError, msgpack.UnpackException) as exc:
            raise RouterRPCError(f"Router RPC {method!r} failed: {exc}") from exc
        if response is None:
            raise RouterRPCError(f"Router RPC {method!r} returned no response")
        if not isinstance(response, (list, tuple)) or len(response) < 4:
            raise RouterRPCError(f"Unexpected Router RPC response: {response!r}")
        if response[0] != 1:
            raise RouterRPCError(f"Unexpected Router RPC response type: {response[0]!r}")
        if response[1] != request_id:
            raise RouterRPCError(f"Router RPC response ID mismatch: {response[1]!r}")
        if response[2] is not None:
            raise RouterRPCError(f"MCU method {method!r} failed: {response[2]!r}")
        return response[3]


MATRIX_DIRECTIONS = {
    "idle", "up", "down", "left", "right", "hold",
    "turn_around", "target_acquired", "target_below_horizon",
    "listening", "thinking", "speaking", "easter_egg", "error",
}


def validate_direction(direction: str) -> str:
    normalized = str(direction).strip().lower()
    if normalized not in MATRIX_DIRECTIONS:
        raise ValueError(f"Unsupported matrix direction {direction!r}")
    return normalized
