from fastapi import FastAPI , HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
import json
import os , re

app = FastAPI()

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/v1/chat/completions"
)
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

    if not req.text.strip():
        raise HTTPException(
            status_code=422,
            detail=str(e)
        )

    prompt = f"""
Extract the invoice.

Return ONLY valid JSON.

{{
  "vendor": "",
  "amount": 0,
  "currency": "",
  "date": ""
}}

Invoice:

{req.text}
"""

    try:
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "stream": False,
                "temperature": 0
            },
            timeout=120
        )

        r.raise_for_status()

        raw = r.json()
        # print(raw)
        # print(content)

        # support multiple OpenAI-compatible formats
        if "choices" in raw:
            content = raw["choices"][0]["message"]["content"]
        elif "message" in raw:
            content = raw["message"]["content"]
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Unexpected response: {raw}"
            )

        # Extract only the JSON object
        match = re.search(r"\{.*\}", content, re.DOTALL)

        if not match:
            raise HTTPException(
                status_code=422,
                detail="No JSON found in LLM response"
            )

        obj = json.loads(match.group(0))

        return ExtractResponse(**obj)
    except : 
        raise HTTPException(
                status_code=422,
                detail=f"Unexpected response: {raw}"
            )
