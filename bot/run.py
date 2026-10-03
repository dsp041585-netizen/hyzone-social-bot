"""Main loop, run every 15 minutes by GitHub Actions.

1. Sunday night: draft next week — posters for poster days, scripts for Reel days — and send to Telegram.
2. Read your Telegram replies: approve / change / skip / videos / questions.
3. Publish approved posts and Reels whose time has come.
4. Keep the Instagram token fresh.
"""
import base64
import json
import os
import re
import shutil
import tempfile
import traceback
from datetime import date, datetime, timedelta

import requests

from . import instagram, media, state as st, telegram as tg
from .config import CFG, DAYS, POSTS_DIR, ROOT, TZ, env, now
from .content import fill, write_post, write_reel_script
from .render import render

HELP = """How to reply:
• Posters: reply "approved", or what to change ("make it about bed bugs").
• Reels: reply to the script with your video. Reply to the edited preview with "approved" or what to fix
  ("cut the first line", "bigger zoom on the egg part", "caption says kemikal, should be chemical").
  Reply "poster" to a Reel script to post a designed poster that day instead.
• Or type: approve all · approve 1 3 · change 4: shorter headline · skip 6 · poster 1 · retry 2
• Queue a follower question for Sunday: q: Is pest control safe with pets?
• status: what's approved and when it goes live."""

APPROVE = {"approve", "approved", "ok", "okay", "yes", "done", "👍", "✅", "approve all", "all approved",
           "approved all", "looks good", "lgtm", "go ahead", "post it", "perfect"}
SKIP = {"skip", "reject", "rejected", "no", "drop", "cancel", "❌"}


# ───────────────────────── helpers ─────────────────────────

def slots(monday: date | None = None) -> list[dict]:
    """The lineup for the week starting `monday`: weeks take turns through config 'rotation'."""
    weeks = CFG["rotation"]
    monday = monday or next_monday(now().date())
    week = weeks[(monday.toordinal() // 7) % len(weeks)]
    order = {d: i for i, d in enumerate(DAYS)}
    return sorted(week, key=lambda s: order[s["day"]])


def next_monday(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) or 7)


def when(p: dict) -> str:
    t = datetime.fromisoformat(p["scheduled_at"])
    return f"{t:%a %d %b, %I:%M %p}".replace(" 0", " ")


def label(state: dict, pid: str) -> str:
    try:
        return f"#{state['current_week'].index(pid) + 1}"
    except ValueError:
        return pid


def notify_error(state: dict, where: str, e: Exception) -> None:
    traceback.print_exc()
    msg = f"⚠️ {where}: {e}"[:600]
    errs = state.setdefault("errors", {})
    if errs.get(where) != msg:
        errs[where] = msg
        try:
            tg.send_message(msg)
        except Exception:
            pass


def clear_error(state: dict, where: str) -> None:
    state.setdefault("errors", {}).pop(where, None)


def next_number(state: dict, series: str) -> int:
    state["counters"][series] = state["counters"].get(series, 0) + 1
    return state["counters"][series]


def poster_slot(slot: dict) -> dict:
    return {k: v for k, v in slot.items() if k != "reel"}


def send_post(state: dict, pid: str, heading: str) -> None:
    p = state["posts"][pid]
    ids = tg.send_photo(str(ROOT / p["image"]), f"{heading}\n\n{fill(p['content']['caption'])}")
    p.setdefault("tg_ids", []).extend(ids)


def send_script(state: dict, pid: str, heading: str) -> None:
    p = state["posts"][pid]
    c = p["content"]
    lines = "\n".join(f"{i}. {line}" for i, line in enumerate(c["lines"], 1))
    bubbles = "\n".join(f"after line {b['line']}: “{b['text']}”" for b in c.get("bubbles", []))
    extra = f"\n\nPest bubbles that will pop up on screen (you don't say these):\n{bubbles}" if bubbles else ""
    text = (f"🎬 {heading}\nOn-screen title: {c['hook']}\n\nSay this calmly, straight to camera "
            f"(30–45 sec, your own words are fine):\n{lines}{extra}\n\n"
            "Record vertical, then REPLY TO THIS MESSAGE with the video (send it as a normal video, not a file).\n"
            "Can't record? Reply \"poster\" to use a designed poster instead.")
    p.setdefault("tg_ids", []).append(tg.send_message(text))


def ordinary_post(slot, day, pid, content, meta, img) -> dict:
    hh, mm = map(int, slot["time"].split(":"))
    return {"id": pid, "day": slot["day"], "date": day.isoformat(), "slot": slot, "meta": meta,
            "scheduled_at": datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ).isoformat(),
            "content": content, "image": str(img.relative_to(ROOT)) if img else None, "image_pushed": False,
            "rev": 1, "status": "pending", "tg_ids": [], "reminded": False, "failures": 0}


