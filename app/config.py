from __future__ import annotations

import json
from pathlib import Path
import sys


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
QR_DIR = DATA_DIR / "qrcodes"
SQLITE_DB_PATH = DATA_DIR / "gym_system.db"
DB_CONFIG_PATH = BASE_DIR / "db_config.json"


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QR_DIR.mkdir(parents=True, exist_ok=True)


def load_db_config() -> dict:
    ensure_directories()

    default_config = {
        "engine": "sqlite",
        "sqlite_path": str(SQLITE_DB_PATH),
    }

    if not DB_CONFIG_PATH.exists():
        return default_config

    with DB_CONFIG_PATH.open("r", encoding="utf-8") as file:
        user_config = json.load(file)

    config = default_config.copy()
    config.update(user_config)
    return config
