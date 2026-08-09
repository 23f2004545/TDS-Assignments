from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .policy import evaluate_policy


app = FastAPI(
    title="Terraform Policy Service",
    version="1.0.0",
)


@app.get("/")
async def root():
    return {
        "service": "terraform-policy-service",
        "status": "ok",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }


@app.post("/terraform/plan")
async def terraform_plan(request: Request):
    """
    Evaluate one normalized Terraform resource change.

    We intentionally accept the raw JSON object rather than relying entirely
    on FastAPI/Pydantic validation because malformed-but-valid JSON should
    produce the required:

        {"decision":"reject","reason":"INVALID_PLAN"}

    instead of FastAPI's default 422 response.
    """

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=200,
            content={
                "decision": "reject",
                "reason": "INVALID_PLAN",
            },
        )

    result = evaluate_policy(payload)

    return JSONResponse(
        status_code=200,
        content=result,
    )