# ───────────────────────── 1. weekly drafting ─────────────────────────

def generate_week(state: dict, monday: date, force: bool = False, rest_only: bool = False) -> None:
    """rest_only: fill only the days still ahead (at least 1 hour before their posting time)."""
    plan, cutoff = [], now() + timedelta(hours=1)
    for s in slots(monday):
        day = monday + timedelta(days=DAYS.index(s["day"]))
        hh, mm = map(int, s["time"].split(":"))
        if rest_only and datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ) < cutoff:
            continue
        plan.append((s, day, f"{monday:%Y-%m-%d}-{s['day'].lower()}"))
    if not plan:
        tg.send_message("Nothing left to post this week. Next week's batch comes on Sunday night.")
        return
    if not force and all(pid in state["posts"] for _, _, pid in plan):
        return

    which = "the rest of this week" if rest_only else f"next week (week of {monday:%d %b})"
    tg.send_message(f"✍️ Drafting {which}… give me a few minutes.")
    drafts, avoid = [], list(state["topics_used"])
    for s, day, pid in plan:
        if s.get("reel"):
            content, question = write_reel_script(s, day, avoid), None
        else:
            question = state["questions"][0] if s.get("mode") == "ask" and state["questions"] else None
            content = write_post(s, day, avoid, question=question)
        avoid.append(content["topic"])
        drafts.append((s, day, pid, content, question))

    folder = POSTS_DIR / f"{monday:%Y-%m-%d}"
    folder.mkdir(parents=True, exist_ok=True)
    jobs, records = [], []
    for s, day, pid, content, question in drafts:
        meta = {"series": s["series"], "number": next_number(state, s["series"])}
        if s.get("reel"):
            rec = ordinary_post(s, day, pid, content, meta, None)
            rec.update(kind="reel", status="awaiting_video", video=None, original=None, plan=None,
                       rev=0, early_reminded=False)
        else:
            img = folder / f"{pid}-v1.jpg"
            rec = ordinary_post(s, day, pid, content, meta, img)
            rec["kind"] = "poster"
            jobs.append((content, meta, str(img)))
        records.append((pid, rec, question))
    if jobs:
        render(jobs)

    for pid, rec, question in records:
        state["posts"][pid] = rec
        state["topics_used"].append(rec["content"]["topic"])
        if question and question in state["questions"]:
            state["questions"].remove(question)
    state["topics_used"] = state["topics_used"][-150:]
    state["current_week"] = [pid for pid, _, _ in records]

    reels = sum(1 for _, r, _ in records if r["kind"] == "reel")
    title = "Rest of this week" if rest_only else f"Week of {monday:%d %b}"
    tg.send_message(f"🗓 {title}: {len(records) - reels} posters + {reels} Reel scripts below.\n\n{HELP}")
    for i, (pid, rec, _) in enumerate(records, 1):
        heading = f"#{i} · {rec['slot']['series']}{' REEL' if rec['kind'] == 'reel' else ''} · {when(rec)}"
        (send_script if rec["kind"] == "reel" else send_post)(state, pid, heading)


def maybe_generate(state: dict, action: str, force: bool) -> None:
    n = now()
    monday = next_monday(n.date())
    due = n.strftime("%a") == CFG["generate"]["day"] and n.hour >= int(CFG["generate"]["hour"])
    first = f"{monday:%Y-%m-%d}-{slots(monday)[0]['day'].lower()}"
    if action == "this_week":
        generate_week(state, monday - timedelta(days=7), force=True, rest_only=True)
    elif action == "generate" or (due and first not in state["posts"]):
        generate_week(state, monday, force=force or action == "generate")


