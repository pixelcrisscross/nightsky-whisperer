# NightSky local-link protocol v1

Transport: WebSocket over the trusted local network, TCP port 8765.

Endpoint: `ws://<uno-q-ip>:8765/ws/phone`

Each client-to-server message is one UTF-8 JSON object.

## Telemetry message

```json
{
  "type": "telemetry",
  "protocol_version": 1,
  "device_id": "android-phone",
  "ts_unix_ms": 1791481024000,
  "location": {
    "latitude_deg": 15.8497,
    "longitude_deg": 74.4977,
    "altitude_m": 740.0,
    "accuracy_m": 8.0,
    "provider": "gps",
    "location_time_ms": 1791481023000
  },
  "orientation": {
    "sensor": "TYPE_ROTATION_VECTOR",
    "rotation_vector": [0.1, 0.2, 0.3, 0.9],
    "phone_top_azimuth_deg": 84.3,
    "pitch_deg": 46.2,
    "roll_deg": -2.1,
    "accuracy_code": 3
  }
}
```

Nullable location fields are JSON `null` until Android supplies a fix. Rotation vector length can vary based on platform sensor output; consumers must not assume exactly four components.

Server → client messages:

- `hello`: connection accepted, protocol version and service identity.
- `ack`: occasional telemetry acknowledgement for link-health feedback.
- `error`: message format error.

This version sends no microphone audio and does not yet define the binary audio frame protocol. That is a separate milestone after the sensor channel is stable.
