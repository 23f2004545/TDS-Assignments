import os
import json

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from google import genai

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

app = Flask(__name__)
CORS(app)


@app.route("/extract", methods=["POST"])
def extract():

    try:
        data = request.get_json()

        text = data["text"]
        schema = data["schema"]

        prompt = f"""
You are an expert invoice information extraction engine.

Extract structured information from the invoice text.

Invoice Text:
{text}

Return ONLY valid JSON.

The JSON MUST validate against the following JSON Schema:

{json.dumps(schema, indent=2)}

Rules:

- Return ONLY JSON.
- Do NOT wrap the response inside markdown.
- Do NOT include explanations.
- Do NOT include extra keys.
- Do NOT omit any keys.
- Every key in the schema must exist.
- If a value cannot be extracted, use null.
- Preserve array order exactly as found.
- Dates must be ISO format YYYY-MM-DD.
- Integer values must be JSON integers.
- Float values must be JSON numbers.
- Boolean values must be true or false.
- Strings must remain strings.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        answer = response.text.strip()

        if answer.startswith("```"):
            answer = answer.replace("```json", "")
            answer = answer.replace("```", "").strip()

        parsed = json.loads(answer)

        return jsonify(parsed)

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "endpoint": "/extract"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)