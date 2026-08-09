from app.policy import evaluate_policy


BASE_PAYLOAD = {
    "environment": "prod-ngjwwn",
    "state": {
        "backend": "gcs",
        "locked": True,
    },
    "providerVersion": "~> 6.0",
    "destroyApproved": False,
    "resource": {
        "address": "google_storage_bucket.data",
        "type": "storage_bucket",
        "action": "create",
        "labels": {
            "owner": "student-k5fw7",
            "environment": "production",
            "cost_center": "cc-2jge",
        },
        "secret": None,
        "forceDestroy": False,
    },
}


def payload():
    """
    Return a fresh copy for each test.
    """
    import copy

    return copy.deepcopy(BASE_PAYLOAD)


def test_valid_create():
    assert evaluate_policy(payload()) == {
        "decision": "approve",
        "reason": "APPROVE",
    }


def test_environment_mismatch():
    p = payload()
    p["environment"] = "wrong-workspace"

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "ENVIRONMENT_MISMATCH",
    }


def test_state_backend():
    p = payload()
    p["state"]["backend"] = "local"

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "STATE_UNSAFE",
    }


def test_state_must_be_locked():
    p = payload()
    p["state"]["locked"] = False

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "STATE_UNSAFE",
    }


def test_provider_exact():
    p = payload()
    p["providerVersion"] = "6.2.1"

    assert evaluate_policy(p)["reason"] == "APPROVE"


def test_provider_equal_exact():
    p = payload()
    p["providerVersion"] = "= 6.2.1"

    assert evaluate_policy(p)["reason"] == "APPROVE"


def test_provider_pessimistic_pin():
    p = payload()
    p["providerVersion"] = "~> 6.0"

    assert evaluate_policy(p)["reason"] == "APPROVE"


def test_provider_unpinned_gte():
    p = payload()
    p["providerVersion"] = ">= 6.0"

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "UNPINNED_PROVIDER",
    }


def test_provider_unpinned_latest():
    p = payload()
    p["providerVersion"] = "latest"

    assert evaluate_policy(p)["reason"] == "UNPINNED_PROVIDER"


def test_missing_label():
    p = payload()
    del p["resource"]["labels"]["owner"]

    assert evaluate_policy(p)["reason"] == "MISSING_LABELS"


def test_wrong_label():
    p = payload()
    p["resource"]["labels"]["owner"] = "someone-else"

    assert evaluate_policy(p)["reason"] == "MISSING_LABELS"


def test_valid_secret_reference():
    p = payload()
    p["resource"]["secret"] = "secret://terraform/db-password"

    assert evaluate_policy(p)["reason"] == "APPROVE"


def test_plaintext_secret():
    p = payload()
    p["resource"]["secret"] = "super-secret-password"

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "PLAINTEXT_SECRET",
    }


def test_empty_secret():
    p = payload()
    p["resource"]["secret"] = ""

    assert evaluate_policy(p)["reason"] == "PLAINTEXT_SECRET"


def test_delete_requires_approval():
    p = payload()
    p["resource"]["action"] = "delete"

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "DELETE_NOT_APPROVED",
    }


def test_approved_delete():
    p = payload()
    p["resource"]["action"] = "delete"
    p["destroyApproved"] = True

    assert evaluate_policy(p)["reason"] == "APPROVE"


def test_force_destroy():
    p = payload()
    p["resource"]["forceDestroy"] = True

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "FORCE_DESTROY",
    }


def test_invalid_boolean_type():
    p = payload()
    p["state"]["locked"] = "true"

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "INVALID_PLAN",
    }


def test_invalid_resource_type():
    p = payload()
    p["resource"]["forceDestroy"] = "false"

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "INVALID_PLAN",
    }


def test_invalid_action_type():
    p = payload()
    p["resource"]["action"] = 123

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "INVALID_PLAN",
    }


def test_invalid_secret_type():
    p = payload()
    p["resource"]["secret"] = 123

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "INVALID_PLAN",
    }


def test_first_rule_wins():
    """
    Invalid type + environment mismatch.
    Rule 1 must win.
    """
    p = payload()
    p["environment"] = "wrong"
    p["state"]["locked"] = "yes"

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "INVALID_PLAN",
    }


def test_environment_before_state():
    p = payload()
    p["environment"] = "wrong"
    p["state"]["backend"] = "local"

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "ENVIRONMENT_MISMATCH",
    }


def test_state_before_provider():
    p = payload()
    p["state"]["backend"] = "local"
    p["providerVersion"] = "latest"

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "STATE_UNSAFE",
    }


def test_provider_before_labels():
    p = payload()
    p["providerVersion"] = "latest"
    del p["resource"]["labels"]["owner"]

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "UNPINNED_PROVIDER",
    }


def test_labels_before_secret():
    p = payload()
    del p["resource"]["labels"]["owner"]
    p["resource"]["secret"] = "plaintext"

    assert evaluate_policy(p) == {
        "decision": "reject",
        "reason": "MISSING_LABELS",
    }