def send_test(state: dict) -> None:
    """Renders samples/sample_week.json and sends it to Telegram. Never posts to Instagram."""
    from .formats import validate
    samples = json.loads((ROOT / "samples" / "sample_week.json").read_text(encoding="utf-8"))
    folder = POSTS_DIR / "test"
    folder.mkdir(parents=True, exist_ok=True)
    jobs = []
    for s, raw in zip(CFG["rotation"][0], samples):
        content = validate(poster_slot(s), raw)
        jobs.append((content, {"series": s["series"], "number": 1}, str(folder / f"test-{s['day'].lower()}.jpg")))
    render(jobs)
    tg.send_message("🧪 Test run: sample posters from the templates. They will NOT be posted.\n"
                    "To test the Reel editor, run 'generate', then reply to a Reel script with any short video.")
    for content, meta, path in jobs:
        tg.send_photo(path, f"TEST · {meta['series']}\n\n{fill(content['caption'])}")


# ───────────────────────── Reels ─────────────────────────

def media_keep(state: dict) -> set[str]:
    keep, cutoff = set(), now() - timedelta(days=3)
    for p in state["posts"].values():
        if p.get("kind") != "reel":
            continue
        if p["status"] != "posted" or datetime.fromisoformat(p["scheduled_at"]) > cutoff:
            keep |= {x for x in (p.get("original"), p.get("video")) if x}
    return keep


def edit_and_preview(state: dict, pid: str, feedback: str | None = None) -> None:
    from .studio import make_reel
    from .director import summary
    p = state["posts"][pid]
    media.pull()
    p["rev"] = p.get("rev", 0) + 1
    out_rel = f"reels/{pid}-v{p['rev']}.mp4"
    work = tempfile.mkdtemp()
    try:
        plan = make_reel(str(media.MEDIA / p["original"]), p["content"], p["slot"]["series"], work,
                         str(media.MEDIA / out_rel), previous=p.get("plan") if feedback else None, feedback=feedback)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    p.update(plan=plan, video=out_rel, status="pending", reminded=False, failures=0)
    media.push(media_keep(state))
    head = f"{label(state, pid)} REEL {'(revised) ' if feedback else ''}· {p['slot']['series']} · {when(p)}"
    ids = tg.send_video(str(media.MEDIA / out_rel),
                        f"{head}\n✂️ {summary(plan)}\n\nReply \"approved\" or tell me what to fix.\n\n{fill(p['content']['caption'])}")
    p.setdefault("tg_ids", []).extend(ids)


def receive_video(state: dict, msg: dict, target: str | None) -> None:
    video = tg.video_in(msg)
    if not target:
        waiting = [pid for pid in state["current_week"]
                   if state["posts"][pid].get("kind") == "reel" and state["posts"][pid]["status"] == "awaiting_video"]
        target = waiting[0] if waiting else None
    if not target or state["posts"][target].get("kind") != "reel":
        tg.send_message("Which Reel is this for? Reply to that Reel's script message with the video.")
        return
    p = state["posts"][target]
    if p["status"] == "posted":
        tg.send_message(f"{label(state, target)} is already live.")
        return
    media.pull()
    rel = f"originals/{target}-{int(now().timestamp())}.mp4"
    (media.MEDIA / "originals").mkdir(parents=True, exist_ok=True)
    try:
        tg.download(video, str(media.MEDIA / rel))
    except ValueError:
        tg.send_message("That video is over Telegram's 20 MB bot limit. Send it again as a normal video "
                        "(not as a file) so Telegram compresses it, or record at 720p.")
        return
    p.update(original=rel, plan=None)
    tg.send_message(f"🎬 Got it! Editing {label(state, target)} now, preview in about 3–5 minutes.")
    edit_and_preview(state, target)


def to_poster(state: dict, pid: str) -> None:
    p = state["posts"][pid]
    if p.get("kind") != "reel" or p["status"] == "posted":
        tg.send_message(f"{label(state, pid)} isn't a Reel waiting to go out.")
        return
    tg.send_message(f"🖼 Making a poster for {label(state, pid)} instead…")
    slot, day = poster_slot(p["slot"]), date.fromisoformat(p["date"])
    content = write_post(slot, day, list(state["topics_used"]))
    img = POSTS_DIR / f"{p['id'][:10]}" / f"{pid}-poster.jpg"
    img.parent.mkdir(parents=True, exist_ok=True)
    render([(content, p["meta"], str(img))])
    p.update(kind="poster", slot=slot, content=content, image=str(img.relative_to(ROOT)), image_pushed=False,
             status="pending", reminded=False)
    send_post(state, pid, f"{label(state, pid)} · {slot['series']} (poster) · {when(p)}")


