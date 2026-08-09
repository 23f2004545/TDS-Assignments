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


# ============================================================
# Action firewall
# ============================================================

FIREWALL_TENANT = "tenant-0uy7uzi"
ALLOWED_EMAIL_DOMAIN = "notify-w15mpvm.example"

ALLOWED_TOOLS = {
    "search",
    "lookup_record",
    "send_email",
    "render_html",
}


def firewall_result(decision: str, reason: str) -> dict[str, str]:
    return {
        "decision": decision,
        "reason": reason,
    }


def firewall_allow() -> dict[str, str]:
    return firewall_result("allow", "ALLOW")


def firewall_block(reason: str) -> dict[str, str]:
    return firewall_result("block", reason)


def validate_firewall_top_level(payload: Any) -> bool:
    """
    Rule 1: validate the top-level normalized action request.

    Expected:
    {
        "provenance": "trusted | untrusted",
        "humanApproved": false,
        "untrustedContent": "optional text",
        "action": {
            "tool": "...",
            "args": {...}
        }
    }

    untrustedContent is optional.
    """

    if not isinstance(payload, dict):
        return False

    required_keys = {
        "provenance",
        "humanApproved",
        "action",
    }

    # Top-level fields are intentionally strict.
    if set(payload.keys()) - required_keys - {"untrustedContent"}:
        return False

    if set(payload.keys()) != required_keys:
        return False

    if payload["provenance"] not in {"trusted", "untrusted"}:
        return False

    if type(payload["humanApproved"]) is not bool:
        return False

    if not isinstance(payload["action"], dict):
        return False

    action = payload["action"]

    # action itself must have exactly tool + args.
    if set(action.keys()) != {"tool", "args"}:
        return False

    if not isinstance(action["tool"], str):
        return False

    if not isinstance(action["args"], dict):
        return False

    return True


def normalize_url_for_safety(value: str) -> str:
    """
    Normalize enough to detect javascript: schemes despite casing,
    surrounding whitespace, or ASCII control characters.
    """
    value = value.strip()

    # Remove ASCII whitespace/control characters that can be used to
    # disguise a javascript scheme.
    value = "".join(
        char for char in value
        if ord(char) > 0x20
    )

    return value.casefold()


def html_is_safe(html: str) -> bool:
    """
    Deterministic HTML safety check.

    Blocks:
      - <script>
      - <iframe>
      - inline event handlers such as onclick/onload
      - javascript: URLs

    Does not inspect natural-language content for "suspicious phrases".
    """

    class SafetyParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.unsafe = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            tag_lower = tag.casefold()

            if tag_lower in {"script", "iframe"}:
                self.unsafe = True
                return

            for name, value in attrs:
                name_lower = name.casefold()

                # Inline event handler: onclick, onload, onerror, etc.
                if name_lower.startswith("on"):
                    self.unsafe = True
                    return

                if value is not None:
                    normalized = normalize_url_for_safety(value)

                    if normalized.startswith("javascript:"):
                        self.unsafe = True
                        return

        def handle_startendtag(
            self,
            tag: str,
            attrs: list[tuple[str, str | None]],
        ) -> None:
            self.handle_starttag(tag, attrs)

        def handle_comment(self, data: str) -> None:
            # Comments themselves are not executable.
            pass

    parser = SafetyParser()

    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return False

    return not parser.unsafe


def validate_search_args(args: dict[str, Any]) -> bool:
    """
    search:
      exactly {"query": "1–200 characters"}
    """

    if set(args.keys()) != {"query"}:
        return False

    query = args["query"]

    if not isinstance(query, str):
        return False

    if not 1 <= len(query) <= 200:
        return False

    return True


def validate_lookup_args(args: dict[str, Any]) -> bool:
    """
    lookup_record:
      exactly {"tenantId": "...", "recordId": "non-empty"}
    """

    if set(args.keys()) != {"tenantId", "recordId"}:
        return False

    tenant_id = args["tenantId"]
    record_id = args["recordId"]

    if not isinstance(tenant_id, str):
        return False

    if not isinstance(record_id, str):
        return False

    if record_id == "":
        return False

    return True


