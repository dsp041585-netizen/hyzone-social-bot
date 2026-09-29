"""Gemini API (free tier) — returns parsed JSON. Can also watch audio/video."""
import base64
import json
import re
import time

import requests

from .config import CFG, env

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def generate_json(prompt: str, temperature: float = 0.9, media: list[tuple[str, bytes]] | None = None) -> dict:
    """media: optional list of (mime_type, bytes), e.g. ("video/mp4", data). Keep total under ~15 MB."""
    model = CFG["gemini"]["model"]
    parts = [{"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}
             for mime, data in (media or [])]
    parts.append({"text": prompt})
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    last = None
    for attempt in range(4):
        try:
            # Header auth works for both key formats (older "AIza…" and newer "AQ.…").
            r = requests.post(URL.format(model=model), headers={"x-goog-api-key": env("GEMINI_API_KEY")},
                              json=body, timeout=240)
            if r.status_code in (429, 500, 503):
                raise RuntimeError(f"Gemini busy ({r.status_code})")
            if r.status_code != 200:
                raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:300]}")
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
            return json.loads(text)
        except (RuntimeError, KeyError, ValueError, requests.RequestException) as e:
            last = e
            time.sleep(8 * (attempt + 1))
    raise RuntimeError(f"Gemini failed after retries: {last}")