# ───────────────────────── 2. your Telegram replies ─────────────────────────

def post_for_reply(state: dict, message_id: int | None) -> str | None:
    if not message_id:
        return None
    for pid, p in state["posts"].items():
        if message_id in p.get("tg_ids", []):
            return pid
    return None


def ids_from_numbers(state: dict, text: str) -> list[str]:
    out = []
    for n in re.findall(r"\d+", text):
        i = int(n) - 1
        if 0 <= i < len(state["current_week"]):
            out.append(state["current_week"][i])
    return out


def approve(state: dict, pids: list[str]) -> None:
    lines = []
    for pid in pids:
        p = state["posts"][pid]
        if p["status"] == "awaiting_video":
            lines.append(f"🎬 {label(state, pid)} needs your video first (or reply \"poster\" to its script).")
        elif p["status"] in ("pending", "skipped", "failed"):
            p["status"], p["failures"] = "approved", 0
            due = datetime.fromisoformat(p["scheduled_at"]) <= now()
            lines.append(f"✅ {label(state, pid)} approved · " + ("posting within 15 min" if due else f"goes live {when(p)}"))
        elif p["status"] == "posted":
            lines.append(f"{label(state, pid)} is already posted.")
    if lines:
        tg.send_message("\n".join(lines))


def skip(state: dict, pids: list[str]) -> None:
    for pid in pids:
        if state["posts"][pid]["status"] != "posted":
            state["posts"][pid]["status"] = "skipped"
    if pids:
        tg.send_message("⏭ Skipped " + ", ".join(label(state, p) for p in pids) + ". Say 'approve N' to bring one back.")


def change(state: dict, pid: str, feedback: str) -> None:
    p = state["posts"][pid]
    if p["status"] == "posted":
        tg.send_message(f"{label(state, pid)} is already live on Instagram, so I can't change it.")
        return
    if p.get("kind") == "reel" and p.get("original"):
        tg.send_message(f"✂️ Re-editing {label(state, pid)}: “{feedback}”")
        edit_and_preview(state, pid, feedback=feedback)
        return
    tg.send_message(f"🔁 Reworking {label(state, pid)}: “{feedback}”")
    avoid = [t for t in state["topics_used"] if t != p["content"]["topic"]]
    day = date.fromisoformat(p["date"])
    if p.get("kind") == "reel":
        content = write_reel_script(p["slot"], day, avoid, previous=p["content"], feedback=feedback)
    else:
        content = write_post(p["slot"], day, avoid, previous=p["content"], feedback=feedback)
    if p["content"]["topic"] in state["topics_used"]:
        state["topics_used"].remove(p["content"]["topic"])
    state["topics_used"].append(content["topic"])
    p["content"] = content
    if p.get("kind") == "reel":
        send_script(state, pid, f"{label(state, pid)} REEL (new script) · {p['slot']['series']} · {when(p)}")
        return
    p["rev"] += 1
    new_img = (ROOT / p["image"]).parent / f"{pid}-v{p['rev']}.jpg"
    render([(content, p["meta"], str(new_img))])
    p.update(image=str(new_img.relative_to(ROOT)), image_pushed=False, status="pending", reminded=False)
    send_post(state, pid, f"{label(state, pid)} (revised) · {p['slot']['series']} · {when(p)}")


def status_text(state: dict) -> str:
    if not state["current_week"]:
        return "No posts drafted yet."
    icons = {"pending": "🕓 waiting for your OK", "approved": "✅ approved", "posted": "📸 posted",
             "skipped": "⏭ skipped", "failed": "⚠️ failed", "awaiting_video": "🎬 waiting for your video"}
    rows = []
    for i, pid in enumerate(state["current_week"], 1):
        p = state["posts"][pid]
        kind = " REEL" if p.get("kind") == "reel" else ""
        rows.append(f"#{i} {p['slot']['series']}{kind} · {when(p)} · {icons.get(p['status'], p['status'])}")
    q = f"\n\nQueued questions: {len(state['questions'])}" if state["questions"] else ""
    return "\n".join(rows) + q


