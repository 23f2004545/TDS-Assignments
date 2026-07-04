import os
import json
import base64
import hashlib

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


def empty_response():
    return {
        "rows": 0,
        "columns": [],
        "mean": {},
        "std": {},
        "variance": {},
        "min": {},
        "max": {},
        "median": {},
        "mode": {},
        "range": {},
        "allowed_values": {},
        "value_range": {},
        "correlation": []
    }


@app.route("/")
def home():
    return {
        "status": "running"
    }


@app.route("/", methods=["POST"])
def inspect():

    try:

        data = request.get_json(force=True)

        print("\n" + "=" * 80)
        print("NEW REQUEST")
        print("=" * 80)

        print("\nKeys:")
        print(list(data.keys()))

        audio_id = data.get("audio_id")

        audio_b64 = data.get("audio_base64", "")

        print("\naudio_id:")
        print(audio_id)

        print("\nBase64 length:")
        print(len(audio_b64))

        audio_bytes = base64.b64decode(audio_b64)

        print("\nDecoded bytes:")
        print(len(audio_bytes))

        print("\nFirst 64 bytes (hex):")
        print(audio_bytes[:64].hex())

        print("\nFirst 32 raw bytes:")
        print(audio_bytes[:32])

        print("\nSHA256:")
        print(hashlib.sha256(audio_bytes).hexdigest())

        print("\nMagic bytes:")
        print(audio_bytes[:16])

        if audio_bytes.startswith(b"RIFF"):
            print("Detected WAV")

        elif audio_bytes.startswith(b"OggS"):
            print("Detected OGG")

        elif audio_bytes.startswith(b"ID3"):
            print("Detected MP3")

        elif audio_bytes.startswith(b"fLaC"):
            print("Detected FLAC")

        elif audio_bytes.startswith(b"PK"):
            print("Detected ZIP")

        elif audio_bytes.startswith(b"{"):
            print("Detected JSON")

        else:
            print("Unknown format")

        print("=" * 80 + "\n")

        return jsonify(empty_response())

    except Exception as e:

        print(e)

        return jsonify(empty_response())


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )