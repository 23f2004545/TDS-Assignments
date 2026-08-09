import json
import re
from urllib.parse import unquote, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


app = FastAPI()


ALLOWED_HOSTS = {
    "cdn-w4903wu.example",
    "app-3pn116f.example",
}

CHANNELS = {
    "html",
    "markdown",
    "url",
    "sql",
    "shell",
}


# ---------------------------------------------------------
# Response helper
# ---------------------------------------------------------

def result(reason: str) -> dict:
    return {
        "safe": reason == "SAFE",
        "reason": reason,
    }


# ---------------------------------------------------------
# Step 2: one-pass decoding
#
# percent escapes
#       ↓
# HTML entities
#       ↓
# literal \uXXXX escapes
# ---------------------------------------------------------

NAMED_ENTITIES = {
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
    "&amp;": "&",
}


HTML_ENTITY_RE = re.compile(
    r"&(?:#(?:[0-9]+|[xX][0-9A-Fa-f]+)|lt|gt|quot|apos|amp);"
)


def decode_html_entity(match: re.Match) -> str:
    token = match.group(0)

    # Named entities
    if token in NAMED_ENTITIES:
        return NAMED_ENTITIES[token]

    # Numeric entities
    if token.lower().startswith("&#x"):
        number = int(token[3:-1], 16)
    else:
        number = int(token[2:-1], 10)

    try:
        return chr(number)
    except ValueError:
        # Invalid Unicode code point: leave it unchanged.
        return token


UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def decode_unicode_escape(match: re.Match) -> str:
    return chr(int(match.group(1), 16))


def decode_once(value: str) -> str:
    # 1. Percent escapes
    decoded = unquote(value)

    # 2. HTML entities
    decoded = HTML_ENTITY_RE.sub(decode_html_entity, decoded)

    # 3. Literal \uXXXX escapes
    decoded = UNICODE_ESCAPE_RE.sub(decode_unicode_escape, decoded)

    return decoded


# ---------------------------------------------------------
# URL helpers
# ---------------------------------------------------------

DANGEROUS_SCHEME_RE = re.compile(
    r"(?:javascript|data|vbscript)\s*:",
    re.IGNORECASE,
)


def has_dangerous_scheme_text(text: str) -> bool:
    return bool(DANGEROUS_SCHEME_RE.search(text))


def classify_url(url: str):
    """
    Returns:
        ("DANGEROUS_SCHEME", None)
        ("EXTERNAL_EXFIL", None)
        (None, parsed_url)

    A URL is considered absolute when:
      - it has a scheme, or
      - it is protocol-relative (//host/path)
    """

    value = url.strip()

    if not value:
        return None, None

    # Explicitly dangerous schemes.
    if has_dangerous_scheme_text(value):
        return "DANGEROUS_SCHEME", None

    parsed = urlsplit(value)

    # Any explicit scheme other than HTTP/HTTPS is dangerous.
    if parsed.scheme:
        if parsed.scheme.lower() not in {"http", "https"}:
            return "DANGEROUS_SCHEME", None

        hostname = parsed.hostname

        # HTTP/HTTPS without a hostname is not a valid absolute
        # network URL for our purposes.
        if not hostname:
            return "DANGEROUS_SCHEME", None

        if hostname.lower() not in ALLOWED_HOSTS:
            return "EXTERNAL_EXFIL", None

        return None, parsed

    # Protocol-relative URL: //host/path
    if value.startswith("//"):
        parsed = urlsplit("https:" + value)
        hostname = parsed.hostname

        if not hostname:
            return "DANGEROUS_SCHEME", None

        if hostname.lower() not in ALLOWED_HOSTS:
            return "EXTERNAL_EXFIL", None

        return None, parsed

    # Relative reference.
    return None, parsed


# ---------------------------------------------------------
# URL extraction
# ---------------------------------------------------------

