from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid
import time

EMAIL = "23f2004545@ds.study.iitm.ac.in"

ALLOWED_ORIGIN = "https://dash-ja7woi.example.com"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()

    response = await call_next(request)

    process_time = time.perf_counter() - start

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.6f}"

    return response


@app.get("/")
def home():
    return {"status": "ok"}


@app.get("/stats")
def stats(values: str):
    try:
        nums = [int(x.strip()) for x in values.split(",")]

        return {
            "email": EMAIL,
            "count": len(nums),
            "sum": sum(nums),
            "min": min(nums),
            "max": max(nums),
            "mean": sum(nums) / len(nums),
        }

    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid input"},
        )