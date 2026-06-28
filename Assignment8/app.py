from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import JSONResponse
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

    if not req.text or not req.text.strip():
        raise JSONResponse(
            status_code=422,
            detail="Text cannot be empty"
        )

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
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "temperature": 0,
        },
        timeout=60,
    )

    import json

    content = response.json()["choices"][0]["message"]["content"]

    obj = json.loads(content)

    return ExtractResponse(**obj)