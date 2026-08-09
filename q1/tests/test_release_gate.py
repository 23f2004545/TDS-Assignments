from copy import deepcopy

from app.policy import evaluate_release_gate


SAFE = {
    "target": "preview",
    "event": "pull_request",
    "ref": "refs/heads/feature/test",
    "workflow": {
        "trigger": "pull_request",
        "permissions": {
            "contents": "read",
            "packages": "write",
            "id-token": "none",
        },
        "testsPassed": True,
        "matrixComplete": True,
        "failFast": False,
        "actions": [
            {
                "owner": "actions",
                "name": "checkout",
                "ref": "v4",
            },
            {
                "owner": "thirdparty",
                "name": "build",
                "ref": "0123456789abcdef0123456789abcdef01234567",
            },
        ],
    },
    "image": {
        "multiStage": True,
        "runsAsRoot": False,
        "secretMode": "none",
        "criticalVulnerabilities": 0,
        "digestPinned": True,
    },
}


def make_payload():
    return deepcopy(SAFE)


def test_safe_preview_promotes():
    result = evaluate_release_gate(make_payload())

    assert result == {
        "decision": "promote",
        "violations": [],
    }


def test_extra_permission():
    payload = make_payload()

    payload["workflow"]["permissions"]["issues"] = "write"

    result = evaluate_release_gate(payload)

    assert result["decision"] == "block"
    assert "EXCESS_PERMISSION" in result["violations"]


def test_wrong_permission_value():
    payload = make_payload()

    payload["workflow"]["permissions"]["contents"] = "write"

    result = evaluate_release_gate(payload)

    assert "EXCESS_PERMISSION" in result["violations"]


def test_pull_request_target_blocked():
    payload = make_payload()

    payload["workflow"]["trigger"] = "pull_request_target"

    result = evaluate_release_gate(payload)

    assert result["decision"] == "block"
    assert "UNSAFE_PR_TRIGGER" in result["violations"]


def test_tests_failed():
    payload = make_payload()

    payload["workflow"]["testsPassed"] = False

    result = evaluate_release_gate(payload)

    assert "TESTS_INCOMPLETE" in result["violations"]


def test_matrix_incomplete():
    payload = make_payload()

    payload["workflow"]["matrixComplete"] = False

    result = evaluate_release_gate(payload)

    assert "TESTS_INCOMPLETE" in result["violations"]


def test_fail_fast_true_blocked():
    payload = make_payload()

    payload["workflow"]["failFast"] = True

    result = evaluate_release_gate(payload)

    assert "TESTS_INCOMPLETE" in result["violations"]


def test_third_party_tag_blocked():
    payload = make_payload()

    payload["workflow"]["actions"][1]["ref"] = "v1"

    result = evaluate_release_gate(payload)

    assert "MUTABLE_ACTION" in result["violations"]


def test_third_party_uppercase_sha_blocked():
    payload = make_payload()

    payload["workflow"]["actions"][1]["ref"] = (
        "0123456789ABCDEF0123456789abcdef01234567"
    )

    result = evaluate_release_gate(payload)

    assert "MUTABLE_ACTION" in result["violations"]


def test_actions_tag_allowed():
    payload = make_payload()

    payload["workflow"]["actions"] = [
        {
            "owner": "actions",
            "name": "checkout",
            "ref": "v4",
        }
    ]

    result = evaluate_release_gate(payload)

    assert result["decision"] == "promote"


def test_short_sha_blocked():
    payload = make_payload()

    payload["workflow"]["actions"][1]["ref"] = (
        "0123456789abcdef"
    )

    result = evaluate_release_gate(payload)

    assert "MUTABLE_ACTION" in result["violations"]


def test_single_stage_image():
    payload = make_payload()

    payload["image"]["multiStage"] = False

    result = evaluate_release_gate(payload)

    assert "SINGLE_STAGE_IMAGE" in result["violations"]


