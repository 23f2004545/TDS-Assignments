from fastapi import FastAPI, HTTPException
from schemas import ProposeRequest, CommitRequest

app = FastAPI()


@app.get("/")
def root():
    return {"status": "mailroom running"}


@app.post("/actions")
def actions(request: dict):

    operation = request.get("operation")

    if operation == "propose":

        data = ProposeRequest(**request)

        proposals = []

        for dossier in data.dossiers:

            proposals.append(
                {
                    "dossierId": dossier.dossierId,
                    "callId": "placeholder",
                    "action": "no_action",
                    "target": None,
                    "payload": {
                        "reasonCode": "INFORMATIONAL",
                        "referenceId": ""
                    },
                    "evidence": []
                }
            )

        return {
            "profile": data.profile,
            "evaluationId": data.evaluationId,
            "status": "awaiting_receipts",
            "inputDigest": "",
            "proposals": proposals
        }

    elif operation == "commit":

        data = CommitRequest(**request)

        outcomes = []

        for receipt in data.receipts:

            outcomes.append(
                {
                    "dossierId": receipt.dossierId,
                    "callId": receipt.callId,
                    "action": receipt.action,
                    "proposalDigest": receipt.proposalDigest,
                    "receiptId": receipt.receiptId,
                    "status": "executed" if receipt.accepted else "rejected"
                }
            )

        return {
            "profile": data.profile,
            "evaluationId": data.evaluationId,
            "status": "completed",
            "inputDigest": data.inputDigest,
            "outcomes": outcomes
        }

    raise HTTPException(400, "Unknown operation")