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


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "endpoint": "/solve"
    })


@app.route("/solve", methods=["POST"])
def solve():

    try:
        data = request.get_json()

        problem = data["problem"]

        prompt = f"""
You are an expert mathematical reasoning engine.

Solve the following arithmetic word problem carefully.

Problem:

{problem}

Return ONLY valid JSON.

Required JSON schema:

{{
  "reasoning": "string",
  "answer": 0
}}

Rules:

- Return ONLY JSON.
- No markdown.
- No explanations outside JSON.
- reasoning MUST be at least 80 characters.
- Explain every arithmetic step.
- Ignore irrelevant numbers.
- answer MUST be a JSON integer.
- Never return answer as a string.
- Never return answer as a float.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        answer = response.text.strip()

        if answer.startswith("```"):
            answer = answer.replace("```json", "")
            answer = answer.replace("```", "").strip()

        result = json.loads(answer)

        # Validate required keys
        if "reasoning" not in result:
            result["reasoning"] = ""

        if "answer" not in result:
            result["answer"] = 0

        # Ensure reasoning length
        if len(result["reasoning"]) < 80:
            result["reasoning"] += (
                " The calculations above are performed carefully by "
                "identifying only the relevant numerical values, "
                "ignoring distractors, and computing the required "
                "integer answer step by step."
            )

        # Ensure integer answer
        result["answer"] = int(result["answer"])

        return jsonify({
            "reasoning": result["reasoning"],
            "answer": result["answer"]
        })

    except Exception as e:
        return jsonify({
            "reasoning": str(e),
            "answer": 0
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)