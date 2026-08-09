from typing import Any
import re


# ============================================================
# Constants
# ============================================================

EXPECTED_PERMISSIONS = {
    "contents": "read",
    "packages": "write",
    "id-token": "none",
}

REQUIRED_THIRD_PARTY_SHA = re.compile(
    r"^[0-9a-f]{40}$"
)


# ============================================================
# Response helpers
# ============================================================

def promote() -> dict[str, Any]:
    return {
        "decision": "promote",
        "violations": [],
    }


def block(violations: list[str]) -> dict[str, Any]:
    return {
        "decision": "block",
        "violations": violations,
    }


# ============================================================
# Basic type helpers
# ============================================================

def is_bool(value: Any) -> bool:
    return type(value) is bool


def is_string(value: Any) -> bool:
    return type(value) is str


# ============================================================
# Schema validation
# ============================================================

def validate_top_level(payload: Any) -> bool:
    """
    The supplied request has a fixed normalized structure.

    Since the problem does not provide an INVALID_SCHEMA violation
    code, malformed requests are treated conservatively by the
    individual policy checks rather than inventing a new response
    reason.
    """

    if not isinstance(payload, dict):
        return False

    required = {
        "target",
        "event",
        "ref",
        "workflow",
        "image",
    }

    if set(payload.keys()) != required:
        return False

    if not isinstance(payload["target"], str):
        return False

    if not isinstance(payload["event"], str):
        return False

    if not isinstance(payload["ref"], str):
        return False

    if not isinstance(payload["workflow"], dict):
        return False

    if not isinstance(payload["image"], dict):
        return False

    return True


# ============================================================
# Workflow validation
# ============================================================

def permissions_are_least_privilege(
    permissions: Any,
) -> bool:
    """
    Permissions must be EXACTLY:

        contents: read
        packages: write
        id-token: none

    No extra permissions are allowed.
    """

    if not isinstance(permissions, dict):
        return False

    if set(permissions.keys()) != set(
        EXPECTED_PERMISSIONS.keys()
    ):
        return False

    for key, expected_value in EXPECTED_PERMISSIONS.items():
        if permissions.get(key) != expected_value:
            return False

    return True


def workflow_tests_are_complete(
    workflow: dict[str, Any],
) -> bool:
    """
    A release requires:

      testsPassed == true
      matrixComplete == true
      failFast == false
    """

    if not is_bool(workflow.get("testsPassed")):
        return False

    if not is_bool(workflow.get("matrixComplete")):
        return False

    if not is_bool(workflow.get("failFast")):
        return False

    return (
        workflow["testsPassed"] is True
        and workflow["matrixComplete"] is True
        and workflow["failFast"] is False
    )


def pull_request_trigger_is_safe(
    payload: dict[str, Any],
) -> bool:
    """
    If the event is pull_request, the workflow must use
    pull_request rather than pull_request_target.
    """

    if payload["event"] != "pull_request":
        return True

    workflow = payload["workflow"]

    return workflow.get("trigger") == "pull_request"


def actions_are_pinned(
    actions: Any,
) -> bool:
    """
    actions/* may use version tags.

    Every third-party action must use a full 40-character
    lowercase hexadecimal commit SHA.
    """

    if not isinstance(actions, list):
        return False

    for action in actions:
        if not isinstance(action, dict):
            return False

        if set(action.keys()) != {
            "owner",
            "name",
            "ref",
        }:
            return False

        owner = action["owner"]
        name = action["name"]
        ref = action["ref"]

        if not isinstance(owner, str):
            return False

        if not isinstance(name, str):
            return False

        if not isinstance(ref, str):
            return False

        # Official actions are allowed to use tags.
        if owner == "actions":
            continue

        # Third-party actions must use a complete lowercase SHA.
        if not REQUIRED_THIRD_PARTY_SHA.fullmatch(ref):
            return False

    return True


# ============================================================
# Image validation
# ============================================================

