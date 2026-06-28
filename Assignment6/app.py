from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
import uuid
import time
from collections import deque

EMAIL = "23f2004545@ds.study.iitm.ac.in"

app = FastAPI()

START_TIME = time.time()

REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP Requests"
)

LOGS = deque(maxlen=1000)


@app.middleware("http")
async def middleware(request: Request, call_next):
    REQUESTS.inc()

    rid = str(uuid.uuid4())

    LOGS.append({
        "level": "INFO",
        "ts": time.time(),
        "path": request.url.path,
        "request_id": rid
    })

    response = await call_next(request)

    response.headers["X-Request-ID"] = rid

    return response


@app.get("/")
def home():
    return {"status": "ok"}


@app.get("/work")
def work(n: int):
    return {
        "email": EMAIL,
        "done": n
    }


@app.get("/metrics")
def metrics():
    return PlainTextResponse(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


@app.get("/healthz")
def health():
    return {
        "status": "ok",
        "uptime_s": time.time() - START_TIME
    }


@app.get("/logs/tail")
def logs(limit: int = 10):
    return list(LOGS)[-limit:]