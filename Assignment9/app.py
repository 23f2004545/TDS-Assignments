from fastapi import FastAPI, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://exam.sanand.workers.dev"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL = 49
RATE_LIMIT = 19
WINDOW = 10

orders = {}
client_requests = {}


def check_rate(client_id):
    now = time.time()

    history = client_requests.setdefault(client_id, [])

    history[:] = [t for t in history if now - t < WINDOW]

    if len(history) >= RATE_LIMIT:
        raise JSONResponse(
            status_code=429,
            headers={"Retry-After": "10"},
            detail="Rate limit exceeded"
        )

    history.append(now)

@app.options("/orders")
def options_orders():
    response = Response(status_code=204)
    response.headers["Access-Control-Allow-Origin"] = "https://exam.sanand.workers.dev"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


@app.post("/orders", status_code=201)
def create_order(
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    x_client_id: str = Header("default", alias="X-Client-Id")
):

    check_rate(x_client_id)

    if idempotency_key not in orders:
        orders[idempotency_key] = {
            "id": str(uuid.uuid4())
        }

    return orders[idempotency_key]


@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: str | None = None,
    x_client_id: str = Header("default")
):

    check_rate(x_client_id)

    start = int(cursor) if cursor else 1

    end = min(start + limit - 1, TOTAL)

    items = [{"id": i} for i in range(start, end + 1)]

    next_cursor = str(end + 1) if end < TOTAL else None

    return {
        "items": items,
        "next_cursor": next_cursor
    }