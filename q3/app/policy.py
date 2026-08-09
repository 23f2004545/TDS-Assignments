from typing import Any


WORKSPACE = "prod-ngjwwn"

REQUIRED_LABELS = {
    "owner": "student-k5fw7",
    "environment": "production",
    "cost_center": "cc-2jge",
}

ALLOWED_BACKENDS = {"gcs", "s3", "azurerm", "remote"}

ALLOWED_ACTIONS = {"create", "update", "delete"}

DESTRUCTIVE_RESOURCE_TYPES = {
    "storage_bucket",
    "sql_database",
    "persistent_disk",
}

ALLOWED_PROVIDER_VERSIONS = {
    "6.2.1",
    "= 6.2.1",
    "~> 6.0",
}


def reject(reason: str) -> dict[str, str]:
    return {
        "decision": "reject",
        "reason": reason,
    }


def approve() -> dict[str, str]:
    return {
        "decision": "approve",
        "reason": "APPROVE",
    }


def is_bool(value: Any) -> bool:
    """
    bool is a subclass of int in Python, so use this instead of isinstance(x, int)
    when we specifically require a JSON boolean.
    """
    return type(value) is bool


def is_string(value: Any) -> bool:
    return type(value) is str


def validate_types(payload: Any) -> bool:
    """
    Rule 1:
    Validate the normalized request and all required nested fields.
    """

    if not isinstance(payload, dict):
        return False

    # Top-level fields
    if not is_string(payload.get("environment")):
        return False

    if not isinstance(payload.get("state"), dict):
        return False

    if not is_string(payload.get("providerVersion")):
        return False

    if not is_bool(payload.get("destroyApproved")):
        return False

    if not isinstance(payload.get("resource"), dict):
        return False

    # State
    state = payload["state"]

    if not is_string(state.get("backend")):
        return False

    if not is_bool(state.get("locked")):
        return False

    # Resource
    resource = payload["resource"]

    if not is_string(resource.get("address")):
        return False

    if not is_string(resource.get("type")):
        return False

    if not is_string(resource.get("action")):
        return False

    if not isinstance(resource.get("labels"), dict):
        return False

    if "secret" not in resource:
        return False

    secret = resource["secret"]

    if secret is not None and not is_string(secret):
        return False

    if not is_bool(resource.get("forceDestroy")):
        return False

    # Labels must be string values.
    labels = resource["labels"]

    if not all(is_string(k) and is_string(v) for k, v in labels.items()):
        return False

    return True


def evaluate_policy(payload: Any) -> dict[str, str]:
    """
    Evaluate the policy in the exact required order.

    Returns the first applicable rejection reason.
    """

    # ---------------------------------------------------------
    # 1. Type validation
    # ---------------------------------------------------------
    if not validate_types(payload):
        return reject("INVALID_PLAN")

    environment = payload["environment"]
    state = payload["state"]
    provider_version = payload["providerVersion"]
    destroy_approved = payload["destroyApproved"]
    resource = payload["resource"]

    # ---------------------------------------------------------
    # 2. Environment
    # ---------------------------------------------------------
    if environment != WORKSPACE:
        return reject("ENVIRONMENT_MISMATCH")

    # ---------------------------------------------------------
    # 3. Remote state safety
    # ---------------------------------------------------------
    if state["backend"] not in ALLOWED_BACKENDS:
        return reject("STATE_UNSAFE")

    if state["locked"] is not True:
        return reject("STATE_UNSAFE")

    # ---------------------------------------------------------
    # 4. Provider pinning
    # ---------------------------------------------------------
    if provider_version not in ALLOWED_PROVIDER_VERSIONS:
        return reject("UNPINNED_PROVIDER")

    # ---------------------------------------------------------
    # 5. Required labels
    # ---------------------------------------------------------
    labels = resource["labels"]

    for key, expected_value in REQUIRED_LABELS.items():
        if labels.get(key) != expected_value:
            return reject("MISSING_LABELS")

    # ---------------------------------------------------------
    # 6. Secret handling
    # ---------------------------------------------------------
    secret = resource["secret"]

    if secret is not None:
        if secret == "" or not secret.startswith("secret://"):
            return reject("PLAINTEXT_SECRET")

    # ---------------------------------------------------------
    # 7. Destructive operation approval
    # ---------------------------------------------------------
    if (
        resource["action"] == "delete"
        and resource["type"] in DESTRUCTIVE_RESOURCE_TYPES
        and destroy_approved is not True
    ):
        return reject("DELETE_NOT_APPROVED")

    # ---------------------------------------------------------
    # 8. Production storage bucket force destruction
    # ---------------------------------------------------------
    if (
        resource["type"] == "storage_bucket"
        and environment == "prod-ngjwwn"
        and resource["forceDestroy"] is True
    ):
        return reject("FORCE_DESTROY")

    return approve()