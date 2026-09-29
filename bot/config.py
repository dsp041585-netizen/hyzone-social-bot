"""Loads config.yaml and secrets from environment variables."""
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
BRIEF = (ROOT / "brief.md").read_text(encoding="utf-8")
TZ = ZoneInfo(CFG.get("timezone", "Asia/Kolkata"))
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

STATE_FILE = ROOT / "state" / "state.json"
POSTS_DIR = ROOT / "posts"
TEMPLATES_DIR = ROOT / "templates"


def env(name: str, required: bool = True) -> str:
    val = os.environ.get(name, "").strip()
    if required and not val:
        raise RuntimeError(f"Missing secret/environment variable: {name}")
    return val


def now() -> datetime:
    return datetime.now(TZ)
