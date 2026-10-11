"""NightSky Whisperer: first-stage phone bridge for Arduino UNO Q.

Receives Android sensor/location telemetry over a local WebSocket.
This prototype deliberately does not infer celestial targets yet; orientation
must be calibrated for the phone's physical mounting before target acquisition.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

STATE: dict[str, Any] = {
    "started_at": time.time(),
    "connected_clients": 0,
    "latest_telemetry": None,
    "latest_received_at": None,
    "telemetry_count": 0,
}
_state_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    print("NightSky Whisperer phone bridge starting")
    yield
    print("NightSky Whisperer phone bridge stopping")


app = FastAPI(
    title="NightSky Whisperer Phone Bridge",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": "NightSky Whisperer Phone Bridge",
        "version": "0.1.0",
        "health": "/health",
        "latest_telemetry": "/latest",
        "websocket": "/ws/phone",
    }


@app.get("/health")
async def health() -> JSONResponse:
    async with _state_lock:
        latest_at = STATE["latest_received_at"]
        result = {
            "ok": True,
            "service": "nightsky-phone-bridge",
            "connected_clients": STATE["connected_clients"],
            "telemetry_count": STATE["telemetry_count"],
            "telemetry_age_seconds": round(time.time() - latest_at, 2) if latest_at else None,
            "uptime_seconds": round(time.time() - STATE["started_at"], 2),
        }
    return JSONResponse(result)


@app.get("/latest")
async def latest() -> dict[str, Any]:
    async with _state_lock:
        telemetry = STATE["latest_telemetry"]
        received_at = STATE["latest_received_at"]
    return {
        "available": telemetry is not None,
        "received_at_unix": received_at,
        "telemetry": telemetry,
    }


@app.websocket("/ws/phone")
async def phone_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    async with _state_lock:
        STATE["connected_clients"] += 1
    print(f"[phone] connected from {websocket.client}")

    try:
        await websocket.send_json({
            "type": "hello",
            "protocol_version": 1,
            "service": "nightsky-phone-bridge",
            "message": "Connected. Send telemetry messages as JSON.",
        })
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            if not isinstance(message, dict):
                await websocket.send_json({"type": "error", "message": "Message must be a JSON object"})
                continue

            message_type = message.get("type")
            if message_type == "telemetry":
                received_at = time.time()
                async with _state_lock:
                    STATE["latest_telemetry"] = message
                    STATE["latest_received_at"] = received_at
                    STATE["telemetry_count"] += 1
                    count = STATE["telemetry_count"]

                # Log once every 5 seconds (roughly every 25 samples at 5 Hz).
                if count == 1 or count % 25 == 0:
                    loc = message.get("location") or {}
                    ori = message.get("orientation") or {}
                    print(
                        f"[telemetry #{count}] "
                        f"lat={loc.get('latitude_deg')} lon={loc.get('longitude_deg')} "
                        f"heading={ori.get('phone_top_azimuth_deg')} "
                        f"pitch={ori.get('pitch_deg')} roll={ori.get('roll_deg')}"
                    )

                # Small periodic acknowledgement lets the client show end-to-end health.
                if count == 1 or count % 25 == 0:
                    await websocket.send_json({
                        "type": "ack",
                        "telemetry_count": count,
                        "server_time_unix_ms": int(received_at * 1000),
                    })
            elif message_type == "ping":
                await websocket.send_json({"type": "pong", "server_time_unix_ms": int(time.time() * 1000)})
            else:
                await websocket.send_json({
                    "type": "ack",
                    "message_type": message_type,
                    "message": "Message received; this message type is not implemented yet.",
                })
    except WebSocketDisconnect:
        print("[phone] disconnected")
    except Exception as exc:  # Keep the prototype server alive for the next connection.
        print(f"[phone] websocket error: {exc!r}")
        try:
            await websocket.close(code=1011, reason="Internal bridge error")
        except Exception:
            pass
    finally:
        async with _state_lock:
            STATE["connected_clients"] = max(0, STATE["connected_clients"] - 1)


if __name__ == "__main__":
    host = os.getenv("NIGHTSKY_HOST", "0.0.0.0")
    port = int(os.getenv("NIGHTSKY_PORT", "8765"))
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")
