"""Asks Gemini for one post in a given slot and validates it."""
import json
from datetime import date

from .config import BRIEF, CFG
from .formats import spec_for, validate
from .gemini import generate_json


def fill(text: str) -> str:
    b = CFG["brand"]
    return text.replace("[PHONE]", b["phone"]).replace("[HANDLE]", b["instagram_handle"])


def write_post(slot: dict, day: date, avoid: list[str], question: str | None = None,
               previous: dict | None = None, feedback: str | None = None) -> dict:
    parts = [
        BRIEF,
        "---",
        f'Write ONE Instagram poster for the HyZone series "{slot["series"]}", '
        f'going out on {day:%A %d %B %Y} in {CFG["brand"]["city"]}.',
        f"It is {day:%B}: pick a timely topic when it fits the series.",
    ]
    if avoid:
        parts.append("Do NOT repeat these recent topics: " + "; ".join(avoid[-60:]))
    if question:
        parts.append(f'Answer this real follower question: "{question}"')
    elif slot.get("mode") == "ask":
        parts.append("Pick a question homeowners in Hyderabad commonly ask about pest control.")
    parts.append(spec_for(slot))
    if previous:
        clean = {k: v for k, v in previous.items() if k not in ("format",)}
        parts.append("CURRENT VERSION:\n" + json.dumps(clean, ensure_ascii=False))
        parts.append(f"The owner wants this change: {feedback}\n"
                     "Rewrite the post applying the change. Keep what was good unless the change says otherwise.")
    parts.append("Reply with the JSON object only.")
    prompt = "\n\n".join(parts)

    last = None
    for _ in range(3):
        try:
            return validate(slot, generate_json(prompt))
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            last = e
    raise RuntimeError(f"Could not get a valid {slot['series']} post: {last}")


def write_reel_script(slot: dict, day: date, avoid: list[str],
                      previous: dict | None = None, feedback: str | None = None) -> dict:
    style = CFG.get("reels", {}).get("script_style", "a natural Telugu-English mix, written in English letters")
    parts = [
        BRIEF,
        "---",
        f'Write a 30–45 second talking-head Instagram Reel script for the HyZone series "{slot["series"]}", '
        f"going out on {day:%A %d %B %Y}. Dev, the owner, will say it to camera.",
        f"It is {day:%B}: pick a timely topic when it fits the series.",
        f"Write the spoken lines in {style}. Sound like a friendly local expert talking to neighbours, not an ad.",
        "Dev speaks plainly and calmly, like a trusted expert: no acting, no jokes, no reading texts, no characters. "
        "The humour lives ONLY on screen: write 1–3 'smug pest' chat bubbles (see brief) that will pop up next to him "
        "while he says the matching fact. Each bubble reacts to one of his lines.",
    ]
    if avoid:
        parts.append("Do NOT repeat these recent topics: " + "; ".join(avoid[-60:]))
    parts.append("""Return JSON:
{
  "topic": "3-6 word summary",
  "hook": "on-screen title in English, max 40 characters, makes people stop scrolling",
  "lines": ["5 to 7 short spoken lines. Line 1 is a hook question or surprising claim. One fact per line.
             The last line mentions HyZone and says to call or DM."],
  "caption": "Instagram caption (see brief), in English",
  "bubbles": [{"line": 2, "pest": "one of cockroach, termite, swarmer, mosquito, rat, ant, bedbug, fly, spider",
               "text": "the pest's cheeky on-screen text, lowercase, max 45 characters, e.g. lol i was behind the fridge the whole time"}]
}
"line" is the 1-based number of the spoken line the bubble reacts to.""")
    if previous:
        parts.append("CURRENT VERSION:\n" + json.dumps(previous, ensure_ascii=False))
        parts.append(f"The owner wants this change: {feedback}\nRewrite the script applying it.")
    parts.append("Reply with the JSON object only.")
    prompt = "\n\n".join(parts)

    last = None
    for _ in range(3):
        try:
            c = generate_json(prompt)
            lines = [str(x).strip() for x in c.get("lines", []) if str(x).strip()]
            if not (3 <= len(lines) <= 10) or not c.get("hook") or not c.get("caption"):
                raise ValueError("incomplete script")
            from .formats import ICONS
            bubbles = []
            for b in (c.get("bubbles") or [])[:3]:
                if isinstance(b, dict) and str(b.get("text", "")).strip():
                    bubbles.append({"line": int(b.get("line") or 1),
                                    "pest": b.get("pest") if b.get("pest") in ICONS else "cockroach",
                                    "text": str(b["text"]).strip()[:48]})
            return {"format": "reel", "topic": str(c.get("topic", c["hook"]))[:60], "hook": str(c["hook"])[:44],
                    "lines": lines, "caption": str(c["caption"]).strip(), "bubbles": bubbles}
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            last = e
    raise RuntimeError(f"Could not get a valid Reel script: {last}")
