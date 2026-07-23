import hashlib
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

EMAIL = "23f2004545@ds.study.iitm.ac.in".strip().lower()

app = FastAPI()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    print("\n" + "=" * 70)
    print(request.method, request.url.path)
    print(dict(request.headers))

    try:
        body = await request.body()
        if body:
            print(body.decode(errors="ignore"))
    except Exception:
        pass

    response = await call_next(request)

    print("STATUS:", response.status_code)
    print("=" * 70 + "\n")

    return response


@app.get("/")
async def root():
    return {"status": "running"}


@app.post("/mcp")
async def mcp(request: Request):
    payload = await request.json()

    print("JSON:", payload)

    method = payload.get("method")
    req_id = payload.get("id")

    # -------------------------
    # initialize
    # -------------------------
    if method == "initialize":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2025-03-26",
                    "serverInfo": {
                        "name": "tds-mcp",
                        "version": "1.0.0"
                    },
                    "capabilities": {
                        "tools": {}
                    }
                }
            }
        )

    # -------------------------
    # initialized notification
    # -------------------------
    if method == "notifications/initialized":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "result": None
            }
        )

    # -------------------------
    # tools/list
    # -------------------------
    if method == "tools/list":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "solve_challenge",
                            "description": "Solve IITM challenge.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {},
                                "required": []
                            }
                        }
                    ]
                }
            }
        )

    # -------------------------
    # tools/call
    # -------------------------
    if method == "tools/call":

        challenge = request.headers.get("X-Exam-Challenge", "")

        answer = hashlib.sha256(
            f"{challenge}:{EMAIL}".encode()
        ).hexdigest()[:16]

        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": answer
                        }
                    ]
                }
            }
        )

    # -------------------------
    # unknown
    # -------------------------
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": "Method not found"
            }
        },
        status_code=404
    )