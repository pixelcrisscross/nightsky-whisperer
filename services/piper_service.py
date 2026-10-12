#!/usr/bin/env python3
"""HTTP wrapper around piper. Runs on the UNO Q host (not in App Lab container).

Legacy standalone wrapper. The active voice pipeline runs Piper in-process
from uno-q/server.py; this file is kept for manual testing and for callers
that want a network-only dependency on piper.
"""
from flask import Flask, request, send_file, jsonify
import os, subprocess, tempfile

PIPER_BIN = os.path.expanduser("~/nightsky/.venv/bin/piper")
PIPER_MODEL = os.path.expanduser("~/nightsky-whisperer/models/en_GB-alba-medium.onnx")

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "bin_exists": os.path.exists(PIPER_BIN),
        "model_exists": os.path.exists(PIPER_MODEL),
    })


@app.route("/synthesize", methods=["POST"])
def synthesize():
    text = request.data.decode("utf-8").strip()
    if not text:
        return "empty text", 400

    out = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run(
            [PIPER_BIN, "-m", PIPER_MODEL, "-f", out],
            input=text.encode(), check=True, timeout=60,
        )
        return send_file(out, mimetype="audio/wav")
    except Exception as e:
        return f"piper failed: {e}", 500


if __name__ == "__main__":
    print(f"piper-service on 0.0.0.0:8082")
    print(f"  bin:   {PIPER_BIN}  exists={os.path.exists(PIPER_BIN)}")
    print(f"  model: {PIPER_MODEL}  exists={os.path.exists(PIPER_MODEL)}")
    app.run(host="0.0.0.0", port=8082, threaded=True)
