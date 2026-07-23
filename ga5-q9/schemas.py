from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel


class Line(BaseModel):
    lineId: str
    text: str


class Source(BaseModel):
    sourceId: str
    kind: str
    provenance: str
    title: str
    lines: List[Line]


class Dossier(BaseModel):
    dossierId: str
    partition: Literal["stable_core", "fresh_audit"]
    receivedAt: str
    mailbox: str
    objective: str
    sources: List[Source]


class ProposeRequest(BaseModel):
    profile: Literal["ga5-mailroom-action-gate/v2"]
    operation: Literal["propose"]
    evaluationId: str
    corpus: Dict[str, Any]
    allowedActions: List[str]
    dossiers: List[Dossier]


class CommitReceipt(BaseModel):
    dossierId: str
    callId: str
    action: str
    accepted: bool
    proposalDigest: str
    receiptId: str


class CommitRequest(BaseModel):
    profile: Literal["ga5-mailroom-action-gate/v2"]
    operation: Literal["commit"]
    evaluationId: str
    inputDigest: str
    receipts: List[CommitReceipt]