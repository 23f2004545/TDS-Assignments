from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

EMAIL = "23f2004545@ds.study.iitm.ac.in"
API_KEY = "ak_oquy5rta3zdpgpfoaz38k524"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Event(BaseModel):
    user: str
    amount: float
    ts: int


class AnalyticsRequest(BaseModel):
    events: list[Event]


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/analytics")
def analytics(
    data: AnalyticsRequest,
    x_api_key: str | None = Header(default=None),
):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    total_events = len(data.events)

    unique_users = len(set(e.user for e in data.events))

    revenue = 0.0
    totals = {}

    for e in data.events:
        if e.amount > 0:
            revenue += e.amount
            totals[e.user] = totals.get(e.user, 0) + e.amount

    top_user = max(totals, key=totals.get) if totals else ""

    return {
        "email": EMAIL,
        "total_events": total_events,
        "unique_users": unique_users,
        "revenue": revenue,
        "top_user": top_user,
    }