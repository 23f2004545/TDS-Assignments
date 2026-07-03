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


@app.route("/dynamic-extract", methods=["POST"])
def dynamic_extract():

    data = request.get_json()

    text = data["text"]
    schema = data["schema"]

    prompt = f"""
Extract information from the following text.

Text:
{text}

Return ONLY valid JSON.

Rules:

- Output EXACTLY these keys:
{json.dumps(schema, indent=2)}

- Do NOT invent keys.
- Missing values -> null.
- integer -> JSON integer
- float -> JSON number
- boolean -> true/false
- date -> YYYY-MM-DD
- array[string] -> JSON array
- array[integer] -> JSON array
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    answer = response.text.strip()

    if answer.startswith("```"):
        answer = answer.replace("```json", "")
        answer = answer.replace("```", "").strip()

    return jsonify(json.loads(answer))


if __name__ == "__main__":
    app.run()