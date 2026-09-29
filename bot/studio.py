"""Raw clip in → finished Reel out. Director (AI) plans; editor (ffmpeg) executes."""
from pathlib import Path

from . import director, reel
from .config import CFG
from .render import render_overlays


def make_reel(src: str, script: dict, series: str, workdir: str, out: str,
              previous: dict | None = None, feedback: str | None = None) -> dict:
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    rcfg = CFG.get("reels", {})

    chunks = reel.speech_chunks(src)
    proxy = str(work / "proxy.mp4")
    reel.make_proxy(src, proxy)
    plan = director.plan_edit(proxy, chunks, script, previous=previous, feedback=feedback)

    kept = [c for c in plan["chunks"] if c["keep"]]
    body = sum(c["end"] - c["start"] for c in kept)
    hook_png, end_png = str(work / "hook.png"), str(work / "end.png")
    jobs = [("reel_hook.html", {"series": series, "hook": plan["hook"]}, hook_png, True),
            ("reel_end.html", {}, end_png, False)]
    cards, t = [], 0.0
    for n, c in enumerate(kept):
        d = c["end"] - c["start"]
        if c["card"]:
            png = str(work / f"card{n}.png")
            jobs.append(("reel_card.html", {"card": c["card"]}, png, True))
            cards.append((png, t, min(body, max(t + d, t + 1.8))))  # stay up long enough to read
        t += d
    render_overlays(jobs)

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    reel.compose(src, str(work), kept, hook_png, end_png, cards, out,
                 end_seconds=float(rcfg.get("end_card_seconds", 2.5)),
                 font=rcfg.get("caption_font", "Noto Sans"))
    return plan
