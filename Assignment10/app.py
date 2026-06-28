from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
        "https://exam.sanand.workers.dev",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def middleware(request: Request, call_next):

    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = rid

    client = request.headers.get("X-Client-Id", "default")

    now = time.time()
    history = clients.setdefault(client, [])

    history[:] = [t for t in history if now - t < WINDOW]

    if len(history) >= LIMIT:
        response = JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
        )
        response.headers["X-Request-ID"] = rid
        return response

    history.append(now)

    response = await call_next(request)

    response.headers["X-Request-ID"] = rid

    return response


@app.get("/ping")
def ping(request: Request):
    return {
        "email": EMAIL,
        "request_id": request.state.request_id,
    }