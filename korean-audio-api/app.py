import base64
import json
import re
from statistics import (
    mean,
    median,
    mode,
    pstdev,
    pvariance,
)

from fastapi import FastAPI, APIRouter, Request
from google import genai
from google.genai import types

from config import config

def parse_json(text: str):
    """
    Extract the first JSON object from an LLM response.
    Handles responses wrapped in ```json ... ``` fences.
    """
    text = text.strip()

    # Remove markdown code fences if present
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: extract first JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError("No valid JSON found in model response.")

router = APIRouter()

app = FastAPI()

app.include_router(router)

# Gemini client
client = genai.Client(api_key=config.GEMINI_API_KEY)

last_debug_info = {}


@router.get("/debug")
def get_debug():
    return last_debug_info


@router.post("/answer-audio")
async def answer_audio(request: Request):
    global last_debug_info

    body = await request.json()
    last_debug_info = {"body_id": body.get("audio_id")}

    audio_b64 = body.get("audio_base64", "")
    transcript = ""

    try:
        audio_bytes = base64.b64decode(audio_b64)

        mime_type = "audio/wav"

        if audio_bytes.startswith(b"ID3") or audio_bytes.startswith(b"\xff\xfb"):
            mime_type = "audio/mpeg"

        elif audio_bytes.startswith(b"OggS"):
            mime_type = "audio/ogg"

        elif audio_bytes.startswith(b"fLaC"):
            mime_type = "audio/flac"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                "Transcribe this audio precisely in Korean. Output ONLY the Korean transcription, nothing else.",
                types.Part.from_bytes(
                    data=audio_bytes,
                    mime_type=mime_type,
                ),
            ],
        )

        transcript = response.text.strip()

    except Exception as e:
        last_debug_info["exception"] = str(e)

    last_debug_info["transcript"] = transcript

    prompt = (
        "Read the following Korean transcript about a dataset.\n"
        "1. Extract column names into 'columns'. If it just talks about 'values' (값), use [\"값\"].\n"
        "2. If it asks to GENERATE data (e.g., '140 rows'), set 'num_rows' and leave 'data_rows' empty.\n"
        "3. MUST extract ANY specific constraints into 'explicit_stats'.\n"
        "CRITICAL EXAMPLES for explicit_stats:\n"
        "- '평균' (mean) -> {\"mean\": {\"값\": 170}}\n"
        "- '표준편차' (std) -> {\"std\": {\"값\": 5}}\n"
        "- '~사이' (between X and Y) -> {\"value_range\": {\"값\": [X, Y]}}\n"
        "- '허용값' (allowed values) -> {\"allowed_values\": {\"값\": [A, B]}}\n\n"
        "Return STRICT JSON:\n"
        "{\"columns\": [\"값\"], "
        "\"data_rows\": [], "
        "\"num_rows\": 100, "
        "\"explicit_stats\": {"
        "\"value_range\": {\"값\": [10,20]}}}\n\n"
        f"TRANSCRIPT:\n{transcript}"
    )
    
    columns = []
    data_rows = []
    num_rows = None
    explicit_stats = {}

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        raw_llm = response.text.strip()

        last_debug_info["raw_llm"] = raw_llm

        extracted = parse_json(raw_llm)

        columns = extracted.get("columns", [])
        data_rows = extracted.get("data_rows", []) or []
        num_rows = extracted.get("num_rows")
        explicit_stats = extracted.get("explicit_stats", {})

    except Exception as e:
        last_debug_info["parse_exception"] = str(e)

    if not columns:
        columns = ["값"]

    actual_rows = num_rows if num_rows is not None else len(data_rows)

    out = {
        "rows": actual_rows,
        "columns": columns,
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
        "correlation": [],
    }

    def col_values(col_index):
        values = []

        for row in data_rows:
            try:
                s = str(row[col_index])
                s = re.sub(r"[^\d\.\-]", "", s)

                if s:
                    values.append(float(s))

            except Exception:
                pass

        return values

    for ci, name in enumerate(columns):
        values = col_values(ci)

        if not values:
            continue

        out["mean"][name] = mean(values)
        out["std"][name] = pstdev(values) if len(values) > 1 else 0.0
        out["variance"][name] = pvariance(values) if len(values) > 1 else 0.0
        out["min"][name] = min(values)
        out["max"][name] = max(values)
        out["median"][name] = median(values)

        try:
            out["mode"][name] = mode(values)
        except Exception:
            out["mode"][name] = values[0]

        out["range"][name] = max(values) - min(values)
        out["value_range"][name] = [min(values), max(values)]

    norm_map = {
        "standard_deviation": "std",
        "average": "mean",
        "minimum": "min",
        "maximum": "max",
    }

    for key, value in explicit_stats.items():
        normalized_key = norm_map.get(key, key)

        if isinstance(value, dict):

            if normalized_key in out and isinstance(out[normalized_key], dict):
                out[normalized_key].update(value)

            else:
                for stat_name, stat_value in value.items():
                    normalized_stat = norm_map.get(stat_name, stat_name)

                    if (
                        normalized_stat in out
                        and isinstance(out[normalized_stat], dict)
                    ):
                        out[normalized_stat][key] = stat_value

        else:
            if normalized_key in out and columns:
                out[normalized_key][columns[0]] = value

    return out