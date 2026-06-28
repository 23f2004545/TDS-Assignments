from fastapi import FastAPI
from pydantic import BaseModel
import requests

app = FastAPI()

OLLAMA_URL = "https://aggregate-appear-realtor-jefferson.trycloudflare.com/v1/chat/completions"
MODEL = "llama3.2"


class ExtractRequest(BaseModel):
    text: str


class ExtractResponse(BaseModel):
    vendor: str
    amount: float
    currency: str
    date: str


@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest):

    prompt = f"""
Extract these invoice fields.

Return ONLY valid JSON.

Schema:
{{
  "vendor": "...",
  "amount": 0,
  "currency": "USD",
  "date": "YYYY-MM-DD"
}}

Invoice:

{req.text}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "stream": False,
            "temperature": 0,
            "response_format": {
                "type": "json_object"
            },
        },
        timeout=60,
    )

    data = response.json()

    content = data["choices"][0]["message"]["content"]

    import json

    obj = json.loads(content)

    return ExtractResponse(**obj)