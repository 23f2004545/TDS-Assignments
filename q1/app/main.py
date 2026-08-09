from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .policy import evaluate_release_gate


app = FastAPI(
    title="GitHub Actions Release Gate",
    version="1.0.0",
)


@app.get("/")
async def root():
    return {
        "service": "github-actions-release-gate",
        "status": "ok",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }


@app.post("/release-gate")
async def release_gate(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=200,
            content={
                "decision": "block",
                "violations": [
                    "EXCESS_PERMISSION",
                    "TESTS_INCOMPLETE",
                    "MUTABLE_ACTION",
                    "SINGLE_STAGE_IMAGE",
                    "ROOT_RUNTIME",
                    "SECRET_IN_LAYER",
                    "CRITICAL_CVE",
                    "UNPINNED_IMAGE",
                ],
            },
        )

    result = evaluate_release_gate(payload)

    return JSONResponse(
        status_code=200,
        content=result,
    )
    