def handle(state: dict, msg: dict) -> None:
    target = post_for_reply(state, (msg.get("reply_to_message") or {}).get("message_id"))
    if tg.video_in(msg):
        receive_video(state, msg, target)
        return
    text = (msg.get("text") or msg.get("caption") or "").strip()
    if not text:
        return
    low = text.lower().strip(" .!")

    if target:
        if low in APPROVE or low.startswith("approve"):
            approve(state, [target])
        elif low in SKIP:
            skip(state, [target])
        elif low.startswith("retry"):
            approve(state, [target])
        elif low in ("poster", "use poster", "poster instead"):
            to_poster(state, target)
        else:
            feedback = re.sub(r"^(rejected|reject|change|changes|redo|fix)\b[\s:,\-.]*", "", text, flags=re.I).strip()
            change(state, target, feedback or text)
        return

    if low in ("help", "/help", "/start"):
        tg.send_message(HELP)
    elif low == "status":
        tg.send_message(status_text(state))
    elif m := re.match(r"^(q|question)\s*[:\-]\s*(.+)$", text, re.I | re.S):
        state["questions"].append(m.group(2).strip())
        tg.send_message(f"📥 Saved for Ask HyZone ({len(state['questions'])} in queue).")
    elif low in APPROVE:
        approve(state, [p for p in state["current_week"] if state["posts"][p]["status"] == "pending"])
    elif m := re.match(r"^(approve|approved|ok|retry)\s+#?([\d ,&#and]+)$", low):
        approve(state, ids_from_numbers(state, m.group(2)))
    elif m := re.match(r"^(skip|reject|rejected|drop)\s+#?([\d ,&#and]+)$", low):
        skip(state, ids_from_numbers(state, m.group(2)))
    elif m := re.match(r"^poster\s+#?(\d+)$", low):
        for pid in ids_from_numbers(state, m.group(1)):
            to_poster(state, pid)
    elif m := re.match(r"^(change|edit|redo|fix|rejected|reject)\s*#?(\d+)\s*[:\-,.]?\s*(.+)$", text, re.I | re.S):
        pids = ids_from_numbers(state, m.group(2))
        if pids:
            change(state, pids[0], m.group(3).strip())
        else:
            tg.send_message("Which post number? e.g. change 3: make it about ants")
    else:
        tg.send_message("I didn't catch that. Tip: reply directly to the poster, script or video you mean.\n\n" + HELP)


def process_telegram(state: dict) -> None:
    my_chat = str(tg.chat_id())
    for upd in tg.get_updates(state["telegram_offset"]):
        state["telegram_offset"] = upd["update_id"] + 1
        msg = upd.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != my_chat:
            continue  # ignore anyone else who finds the bot
        try:
            handle(state, msg)
        except Exception as e:
            notify_error(state, "Handling your message", e)


# ───────────────────────── 3. publishing ─────────────────────────

def image_url(path: str) -> str:
    repo = env("GITHUB_REPOSITORY")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"


def instagram_connected() -> bool:
    return bool(os.environ.get("IG_ACCESS_TOKEN", "").strip() and os.environ.get("IG_USER_ID", "").strip())


