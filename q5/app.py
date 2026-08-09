import json
import math
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


app = FastAPI(
    title="Deterministic Corroboration Service",
    version="1.0.0",
)


VALID_SOURCE_TYPES = {
    "dns",
    "ct_log",
    "registry",
    "archive",
    "scan",
}


def response(
    verdict: str,
    confidence: str,
    corroborating_sources: list[str],
) -> JSONResponse:
    """
    Always return the exact required response shape.
    """
    return JSONResponse(
        content={
            "verdict": verdict,
            "confidence": confidence,
            "corroboratingSources": corroborating_sources,
        }
    )


def parse_timestamp(value: Any) -> datetime | None:
    """
    Parse an ISO-8601 timestamp.

    The API examples use Z, e.g.
    2026-08-01T00:00:00Z

    A naive timestamp is rejected because the specification
    provides timestamps with timezone information.
    """
    if not isinstance(value, str):
        return None

    try:
        normalized = value

        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"

        parsed = datetime.fromisoformat(normalized)

        if parsed.tzinfo is None:
            return None

        return parsed.astimezone(timezone.utc)

    except (TypeError, ValueError, OverflowError):
        return None


def is_valid_number(value: Any) -> bool:
    """
    stalenessDays must be a JSON number.

    bool is intentionally rejected because Python's bool
    is a subclass of int.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def is_valid_source(source: Any) -> bool:
    """
    A valid source requires:
      id       -> string
      origin   -> string
      value    -> string
      observedAt -> string
      type     -> one of the allowed source types

    authoritative is deliberately NOT required to be present or
    a particular type because the specification does not include
    it in the "valid source" definition.
    """
    if not isinstance(source, dict):
        return False

    if not isinstance(source.get("id"), str):
        return False

    if not isinstance(source.get("origin"), str):
        return False

    if not isinstance(source.get("value"), str):
        return False

    if not isinstance(source.get("observedAt"), str):
        return False

    if source.get("type") not in VALID_SOURCE_TYPES:
        return False

    return True


def is_fresh(
    source: dict[str, Any],
    as_of: datetime,
    staleness_days: float,
) -> bool:
    """
    Fresh means:

        asOf - observedAt <= stalenessDays

    No wall clock is consulted anywhere.
    """
    observed_at = parse_timestamp(source["observedAt"])

    if observed_at is None:
        return False

    age = as_of - observed_at
    allowed_age = staleness_days * 86400.0

    return age.total_seconds() <= allowed_age


def parse_request_body(raw_body: bytes) -> Any:
    """
    Parse JSON while rejecting non-standard JSON constants such as
    NaN and Infinity.
    """

    def reject_constant(value: str) -> None:
        raise ValueError(f"Invalid JSON constant: {value}")

    return json.loads(
        raw_body.decode("utf-8"),
        parse_constant=reject_constant,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/corroborate")
async def corroborate(request: Request) -> JSONResponse:
    # ---------------------------------------------------------
    # RULE 1
    #
    # invalid / low / []
    #
    # Conditions:
    # - body is not an object
    # - claim.value is not a string
    # - asOf missing or unparseable
    # - stalenessDays is not a number
    # - sources is not an array
    # ---------------------------------------------------------

    try:
        raw_body = await request.body()
        body = parse_request_body(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return response("invalid", "low", [])

    if not isinstance(body, dict):
        return response("invalid", "low", [])

    claim = body.get("claim")

    if not isinstance(claim, dict):
        return response("invalid", "low", [])

    claim_value = claim.get("value")

    if not isinstance(claim_value, str):
        return response("invalid", "low", [])

    as_of = parse_timestamp(body.get("asOf"))

    if as_of is None:
        return response("invalid", "low", [])

    staleness_days = body.get("stalenessDays")

    if not is_valid_number(staleness_days):
        return response("invalid", "low", [])

    sources = body.get("sources")

    if not isinstance(sources, list):
        return response("invalid", "low", [])

    # ---------------------------------------------------------
    # Keep only valid sources.
    #
    # Invalid sources are ignored entirely.
    # ---------------------------------------------------------

    valid_sources: list[dict[str, Any]] = [
        source
        for source in sources
        if is_valid_source(source)
    ]

    # ---------------------------------------------------------
    # Determine freshness.
    #
    # Only fresh sources participate in the decision.
    # ---------------------------------------------------------

    fresh_sources: list[dict[str, Any]] = [
        source
        for source in valid_sources
        if is_fresh(
            source,
            as_of,
            float(staleness_days),
        )
    ]

    # ---------------------------------------------------------
    # RULE 2
    #
    # CONTRADICTED
    #
    # At least one fresh authoritative source has a value
    # different from the claim.
    #
    # Return ALL such source IDs, sorted ascending.
    # ---------------------------------------------------------

    contradicting_sources = [
        source
        for source in fresh_sources
        if source.get("authoritative") is True
        and source["value"] != claim_value
    ]

    if contradicting_sources:
        contradicting_ids = sorted(
            source["id"]
            for source in contradicting_sources
        )

        return response(
            "contradicted",
            "low",
            contradicting_ids,
        )

    # ---------------------------------------------------------
    # RULE 3
    #
    # SUPPORTED
    #
    # Keep:
    #   - fresh
    #   - value == claim.value
    #
    # Then reduce to ONE representative per origin.
    #
    # Representative:
    #   lexicographically smallest id
    # ---------------------------------------------------------

    agreeing_sources = [
        source
        for source in fresh_sources
        if source["value"] == claim_value
    ]

    representatives_by_origin: dict[str, dict[str, Any]] = {}

    for source in agreeing_sources:
        origin = source["origin"]

        current = representatives_by_origin.get(origin)

        if current is None or source["id"] < current["id"]:
            representatives_by_origin[origin] = source

    representatives = list(representatives_by_origin.values())

    if len(representatives) >= 2:
        representative_ids = sorted(
            source["id"]
            for source in representatives
        )

        distinct_types = {
            source["type"]
            for source in representatives
        }

        if len(distinct_types) >= 2:
            confidence = "high"
        else:
            confidence = "medium"

        return response(
            "supported",
            confidence,
            representative_ids,
        )

    # ---------------------------------------------------------
    # RULE 4
    #
    # Everything else is unverified / low / []
    # ---------------------------------------------------------

    return response(
        "unverified",
        "low",
        [],
    )