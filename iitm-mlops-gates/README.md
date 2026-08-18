# IITM MLOps Deterministic Gate Service

A single FastAPI deployment implementing the seven assignment services as independent HTTP endpoints. The implementation is intentionally deterministic: UTF-8 byte ordering, compact JSON, explicit timestamp normalization, SHA-256/CRC32C verification, exact response shapes, and persistent state for the stateful workflows are handled centrally.

## Endpoints

| Assignment | Method | Path | State |
|---|---|---|---|
| Q1 corpus | POST | `/build-corpus` | stateless |
| Q2 experiment gate | POST | `/bqml` | stateful by `runId` |
| Q3 promotion gate | POST | `/promote` | deterministic promotion decision |
| Q4 intervention/PEFT audit | POST | `/adapt` | stateless |
| Q5 quantization gate | POST | `/quantize` | stateful by `freezeId` |
| Q6 pipeline controller | POST | `/pipeline` | stateful by `session` |
| Q7 bundle verifier | POST | `/verify-bundle` | stateless |

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Swagger UI is available at `/docs`.

## Render

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
uvicorn app:app --host 0.0.0.0 --port $PORT
```

The included `render.yaml` can also be used as the Render Blueprint configuration.

## State

Q2, Q5 and Q6 persist state in `state.sqlite3`. The database is intentionally excluded from Git. Render's free filesystem is ephemeral; the service is designed for grader requests that remain on the same live instance. For durable production persistence, replace `StateDB` with a managed database without changing endpoint contracts.

## Determinism utilities

`shared/common.py` provides:

- compact UTF-8 JSON serialization with `ensure_ascii=False`;
- UTF-8 byte sorting and deterministic reason-code ordering;
- safe-integer and finite-number checks;
- strict timestamp parsing and UTC normalization;
- Unicode NFKC/lower/trim/whitespace normalization;
- Unicode letter/number word sets;
- pure-Python CRC32C (Castagnoli);
- SHA-256 helpers;
- SQLite-backed state storage.

## Deployment layout

```text
app.py
services/
  corpus.py
  bqml.py
  promote.py
  adapt.py
  quantize.py
  pipeline.py
  verify_bundle.py
shared/
  common.py
```

Do not commit `state.sqlite3`, `__pycache__`, virtual environments, or secrets.
