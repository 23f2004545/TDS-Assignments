import os
import base64

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

app = Flask(__name__)
CORS(app)


@app.route("/answer-image", methods=["POST"])
def answer_image():
    try:
        data = request.get_json()

        image_base64 = data["image_base64"]
        question = data["question"]

        image_bytes = base64.b64decode(image_base64)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/png"
                ),
                f"""
Answer the following question about the image.

Rules:
- Return ONLY the answer.
- No explanation.
- If numeric, return only the number.
- Do not include units or currency symbols.

Question:
{question}
"""
            ]
        )

        answer = response.text.strip()

        return jsonify({
            "answer": answer
        })

    except Exception as e:
        return jsonify({
            "answer": "",
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)