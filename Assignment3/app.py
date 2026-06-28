from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import yaml
import os

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000"
}

CONFIG = DEFAULTS.copy()

# YAML
with open("config.development.yaml") as f:
    CONFIG.update(yaml.safe_load(f) or {})

# .env
if os.getenv("NUM_WORKERS"):
    CONFIG["workers"] = int(os.getenv("NUM_WORKERS"))

if os.getenv("APP_LOG_LEVEL"):
    CONFIG["log_level"] = os.getenv("APP_LOG_LEVEL")

if os.getenv("APP_API_KEY"):
    CONFIG["api_key"] = os.getenv("APP_API_KEY")

# OS Environment
for k, v in os.environ.items():
    if k.startswith("APP_"):
        key = k[4:].lower()

        if key == "debug":
            CONFIG["debug"] = str(v).lower() in (
                "true",
                "1",
                "yes",
                "on",
            )


def cast(key, value):
    if key in ("port", "workers"):
        return int(value)

    if key == "debug":
        return str(value).lower() in (
            "true",
            "1",
            "yes",
            "on",
        )

    return str(value)


@app.get("/effective-config")
def effective_config(set: list[str] = Query(default=[])):
    cfg = CONFIG.copy()

    for item in set:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        cfg[k] = cast(k, v)

    cfg["port"] = cast("port", cfg["port"])
    cfg["workers"] = cast("workers", cfg["workers"])
    cfg["debug"] = cast("debug", cfg["debug"])
    cfg["log_level"] = str(cfg["log_level"])
    cfg["api_key"] = "****"

    return cfg