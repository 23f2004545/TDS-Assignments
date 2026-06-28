from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import uuid
import time

EMAIL = "23f2004545@ds.study.iitm.ac.in"

WINDOW = 10
LIMIT = 15

clients = {}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app-5zwmao.example.com",
        "https://exam.sanand.workers.dev"
    ],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def middleware(request: Request, call_next):

    rid = request.headers.get(
        "X-Request-ID",
        str(uuid.uuid4())
    )

    client = request.headers.get(
        "X-Client-Id",
        "default"
    )

    now = time.time()

    history = clients.setdefault(client, [])

    history[:] = [t for t in history if now - t < WINDOW]

    if len(history) >= LIMIT:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"}
        )

    history.append(now)

    response = await call_next(request)

    response.headers["X-Request-ID"] = rid

    request.state.request_id = rid

    return response


@app.options("/ping")
def options():
    response = Response()

    response.headers["Access-Control-Allow-Origin"] = "https://app-5zwmao.example.com"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"

    return response


@app.get("/ping")
def ping(request: Request):

    return {
        "email": EMAIL,
        "request_id": request.state.request_id
    }