def validate_email_args(args: dict[str, Any]) -> bool:
    """
    send_email:
      exactly {"to": "...", "subject": "...", "body": "..."}
    """

    if set(args.keys()) != {"to", "subject", "body"}:
        return False

    if not isinstance(args["to"], str):
        return False

    if not isinstance(args["subject"], str):
        return False

    if not isinstance(args["body"], str):
        return False

    return True


def email_domain_is_allowed(recipient: str) -> bool:
    """
    Require an email-like address whose domain is exactly the assigned
    domain.

    Examples:
      user@notify-w15mpvm.example       -> True
      user@NOTIFY-W15MPVM.EXAMPLE       -> True
      user@evil.example                 -> False
      user@notify-w15mpvm.example.evil  -> False
    """

    recipient = recipient.strip()

    if recipient.count("@") != 1:
        return False

    local_part, domain = recipient.rsplit("@", 1)

    if not local_part or not domain:
        return False

    return domain.casefold() == ALLOWED_EMAIL_DOMAIN.casefold()


def validate_render_html_args(args: dict[str, Any]) -> bool:
    """
    render_html:
      exactly {"html": "..."}
    """

    if set(args.keys()) != {"html"}:
        return False

    if not isinstance(args["html"], str):
        return False

    return True


def evaluate_action_firewall(payload: Any) -> dict[str, str]:
    """
    Evaluate the firewall rules in the exact required order:

    1. Top-level schema
    2. Tool allowlist
    3. Selected tool argument schema
    4. Tenant scope
    5. Exact email domain
    6. Human approval
    7. HTML safety
    """

    # ---------------------------------------------------------
    # 1. Top-level schema
    # ---------------------------------------------------------
    if not validate_firewall_top_level(payload):
        return firewall_block("INVALID_SCHEMA")

    action = payload["action"]
    tool = action["tool"]
    args = action["args"]

    # ---------------------------------------------------------
    # 2. Tool allowlist
    # ---------------------------------------------------------
    if tool not in ALLOWED_TOOLS:
        return firewall_block("TOOL_NOT_ALLOWED")

    # ---------------------------------------------------------
    # 3. Selected tool argument schema
    # ---------------------------------------------------------
    if tool == "search":
        if not validate_search_args(args):
            return firewall_block("INVALID_SCHEMA")

    elif tool == "lookup_record":
        if not validate_lookup_args(args):
            return firewall_block("INVALID_SCHEMA")

    elif tool == "send_email":
        if not validate_email_args(args):
            return firewall_block("INVALID_SCHEMA")

    elif tool == "render_html":
        if not validate_render_html_args(args):
            return firewall_block("INVALID_SCHEMA")

    # ---------------------------------------------------------
    # 4. Tenant scope
    # ---------------------------------------------------------
    if tool == "lookup_record":
        if args["tenantId"] != FIREWALL_TENANT:
            return firewall_block("TENANT_SCOPE")

    # ---------------------------------------------------------
    # 5. Exact email domain
    # ---------------------------------------------------------
    if tool == "send_email":
        if not email_domain_is_allowed(args["to"]):
            return firewall_block("EGRESS_DENIED")

    # ---------------------------------------------------------
    # 6. Human approval
    # ---------------------------------------------------------
    if tool == "send_email":
        if payload["humanApproved"] is not True:
            return firewall_block("APPROVAL_REQUIRED")

    # ---------------------------------------------------------
    # 7. HTML safety
    # ---------------------------------------------------------
    if tool == "render_html":
        if not html_is_safe(args["html"]):
            return firewall_block("UNSAFE_OUTPUT")

    # ---------------------------------------------------------
    # All rules passed.
    # ---------------------------------------------------------
    return firewall_allow()