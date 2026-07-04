import os , json 
import tempfile
import base64
import hashlib

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from mutagen.mp3 import MP3

from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

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

        audio_id = data.get("audio_id")

        audio_b64 = data.get("audio_base64", "")

        audio_bytes = base64.b64decode(audio_b64)

        print("\n")
        print("=" * 80)
        print("NEW AUDIO")
        print("=" * 80)

        print("audio_id:", audio_id)

        print("base64 length:", len(audio_b64))

        print("decoded bytes:", len(audio_bytes))

        print("sha256:", hashlib.sha256(audio_bytes).hexdigest())

        print("first16:", audio_bytes[:16].hex())

        if audio_bytes[:2] == b"\xff\xf3" or audio_bytes[:2] == b"\xff\xfb":
            print("FORMAT: MP3")

        elif audio_bytes.startswith(b"RIFF"):
            print("FORMAT: WAV")

        elif audio_bytes.startswith(b"OggS"):
            print("FORMAT: OGG")

        else:
            print("FORMAT: UNKNOWN")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(audio_bytes)
            filename = f.name

        print("Saved to:", filename)
        
        audio = MP3(filename)

        print("=" * 80)
        print("AUDIO INFO")
        print("=" * 80)
        print("Duration:", audio.info.length)
        print("Bitrate:", audio.info.bitrate)
        print("Sample Rate:", audio.info.sample_rate)
        print("=" * 80)
        
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type="audio/mpeg"
                ),
                """
        You are given a Korean audio recording.

        Understand EVERYTHING spoken.

        Do NOT summarize.

        Do NOT omit constraints.

        Your task is:

        1. Produce a verbatim transcript.

        2. Extract every instruction mentioned.

        This includes:

        - dataset size
        - column names
        - column types
        - categorical values
        - numeric ranges
        - distributions
        - random seed
        - ordering
        - formulas
        - statistical operations
        - every explicit or implicit constraint

        3. Follow those instructions exactly.

        4. Generate the requested dataset.

        5. Compute:

        rows
        columns
        mean
        std
        variance
        min
        max
        median
        mode
        range
        allowed_values
        value_range
        correlation

        Return ONLY valid JSON.

        {
        "debug":{
            "transcript":"",
            "instructions":{}
        },
        "result":{
            "rows":0,
            "columns":[],
            "mean":{},
            "std":{},
            "variance":{},
            "min":{},
            "max":{},
            "median":{},
            "mode":{},
            "range":{},
            "allowed_values":{},
            "value_range":{},
            "correlation":[]
        }
        }

        Do not wrap the JSON inside markdown.
        Do not write anything before or after the JSON.
        """
            ]
        )

        raw = response.text.strip()

        print("\n")
        print("=" * 80)
        print("RAW GEMINI OUTPUT")
        print("=" * 80)
        print(raw)
        print("=" * 80)

        # Remove accidental markdown fences
        raw = raw.replace("```json", "").replace("```", "").strip()

        try:

            parsed = json.loads(raw)

            print("\n")
            print("=" * 80)
            print("TRANSCRIPT")
            print("=" * 80)
            print(parsed["debug"]["transcript"])

            print("\n")
            print("=" * 80)
            print("INSTRUCTIONS")
            print("=" * 80)
            print(json.dumps(parsed["debug"]["instructions"], indent=2, ensure_ascii=False))

            print("=" * 80)

            return jsonify(parsed["result"])

        except Exception as e:

            print("JSON PARSE ERROR:", e)

            return jsonify(empty_response())
    except Exception as e:

        print(e)

        return jsonify(empty_response())
    

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )