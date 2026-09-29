"""Tiny JSON state kept in the repo (state/state.json), committed after every run."""
import json

from .config import STATE_FILE

DEFAULT = {
    "telegram_offset": 0,
    "current_week": [],      # post ids of the latest batch, in order (#1..#7)
    "posts": {},             # post id -> post record
    "topics_used": [],       # short topic strings, newest last
    "questions": [],         # follower questions queued for "Ask HyZone"
    "counters": {},          # series name -> issue number
    "last_error": "",
    "token_refreshed_at": "",
}


def load() -> dict:
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    else:
        data = {}
    for k, v in DEFAULT.items():
        data.setdefault(k, json.loads(json.dumps(v)))
    return data


def save(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
