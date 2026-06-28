from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from threading import Lock
import uuid
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://exam.sanand.workers.dev"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

TOTAL = 49
RATE_LIMIT = 19
WINDOW = 10

orders = {}
client_requests = {}
lock = Lock()


def check_rate(client_id: str):
    now = time.time()

    with lock:
        history = client_requests.setdefault(client_id, [])

        history[:] = [
            t for t in history
            if now - t < WINDOW
        ]

        if len(history) >= RATE_LIMIT:
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded"
                },
            )
            response.headers["Retry-After"] = "10"
            return response

        history.append(now)

    return None


@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    x_client_id: str = Header("default", alias="X-Client-Id"),
):

    rate = check_rate(x_client_id)
    if rate:
        return rate

    if idempotency_key not in orders:
        orders[idempotency_key] = {
            "id": str(uuid.uuid4())
        }

    return orders[idempotency_key]


@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: str = "1",
    x_client_id: str = Header("default", alias="X-Client-Id"),
):

    rate = check_rate(x_client_id)
    if rate:
        return rate

    start = max(int(cursor), 1)

    end = min(start + limit - 1, TOTAL)

    items = [
        {"id": i}
        for i in range(start, end + 1)
    ]

    next_cursor = str(end + 1) if end < TOTAL else ""

    return {
        "items": items,
        "next_cursor": next_cursor,
    }