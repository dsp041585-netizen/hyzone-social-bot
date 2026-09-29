"""The five locked poster formats: what the writer must return, and validation."""

ICONS = ["cockroach", "termite", "swarmer", "mosquito", "rat", "ant", "bedbug", "fly", "spider"]

# Pin positions on each room drawing (x, y in the 848x440 illustration)
ROOMS = {
    "kitchen": {"fridge": (160, 300), "dustbin": (292, 300), "sink": (510, 226),
                "drain": (450, 352), "cabinet": (650, 320), "stove": (735, 140)},
    "bathroom": {"toilet": (160, 300), "sink": (430, 232), "mirror_cabinet": (430, 105),
                 "shower": (700, 170), "drain": (690, 352)},
    "bedroom": {"window": (145, 135), "bed": (440, 305), "switchboard": (470, 170),
                "wardrobe": (725, 320)},
}

COMMON = """Return ONE JSON object. Also include:
  "topic": 3-6 word summary of the fact (used to avoid repeats),
  "caption": the Instagram caption (see brief)."""

SPECS = {
    "you_think": """FORMAT "You Think / Actually" (split poster, myth on top, truth below).
{
  "myth": "the common belief, as people say it, max 70 characters, no quote marks",
  "actually": "the correct fact, max 120 characters, one or two short sentences"
}""",
    "big_number": """FORMAT "Big Number" (one giant number + one line).
{
  "number": "the number exactly as shown, max 6 characters, e.g. 30–40, 7, 1/4, 2x",
  "line": "what the number means, max 60 characters, reads naturally after the number",
  "takeaway": "why it matters / what to do, max 100 characters"
}
The number must be a well-established fact. If unsure, choose another fact.""",
    "chat:pest": """FORMAT "The Pest Texts Back" (a funny phone chat between a homeowner and a pest).
{
  "headline": "setup line, max 38 characters, e.g. You say your house is spotless.",
  "headline_accent": "max 30 characters, e.g. The mosquito texts back.",
  "contact_name": "e.g. The Mosquito",
  "contact_status": "online · <where it hides>, max 34 characters",
  "icon": one of ICONS,
  "messages": [ {"from": "me" or "them", "text": "max 55 characters"} ]  5 or 6 messages, starts with "me", ends with "me" reacting,
  "fact_label": "e.g. THE FACT (max 16 chars, caps)",
  "fact_text": "the core fact, max 55 characters",
  "action_label": "e.g. THE FIX (max 16 chars, caps)",
  "action_text": "what to do, max 55 characters"
}
Use the brief's "smug pest" bit exactly: the human states a common belief confidently, the pest deadpans ("haha", "lol",
"cute") and flexes one true fact per message, each worse than the last; the human ends with a short panicked action.""",
    "chat:group": """FORMAT "Pests' Group Chat" (pests gossiping in a group chat about HyZone or about hygiene habits).
{
  "headline": "max 38 characters, e.g. Meanwhile, in the pests'",
  "headline_accent": "max 30 characters, e.g. group chat…",
  "contact_name": "group name, e.g. Pests of Hyderabad",
  "contact_status": "members, e.g. Cockroach, Termite, Rat",
  "icon": "group",
  "messages": [ {"from": "<pest name, e.g. Cockroach>", "text": "max 50 characters"} ]  5 messages,
  "fact_label": "max 16 chars, caps",
  "fact_text": "max 55 characters",
  "action_label": "max 16 chars, caps",
  "action_text": "max 55 characters"
}""",
    "chat:ask": """FORMAT "Ask HyZone" (a follower asks a real question, HyZone answers in a chat).
{
  "headline": "max 38 characters, e.g. Your question this week.",
  "headline_accent": "max 30 characters, e.g. We text back.",
  "contact_name": "HyZone",
  "contact_status": "pest control · Hyderabad",
  "icon": "hyzone",
  "messages": [ {"from": "me" or "them", "text": "max 70 characters"} ]  4 or 5 messages; "me" asks first, "them" (HyZone) answers clearly, "me" ends,
  "fact_label": "e.g. THE ANSWER",
  "fact_text": "the answer in one line, max 55 characters",
  "action_label": "YOUR TURN",
  "action_text": "DM a question. We answer every Sunday"
}
Answers must be general and safe; for safety specifics say the technician will advise.""",
    "hotspots": """FORMAT "Hideout Map" (a room drawing with 3 numbered pins + 3 short lines).
{
  "headline": "max 32 characters, e.g. Where cockroaches hide",
  "headline_accent": "max 20 characters, e.g. in your kitchen",
  "room": one of ["kitchen", "bathroom", "bedroom"],
  "spots": [ {"location": one of that room's LOCATIONS, "title": "max 22 characters, ends with a full stop",
              "detail": "max 34 characters"} ]  exactly 3 spots, different locations
}
LOCATIONS: kitchen = fridge, dustbin, sink, drain, cabinet, stove; bathroom = toilet, sink, mirror_cabinet, shower, drain;
bedroom = window, bed, switchboard, wardrobe.""",
    "profile_card": """FORMAT "Know Your Enemy" (a pest profile card).
{
  "pest_name": "max 24 characters, e.g. The Aedes Mosquito",
  "tagline": "caps, max 22 characters, e.g. SPREADS DENGUE or DAMAGES WOODWORK",
  "icon": one of ICONS,
  "rows": [ {"label": "caps, max 12 characters", "value": "max 34 characters"} ]  exactly 4 rows,
          e.g. BITES / BREEDS IN / LOOKS LIKE / WEAKNESS
}""",
}


