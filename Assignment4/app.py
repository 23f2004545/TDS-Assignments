from fastapi import FastAPI
import redis
import os

app = FastAPI()

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=6379,
    decode_responses=True
)


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/hit/{key}")
def hit(key: str):
    count = r.incr(key)
    return {
        "key": key,
        "count": count
    }


@app.get("/count/{key}")
def count(key: str):
    value = r.get(key)

    return {
        "key": key,
        "count": int(value) if value else 0
    }


@app.get("/healthz")
def health():

    try:
        r.ping()

        return {
            "status": "ok",
            "redis": "up"
        }

    except Exception:

        return {
            "status": "fail",
            "redis": "down"
        }