HTML_ATTRIBUTE_RE = re.compile(
    r"""
    \b(?:src|href)
    \s*=\s*
    (?P<quote>["'])
    (?P<value>.*?)
    (?P=quote)
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)


def extract_html_urls(text: str):
    urls = []

    for match in HTML_ATTRIBUTE_RE.finditer(text):
        urls.append(match.group("value"))

    return urls


def extract_markdown_urls(text: str):
    """
    Extract the target inside ](...).

    Supports:
      [text](https://example.com)
      [text](<https://example.com/path with spaces>)

    Also handles nested parentheses reasonably for URLs such as:
      [x](https://host/path(foo))
    """

    urls = []
    marker = re.compile(r"\]\(")

    for match in marker.finditer(text):
        i = match.end()

        # Ignore whitespace immediately after '('.
        while i < len(text) and text[i].isspace():
            i += 1

        if i >= len(text):
            continue

        # Markdown angle-bracket destination.
        if text[i] == "<":
            end = text.find(">", i + 1)

            if end == -1:
                continue

            urls.append(text[i + 1:end])
            continue

        # Normal destination.
        start = i
        depth = 0

        while i < len(text):
            char = text[i]

            # Escaped character.
            if char == "\\" and i + 1 < len(text):
                i += 2
                continue

            if char == "(":
                depth += 1

            elif char == ")":
                if depth == 0:
                    break
                depth -= 1

            elif char.isspace() and depth == 0:
                break

            i += 1

        urls.append(text[start:i])

    return urls


def extracted_urls_for_channel(channel: str, output: str):
    if channel == "html":
        return extract_html_urls(output)

    if channel == "markdown":
        return extract_markdown_urls(output)

    if channel == "url":
        return [output.strip()]

    return []


# ---------------------------------------------------------
# Channel-specific rules
# ---------------------------------------------------------

SCRIPT_TAG_RE = re.compile(
    r"<\s*(?:script|iframe|object|embed)(?=[\s/>])",
    re.IGNORECASE,
)


EVENT_HANDLER_RE = re.compile(
    r"\bon[a-zA-Z][a-zA-Z0-9:_-]*\s*=",
    re.IGNORECASE,
)


SQL_METACHAR_RE = re.compile(
    r"""
    '
    |"
    |;
    |--
    |/\*
    |\bunion\b
    |\bor\s+1\s*=\s*1\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


SHELL_METACHAR_RE = re.compile(
    r"[;&|`<>]|\$\(|\$\{"
)


def check_channel_rules(channel: str, output: str):
    # ---------------------------------------------
    # HTML
    # ---------------------------------------------
    if channel == "html":

        if SCRIPT_TAG_RE.search(output):
            return "SCRIPT_TAG"

        if EVENT_HANDLER_RE.search(output):
            return "EVENT_HANDLER"

        # Dangerous scheme text is checked before URL extraction.
        if has_dangerous_scheme_text(output):
            return "DANGEROUS_SCHEME"

        for url in extract_html_urls(output):
            reason, _ = classify_url(url)

            if reason == "DANGEROUS_SCHEME":
                return "DANGEROUS_SCHEME"

        for url in extract_html_urls(output):
            reason, _ = classify_url(url)

            if reason == "EXTERNAL_EXFIL":
                return "EXTERNAL_EXFIL"

        return "SAFE"

    # ---------------------------------------------
    # Markdown
    # ---------------------------------------------
    if channel == "markdown":

        if has_dangerous_scheme_text(output):
            return "DANGEROUS_SCHEME"

        for url in extract_markdown_urls(output):
            reason, _ = classify_url(url)

            if reason == "DANGEROUS_SCHEME":
                return "DANGEROUS_SCHEME"

        for url in extract_markdown_urls(output):
            reason, _ = classify_url(url)

            if reason == "EXTERNAL_EXFIL":
                return "EXTERNAL_EXFIL"

        return "SAFE"

    # ---------------------------------------------
    # URL
    # ---------------------------------------------
    if channel == "url":

        if has_dangerous_scheme_text(output):
            return "DANGEROUS_SCHEME"

        reason, _ = classify_url(output.strip())

        if reason == "DANGEROUS_SCHEME":
            return "DANGEROUS_SCHEME"

        if reason == "EXTERNAL_EXFIL":
            return "EXTERNAL_EXFIL"

        return "SAFE"

    # ---------------------------------------------
    # SQL
    # ---------------------------------------------
    if channel == "sql":

        if SQL_METACHAR_RE.search(output):
            return "SQL_METACHAR"

        return "SAFE"

    # ---------------------------------------------
    # Shell
    # ---------------------------------------------
    if channel == "shell":

        if SHELL_METACHAR_RE.search(output):
            return "SHELL_METACHAR"

        return "SAFE"

    # Should never happen after schema validation.
    return "INVALID_SCHEMA"


# ---------------------------------------------------------
# Main deterministic gate
# ---------------------------------------------------------

def sanitize(channel: str, output: str):
    """
    Rules are intentionally evaluated in the exact order
    specified by the challenge.
    """

    # Rule 1 is handled before this function.
    #
    # Rule 2:
    # Decode once. If the decoded value differs from the
    # original and the decoded value would trip a channel
    # rule, return ENCODED_PAYLOAD.
    decoded = decode_once(output)

    if decoded != output:
        decoded_reason = check_channel_rules(channel, decoded)

        if decoded_reason != "SAFE":
            return result("ENCODED_PAYLOAD")

    # Rule 3:
    # Evaluate the original output.
    reason = check_channel_rules(channel, output)

    return result(reason)


# ---------------------------------------------------------
# Endpoint
# ---------------------------------------------------------

@app.post("/sanitize-output")
async def sanitize_output(request: Request):

    # Read raw request body so malformed JSON can also be
    # converted into the required INVALID_SCHEMA response.
    try:
        raw_body = await request.body()
        body = json.loads(raw_body)
    except Exception:
        return JSONResponse(
            content=result("INVALID_SCHEMA")
        )

    # Rule 1: body must be an object.
    if not isinstance(body, dict):
        return JSONResponse(
            content=result("INVALID_SCHEMA")
        )

    channel = body.get("channel")
    output = body.get("output")

    # Rule 1: channel must be one of the five values.
    if channel not in CHANNELS:
        return JSONResponse(
            content=result("INVALID_SCHEMA")
        )

    # Rule 1: output must be a string.
    if not isinstance(output, str):
        return JSONResponse(
            content=result("INVALID_SCHEMA")
        )

    # Rule 1: maximum 20,000 characters.
    if len(output) > 20000:
        return JSONResponse(
            content=result("INVALID_SCHEMA")
        )

    # Rules 2 and 3.
    return JSONResponse(
        content=sanitize(channel, output)
    )


# ---------------------------------------------------------
# Render / local entry point
# ---------------------------------------------------------

@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/health")
def health_check():
    return {"status": "ok"}