def spec_for(slot: dict) -> str:
    key = slot["format"] + (":" + slot["mode"] if slot["format"] == "chat" else "")
    return SPECS[key].replace("one of ICONS", "one of " + str(ICONS)) + "\n" + COMMON


def _s(v, n):
    v = str(v or "").strip()
    return v if len(v) <= n else v[: n - 1].rstrip() + "…"


def validate(slot: dict, c: dict) -> dict:
    """Checks required fields and trims lengths. Raises ValueError if unusable."""
    fmt = slot["format"]
    for k in ("caption", "topic"):
        if not str(c.get(k, "")).strip():
            raise ValueError(f"missing {k}")
    out = {"format": fmt, "caption": str(c["caption"]).strip(), "topic": _s(c["topic"], 60)}
    if fmt == "you_think":
        out.update(myth=_s(c["myth"], 90).strip('"“”'), actually=_s(c["actually"], 150))
    elif fmt == "big_number":
        out.update(number=_s(c["number"], 7), line=_s(c["line"], 75), takeaway=_s(c["takeaway"], 120))
    elif fmt == "chat":
        msgs = [m for m in c.get("messages", []) if str(m.get("text", "")).strip()][:6]
        if len(msgs) < 3:
            raise ValueError("chat needs messages")
        mode = slot["mode"]
        icon = c.get("icon") if mode == "pest" else ("group" if mode == "group" else "hyzone")
        if icon not in ICONS + ["group", "hyzone"]:
            icon = "cockroach"
        out.update(
            mode=mode, headline=_s(c["headline"], 44), headline_accent=_s(c["headline_accent"], 36),
            contact_name=_s(c["contact_name"], 26), contact_status=_s(c["contact_status"], 40), icon=icon,
            messages=[{"from": str(m.get("from", "them")), "text": _s(m["text"], 80)} for m in msgs],
            fact_label=_s(c["fact_label"], 18).upper(), fact_text=_s(c["fact_text"], 64),
            action_label=_s(c["action_label"], 18).upper(), action_text=_s(c["action_text"], 64),
        )
    elif fmt == "hotspots":
        room = c.get("room") if c.get("room") in ROOMS else "kitchen"
        spots, seen = [], set()
        for s in c.get("spots", []):
            loc = s.get("location")
            if loc in ROOMS[room] and loc not in seen:
                seen.add(loc)
                x, y = ROOMS[room][loc]
                spots.append({"title": _s(s["title"], 28), "detail": _s(s["detail"], 42), "x": x, "y": y})
        if len(spots) < 3:
            raise ValueError("hotspots needs 3 valid spots")
        out.update(headline=_s(c["headline"], 38), headline_accent=_s(c["headline_accent"], 26),
                   room=room, spots=spots[:3])
    elif fmt == "profile_card":
        rows = [r for r in c.get("rows", []) if r.get("label") and r.get("value")][:4]
        if len(rows) < 3:
            raise ValueError("profile needs rows")
        icon = c.get("icon") if c.get("icon") in ICONS else "cockroach"
        out.update(pest_name=_s(c["pest_name"], 28), tagline=_s(c["tagline"], 26).upper(), icon=icon,
                   rows=[{"label": _s(r["label"], 14).upper(), "value": _s(r["value"], 40)} for r in rows])
    else:
        raise ValueError(f"unknown format {fmt}")
    return out