def publish_due(state: dict) -> None:
    t = now()
    early = timedelta(hours=float(CFG.get("reels", {}).get("remind_hours_before", 6)))
    for pid, p in sorted(state["posts"].items(), key=lambda kv: kv[1]["scheduled_at"]):
        at = datetime.fromisoformat(p["scheduled_at"])
        first = (p.get("tg_ids") or [None])[0]
        if p["status"] == "awaiting_video" and at - early <= t < at and not p.get("early_reminded"):
            p["early_reminded"] = True
            tg.send_message(f"🎬 {label(state, pid)} Reel ({p['slot']['series']}) goes out at {when(p)}. "
                            "Reply to the script with your video, or reply \"poster\" to use a poster instead.",
                            reply_to=first)
        if at > t:
            continue
        if p["status"] == "approved" and not instagram_connected():
            # Manual mode until Instagram is connected: hand Dev the finished file + caption to post himself.
            try:
                caption = fill(p["content"]["caption"])
                head = f"📲 Time to post {label(state, pid)} · {p['slot']['series']}\n" \
                       "Save this, open Instagram, post it, and paste the caption below."
                if p.get("kind") == "reel":
                    media.pull()
                    tg.send_video(str(media.MEDIA / p["video"]), head)
                else:
                    tg.send_photo(str(ROOT / p["image"]), head)
                tg.send_message(caption)
                p["status"] = "posted"
            except Exception as e:
                notify_error(state, f"Sending {label(state, pid)} to post", e)
            continue
        if p["status"] == "approved" and (p.get("kind") == "reel" or p.get("image_pushed", True)):
            try:
                caption = fill(p["content"]["caption"])
                if p.get("kind") == "reel":
                    p["ig_id"] = instagram.publish_reel(media.url(p["video"]), caption)
                else:
                    p["ig_id"] = instagram.publish(image_url(p["image"]), caption)
                p["status"] = "posted"
                tg.send_message(f"📸 Posted {label(state, pid)} · {p['slot']['series']}")
            except Exception as e:
                p["failures"] = p.get("failures", 0) + 1
                if p["failures"] >= 3:
                    p["status"] = "failed"
                    tg.send_message(f"⚠️ Gave up posting {label(state, pid)} after 3 tries: {e}\n"
                                    f"Fix the issue, then reply 'retry {label(state, pid)[1:]}'.")
                else:
                    notify_error(state, f"Posting {label(state, pid)}", e)
        elif p["status"] in ("pending", "awaiting_video") and not p.get("reminded"):
            p["reminded"] = True
            what = "needs your video" if p["status"] == "awaiting_video" else "isn't approved"
            tg.send_message(f"⏰ {label(state, pid)} ({p['slot']['series']}) was due at {when(p)} but {what}. "
                            "Reply 'approved' / send the video to post it now, 'poster' to swap in a poster, or 'skip'.",
                            reply_to=first)


# ───────────────────────── 4. Instagram token refresh ─────────────────────────

def set_github_secret(name: str, value: str) -> None:
    from nacl import encoding, public
    repo, pat = env("GITHUB_REPOSITORY"), env("GH_PAT")
    h = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"}
    key = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=h, timeout=30)
    key.raise_for_status()
    k = key.json()
    box = public.SealedBox(public.PublicKey(k["key"].encode(), encoding.Base64Encoder()))
    enc = base64.b64encode(box.encrypt(value.encode())).decode()
    r = requests.put(f"https://api.github.com/repos/{repo}/actions/secrets/{name}", headers=h, timeout=30,
                     json={"encrypted_value": enc, "key_id": k["key_id"]})
    r.raise_for_status()


def maybe_refresh_token(state: dict) -> None:
    if not os.environ.get("GH_PAT") or not instagram_connected():
        return
    last = state.get("token_refreshed_at")
    if last and now() - datetime.fromisoformat(last) < timedelta(days=30):
        return
    set_github_secret("IG_ACCESS_TOKEN", instagram.refresh_token(env("IG_ACCESS_TOKEN")))
    state["token_refreshed_at"] = now().isoformat()
    tg.send_message("🔑 Instagram access renewed for another 60 days.")


# ───────────────────────── entry ─────────────────────────

def main() -> None:
    action = os.environ.get("ACTION", "run") or "run"
    force = os.environ.get("FORCE", "false").lower() == "true"
    state = st.load()
    for p in state["posts"].values():
        p["image_pushed"] = True  # anything in the saved state was pushed by an earlier run

    steps = []
    if action == "test":
        steps.append(("Test run", lambda: send_test(state)))
    steps += [
        ("Drafting posts", lambda: maybe_generate(state, action, force)),
        ("Reading Telegram", lambda: process_telegram(state)),
        ("Publishing", lambda: publish_due(state)),
        ("Renewing Instagram access", lambda: maybe_refresh_token(state)),
    ]
    try:
        for name, fn in steps:
            try:
                fn()
                clear_error(state, name)
            except Exception as e:
                notify_error(state, name, e)
    finally:
        st.save(state)


if __name__ == "__main__":
    main()