def test_root_runtime():
    payload = make_payload()

    payload["image"]["runsAsRoot"] = True

    result = evaluate_release_gate(payload)

    assert "ROOT_RUNTIME" in result["violations"]


def test_buildkit_secret_allowed():
    payload = make_payload()

    payload["image"]["secretMode"] = "buildkit"

    result = evaluate_release_gate(payload)

    assert result["decision"] == "promote"


def test_arg_secret_blocked():
    payload = make_payload()

    payload["image"]["secretMode"] = "arg"

    result = evaluate_release_gate(payload)

    assert "SECRET_IN_LAYER" in result["violations"]


def test_copy_secret_blocked():
    payload = make_payload()

    payload["image"]["secretMode"] = "copy"

    result = evaluate_release_gate(payload)

    assert "SECRET_IN_LAYER" in result["violations"]


def test_critical_cve():
    payload = make_payload()

    payload["image"]["criticalVulnerabilities"] = 1

    result = evaluate_release_gate(payload)

    assert "CRITICAL_CVE" in result["violations"]


def test_digest_required():
    payload = make_payload()

    payload["image"]["digestPinned"] = False

    result = evaluate_release_gate(payload)

    assert "UNPINNED_IMAGE" in result["violations"]


def test_safe_production():
    payload = make_payload()

    payload["target"] = "production"
    payload["event"] = "push"
    payload["ref"] = "refs/heads/main"

    payload["workflow"]["trigger"] = "push"
    payload["workflow"]["environmentApproval"] = True

    result = evaluate_release_gate(payload)

    assert result == {
        "decision": "promote",
        "violations": [],
    }


def test_production_wrong_ref():
    payload = make_payload()

    payload["target"] = "production"
    payload["event"] = "push"
    payload["ref"] = "refs/heads/develop"
    payload["workflow"]["trigger"] = "push"
    payload["workflow"]["environmentApproval"] = True

    result = evaluate_release_gate(payload)

    assert "INVALID_PRODUCTION_REF" in result["violations"]


def test_production_requires_approval():
    payload = make_payload()

    payload["target"] = "production"
    payload["event"] = "push"
    payload["ref"] = "refs/heads/main"
    payload["workflow"]["trigger"] = "push"
    payload["workflow"]["environmentApproval"] = False

    result = evaluate_release_gate(payload)

    assert "APPROVAL_REQUIRED" in result["violations"]


def test_production_pull_request_is_invalid():
    payload = make_payload()

    payload["target"] = "production"
    payload["event"] = "pull_request"
    payload["ref"] = "refs/heads/feature"
    payload["workflow"]["trigger"] = "pull_request"
    payload["workflow"]["environmentApproval"] = True

    result = evaluate_release_gate(payload)

    assert "INVALID_PRODUCTION_REF" in result["violations"]


def test_multiple_failures_are_accumulated():
    payload = make_payload()

    payload["workflow"]["permissions"]["issues"] = "write"
    payload["workflow"]["trigger"] = "pull_request_target"
    payload["workflow"]["testsPassed"] = False
    payload["workflow"]["actions"][1]["ref"] = "v1"

    payload["image"]["multiStage"] = False
    payload["image"]["runsAsRoot"] = True
    payload["image"]["secretMode"] = "arg"
    payload["image"]["criticalVulnerabilities"] = 2
    payload["image"]["digestPinned"] = False

    result = evaluate_release_gate(payload)

    assert result["decision"] == "block"

    expected = {
        "EXCESS_PERMISSION",
        "UNSAFE_PR_TRIGGER",
        "TESTS_INCOMPLETE",
        "MUTABLE_ACTION",
        "SINGLE_STAGE_IMAGE",
        "ROOT_RUNTIME",
        "SECRET_IN_LAYER",
        "CRITICAL_CVE",
        "UNPINNED_IMAGE",
    }

    assert set(result["violations"]) == expected