def image_is_hardened(
    image: Any,
) -> bool:
    """
    Base image requirements:

      multiStage == true
      runsAsRoot == false
      secretMode in {none, buildkit}
      criticalVulnerabilities == 0
      digestPinned == true
    """

    if not isinstance(image, dict):
        return False

    if not is_bool(image.get("multiStage")):
        return False

    if not is_bool(image.get("runsAsRoot")):
        return False

    if not isinstance(
        image.get("secretMode"),
        str,
    ):
        return False

    if not isinstance(
        image.get("criticalVulnerabilities"),
        int,
    ) or isinstance(
        image.get("criticalVulnerabilities"),
        bool,
    ):
        return False

    if not is_bool(image.get("digestPinned")):
        return False

    return True


# ============================================================
# Main policy
# ============================================================

def evaluate_release_gate(
    payload: Any,
) -> dict[str, Any]:
    """
    Evaluate every release-gate rule.

    IMPORTANT:
    Unlike the Terraform policy, this policy does NOT stop at the
    first violation. The specification explicitly requires all
    applicable violation codes.
    """

    violations: list[str] = []

    # ---------------------------------------------------------
    # Defensive access
    # ---------------------------------------------------------

    if not isinstance(payload, dict):
        return block([
            "EXCESS_PERMISSION",
            "UNSAFE_PR_TRIGGER",
            "TESTS_INCOMPLETE",
            "MUTABLE_ACTION",
            "SINGLE_STAGE_IMAGE",
            "ROOT_RUNTIME",
            "SECRET_IN_LAYER",
            "CRITICAL_CVE",
            "UNPINNED_IMAGE",
        ])

    workflow = payload.get("workflow")
    image = payload.get("image")

    if not isinstance(workflow, dict):
        workflow = {}

    if not isinstance(image, dict):
        image = {}

    target = payload.get("target")
    event = payload.get("event")
    ref = payload.get("ref")

    # =========================================================
    # 1. LEAST-PRIVILEGE PERMISSIONS
    # =========================================================

    if not permissions_are_least_privilege(
        workflow.get("permissions")
    ):
        violations.append("EXCESS_PERMISSION")

    # =========================================================
    # 2. PULL REQUEST SAFETY
    # =========================================================

    if event == "pull_request":
        if workflow.get("trigger") != "pull_request":
            violations.append("UNSAFE_PR_TRIGGER")

    # =========================================================
    # 3. COMPLETE TEST MATRIX
    # =========================================================

    if not workflow_tests_are_complete(workflow):
        violations.append("TESTS_INCOMPLETE")

    # =========================================================
    # 4. ACTION PINNING
    # =========================================================

    if not actions_are_pinned(
        workflow.get("actions")
    ):
        violations.append("MUTABLE_ACTION")

    # =========================================================
    # 5. MULTI-STAGE IMAGE
    # =========================================================

    if image.get("multiStage") is not True:
        violations.append("SINGLE_STAGE_IMAGE")

    # =========================================================
    # 6. NON-ROOT RUNTIME
    # =========================================================

    if image.get("runsAsRoot") is not False:
        violations.append("ROOT_RUNTIME")

    # =========================================================
    # 7. SECRET HANDLING
    # =========================================================

    if image.get("secretMode") not in {
        "none",
        "buildkit",
    }:
        violations.append("SECRET_IN_LAYER")

    # =========================================================
    # 8. CRITICAL VULNERABILITIES
    # =========================================================

    critical = image.get(
        "criticalVulnerabilities"
    )

    if (
        not isinstance(critical, int)
        or isinstance(critical, bool)
        or critical != 0
    ):
        violations.append("CRITICAL_CVE")

    # =========================================================
    # 9. IMAGE DIGEST
    # =========================================================

    if image.get("digestPinned") is not True:
        violations.append("UNPINNED_IMAGE")

    # =========================================================
    # 10. PRODUCTION REF
    # =========================================================

    if target == "production":
        if (
            event != "push"
            or ref != "refs/heads/main"
            or workflow.get("trigger") != "push"
        ):
            violations.append(
                "INVALID_PRODUCTION_REF"
            )

    # =========================================================
    # 11. PRODUCTION ENVIRONMENT APPROVAL
    # =========================================================

    if target == "production":
        if workflow.get("environmentApproval") is not True:
            violations.append(
                "APPROVAL_REQUIRED"
            )

    # =========================================================
    # FINAL DECISION
    # =========================================================

    if violations:
        return block(violations)

    return promote()