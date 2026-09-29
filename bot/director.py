"""The AI director: watches the raw clip and returns an edit plan."""
from pathlib import Path

from .config import CFG
from .formats import ICONS
from .gemini import generate_json

CARD_TYPES = {"stat", "myth", "fact", "pest", "tip", "bubble"}


def _script_rule() -> str:
    if CFG.get("reels", {}).get("caption_script", "roman") == "telugu":
        return "write Telugu words in Telugu script and English words in English letters"
    return ("write Telugu words in English letters (Roman script, the way people type Telugu on WhatsApp) "
            "and English words normally")


def plan_edit(proxy: str, chunks: list[tuple[float, float]], script: dict,
              previous: dict | None = None, feedback: str | None = None) -> dict:
    lang = CFG.get("reels", {}).get("language", "Telugu-English mix")
    chunk_list = "\n".join(f"{i}: {s:.2f}s – {e:.2f}s" for i, (s, e) in enumerate(chunks, 1))
    bubbles = script.get("bubbles") or []
    bubble_list = "\n".join(f'- after line {b["line"]}: {b["pest"]} says "{b["text"]}"' for b in bubbles) or "(none)"
    prompt = f"""You are the video editor and creative director for HyZone, a pest control brand in Hyderabad.
Watch this raw talking-head video. The owner, Dev, speaks to camera in {lang}.
It has been split at pauses into these numbered chunks (times in seconds):
{chunk_list}

The script he was reading from (he may paraphrase):
Title: {script.get('hook', '')}
{chr(10).join(script.get('lines', []))}

Plan the edit. Return JSON:
{{"hook": "...", "chunks": [{{"i": 1, "keep": true, "caption": "...", "emphasis": "...", "zoom": false, "card": null}}]}}
One entry per chunk, same order, all {len(chunks)} chunks.

RULES
- keep: keep only the best, most complete take of each line. Drop false starts, repeated lines (keep the LAST clean one),
  filler, "ok", "one more time", off-script chatter, coughs, silence. Kept chunks must flow as one natural message.
- caption: exactly what is said in that chunk; {_script_rule()}. No emojis. "" for dropped chunks.
- emphasis: the single most important word of the caption (must appear in it exactly), or "".
- zoom: true on about a third of kept chunks, on punchlines and key facts; never on two kept chunks in a row.
- card: a pop-up graphic ONLY where the words say it; 2–4 per Reel, at most one every ~6 seconds; else null.
    {{"type": "stat", "big": "max 6 chars, e.g. 30–40", "small": "max 28 chars"}}  when a number is said
    {{"type": "myth", "text": "max 40 chars"}}  when stating the myth
    {{"type": "fact", "text": "max 48 chars"}}  when stating the truth
    {{"type": "pest", "icon": one of {ICONS}, "label": "max 18 chars"}}  when a pest is first named
    {{"type": "tip", "text": "max 48 chars"}}  when giving an action to take
    {{"type": "bubble", "icon": pest, "text": "..."}}  a cheeky pest chat bubble, the funniest card: place EVERY
      planned bubble below on the kept chunk where Dev says the matching line, using its exact text and pest
  Card text in English, only facts that were actually spoken. Bubbles count toward the card total.

PLANNED PEST BUBBLES (on-screen jokes; Dev never says these):
{bubble_list}
- hook: on-screen title shown for the whole Reel, English, max 40 characters, makes people stop scrolling.
"""
    if previous:
        prompt += f"\nYOUR PREVIOUS PLAN:\n{previous}\n\nThe owner watched it and wants: {feedback}\nRevise the plan accordingly.\n"
    prompt += "\nReply with the JSON only."

    raw = generate_json(prompt, temperature=0.4, media=[("video/mp4", Path(proxy).read_bytes())])
    return validate_plan(raw, chunks, script)


def _cut(v, n):
    v = str(v or "").strip()
    return v if len(v) <= n else v[: n - 1] + "…"


def validate_plan(raw: dict, chunks: list[tuple[float, float]], script: dict) -> dict:
    by_i = {}
    for c in raw.get("chunks", []):
        try:
            by_i[int(c.get("i"))] = c
        except (TypeError, ValueError):
            continue
    out, prev_zoom = [], False
    for i, (s, e) in enumerate(chunks, 1):
        c = by_i.get(i, {"keep": True})
        keep = bool(c.get("keep", True))
        caption = _cut(c.get("caption", ""), 140)
        emphasis = str(c.get("emphasis") or "").strip()
        zoom = bool(c.get("zoom")) and keep and not prev_zoom
        card = c.get("card") if keep else None
        if isinstance(card, dict) and card.get("type") in CARD_TYPES:
            t = card["type"]
            if t == "stat":
                card = {"type": t, "big": _cut(card.get("big"), 7), "small": _cut(card.get("small"), 32)}
            elif t == "pest":
                icon = card.get("icon") if card.get("icon") in ICONS else "cockroach"
                card = {"type": t, "icon": icon, "label": _cut(card.get("label"), 20)}
            elif t == "bubble":
                icon = card.get("icon") if card.get("icon") in ICONS else "cockroach"
                card = {"type": t, "icon": icon, "text": _cut(card.get("text"), 50),
                        "name": "The " + icon.replace("bedbug", "bed bug").replace("swarmer", "termite").title()}
            else:
                card = {"type": t, "text": _cut(card.get("text"), 52)}
        else:
            card = None
        out.append({"i": i, "start": s, "end": e, "keep": keep, "caption": caption,
                    "emphasis": emphasis, "zoom": zoom, "card": card})
        if keep:
            prev_zoom = zoom
    if not any(c["keep"] for c in out):
        for c in out:
            c["keep"] = True
    return {"hook": _cut(raw.get("hook") or script.get("hook", ""), 44), "chunks": out}


def summary(plan: dict) -> str:
    kept = [c for c in plan["chunks"] if c["keep"]]
    dropped = len(plan["chunks"]) - len(kept)
    cards = [c["card"]["type"] for c in kept if c["card"]]
    zooms = sum(c["zoom"] for c in kept)
    return (f"Cut {dropped} bad take(s)/pause(s) · {zooms} punch-in zoom(s) · "
            f"{len(cards)} pop-up card(s){': ' + ', '.join(cards) if cards else ''}")
