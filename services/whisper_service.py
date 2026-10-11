#!/usr/bin/env python3
"""HTTP wrapper around whisper-cli. Runs on the UNO Q host (not in App Lab container)."""
from flask import Flask, request, jsonify
import os, subprocess, tempfile

WHISPER_BIN = os.path.expanduser("~/whisper.cpp/build/bin/whisper-cli")
WHISPER_MODEL = os.path.expanduser("~/nightsky-whisperer/models/ggml-tiny.en.bin")

app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "bin_exists": os.path.exists(WHISPER_BIN),
        "model_exists": os.path.exists(WHISPER_MODEL),
    })

@app.route("/transcribe", methods=["POST"])
def transcribe():
    wav_bytes = request.data
    if not wav_bytes:
        return jsonify({"error": "empty body"}), 400

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        path = f.name

    try:
        r = subprocess.run(
            [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", path,
             "--no-timestamps", "--no-prints"],
            capture_output=True, text=True, timeout=60)
        text = r.stdout.strip().replace("[BLANK_AUDIO]", "").strip()
        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.unlink(path)

if __name__ == "__main__":
    print(f"whisper-service on 0.0.0.0:8081")
    print(f"  bin:   {WHISPER_BIN}  exists={os.path.exists(WHISPER_BIN)}")
    print(f"  model: {WHISPER_MODEL}  exists={os.path.exists(WHISPER_MODEL)}")
    app.run(host="0.0.0.0", port=8081, threaded=True)
