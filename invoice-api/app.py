import os
import json

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

app = Flask(__name__)
CORS(app)


PROMPT = """
You are an invoice extraction engine.

Extract exactly these six fields.

Return ONLY valid JSON.

Schema:

{
  "invoice_no": string or null,
  "date": string (YYYY-MM-DD) or null,
  "vendor": string or null,
  "amount": number or null,
  "tax": number or null,
  "currency": string or null
}

Rules:
- amount = subtotal before tax.
- tax = tax amount only.
- date must always be YYYY-MM-DD.
- Never return markdown.
- Never explain anything.
"""


@app.route("/extract", methods=["POST"])
def extract():

    try:
        invoice_text = request.json.get("invoice_text", "")

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=f"{PROMPT}\n\nInvoice:\n{invoice_text}"
        )

        text = response.text.strip()

        data = json.loads(text)

        required = [
            "invoice_no",
            "date",
            "vendor",
            "amount",
            "tax",
            "currency",
        ]

        for key in required:
            data.setdefault(key, None)

        return jsonify(data)

    except Exception as e:
        print(e)
        return jsonify(
            {
                "invoice_no": None,
                "date": None,
                "vendor": None,
                "amount": None,
                "tax": None,
                "currency": None,
                "error": str(e),
            }
        ), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)