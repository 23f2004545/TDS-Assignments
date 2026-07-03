import os
import base64

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

app = Flask(__name__)
CORS(app)

@app.route("/answer-image", methods=["POST"])
def answer_image():
    try:
        data = request.get_json(force=True)

        image_base64 = data.get("image_base64")
        question = data.get("question")

        if not image_base64 or not question:
            return jsonify({"answer": ""}), 400

        image_bytes = base64.b64decode(image_base64)

        # Detect image type
        if image_bytes.startswith(b"\x89PNG"):
            mime_type = "image/png"
        elif image_bytes.startswith(b"\xff\xd8\xff"):
            mime_type = "image/jpeg"
        else:
            mime_type = "image/png"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                ),
                types.Part.from_text(
                    text=f"""
Answer the question about the image.

Rules:
- Return ONLY the answer.
- No explanation.
- No markdown.
- If numeric, return only the number.
- Do not include units or currency symbols.

Question:
{question}
"""
                ),
            ],
        )

        answer = ""

        if getattr(response, "text", None):
            answer = response.text.strip()

        return jsonify({"answer": answer})

    except Exception as e:
        print(e)
        return jsonify({"answer": "", "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)