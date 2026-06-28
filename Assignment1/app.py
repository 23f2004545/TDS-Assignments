from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uuid
import time

app = FastAPI()

EMAIL = "23f2004545@ds.study.iitm.ac.in"


@app.middleware("http")
async def add_request_headers(request: Request, call_next):
    """
    Middleware executed for every request.

    Adds:
    - X-Request-ID
    - X-Process-Time
    """

    request_id = str(uuid.uuid4())

    start_time = time.perf_counter()

    response = await call_next(request)

    process_time = time.perf_counter() - start_time

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.6f}"

    return response


@app.get("/")
def home():
    return {"message": "API Running"}


@app.get("/stats")
def stats(values: str):
    """
    Example:
    /stats?values=1,2,3,4,5
    """

    try:
        numbers = [int(x.strip()) for x in values.split(",")]

    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"error": "values must be comma-separated integers"},
        )

    count = len(numbers)
    total = sum(numbers)
    minimum = min(numbers)
    maximum = max(numbers)
    mean = total / count

    return {
        "email": EMAIL,
        "count": count,
        "sum": total,
        "min": minimum,
        "max": maximum,
        "mean": mean,
    }