"""The editor: finds speech chunks, then assembles the Reel from the director's edit plan.

Timeline: kept chunks (with punch-in zooms) → hook title on top → pop-up cards → captions → end card.
Output: 1080x1920, 30 fps, H.264 + AAC 48 kHz, faststart (Instagram Reels spec).
"""
import re
import subprocess
from pathlib import Path

W, H = 1080, 1920
PAD = 0.12          # seconds kept before/after speech
ZOOM = 1.2          # punch-in factor


def _run(cmd: list[str], cwd: str | None = None) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-800:]}")
    return r.stderr


def duration(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def speech_chunks(path: str) -> list[tuple[float, float]]:
    """Splits the clip at pauses. Threshold adapts to how loud the recording is."""
    total = duration(path)
    vol = _run(["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect", "-vn", "-f", "null", "-"])
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", vol)
    thr = max(-45.0, min(-25.0, (float(m.group(1)) if m else -30.0) - 8))
    log = _run(["ffmpeg", "-hide_banner", "-i", path, "-af", f"silencedetect=noise={thr}dB:d=0.35", "-vn", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", log)]
    silences = list(zip(starts, ends + [total] * (len(starts) - len(ends))))

    speech, cur = [], 0.0
    for s, e in silences:
        if s > cur:
            speech.append((cur, s))
        cur = max(cur, e)
    if cur < total:
        speech.append((cur, total))

    out = []
    for s, e in speech:
        s, e = max(0.0, s - PAD), min(total, e + PAD)
        if e - s < 0.3:
            continue
        if out and s - out[-1][1] < 0.15:
            out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return [(round(s, 2), round(e, 2)) for s, e in out] or [(0.0, round(total, 2))]


def make_proxy(src: str, out: str) -> None:
    """Small copy for the AI director to watch (keeps the upload tiny)."""
    _run(["ffmpeg", "-y", "-hide_banner", "-i", src, "-vf", "scale=-2:480,fps=5", "-c:v", "libx264",
          "-preset", "veryfast", "-crf", "32", "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "32k", out])


# ───────────────────────── captions (ASS) ─────────────────────────

def _t(sec: float) -> str:
    cs = int(round(sec * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _esc(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def caption_cues(text: str, start: float, end: float, emphasis: str = "") -> list[tuple[float, float, str]]:
    """Splits a caption into 2-4 word pieces, timed by length, with the emphasis word in gold."""
    words = text.split()
    if not words:
        return []
    pieces, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= 4 or len(" ".join(cur)) >= 22:
            pieces.append(cur)
            cur = []
    if cur:
        if pieces and len(cur) == 1:
            pieces[-1] += cur
        else:
            pieces.append(cur)
    total_chars = sum(len(" ".join(p)) for p in pieces)
    emph = re.sub(r"\W", "", emphasis.lower())
    cues, t = [], start
    for p in pieces:
        d = (end - start) * len(" ".join(p)) / total_chars
        shown = []
        for w in p:
            if emph and re.sub(r"\W", "", w.lower()) == emph:
                shown.append(r"{\c&H59A0C5&}" + _esc(w) + r"{\c&HFFFFFF&}")
            else:
                shown.append(_esc(w))
        cues.append((t, t + d, " ".join(shown)))
        t += d
    return cues


def write_ass(cues: list[tuple[float, float, str]], path: str, font: str = "Noto Sans") -> None:
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},66,&H00FFFFFF,&H00FFFFFF,&H003C4D0A,&H00000000,-1,0,0,0,100,100,0,0,3,16,0,2,90,90,500,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [f"Dialogue: 0,{_t(s)},{_t(e)},Cap,,0,0,0,,{txt}" for s, e, txt in cues]
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


# ───────────────────────── assembly ─────────────────────────

def compose(src: str, workdir: str, plan: list[dict], hook_png: str, end_png: str,
            cards: list[tuple[str, float, float]], out: str, end_seconds: float = 2.5,
            font: str = "Noto Sans") -> float:
    """plan: kept chunks in order: {start, end, caption, emphasis, zoom}. cards: (png, t_start, t_end)
    on the edited timeline. Returns the final duration."""
    work = Path(workdir)
    cues, t = [], 0.0
    for c in plan:
        d = c["end"] - c["start"]
        cues += caption_cues(c.get("caption", ""), t, t + d, c.get("emphasis", ""))
        t += d
    body = t
    write_ass(cues, str(work / "subs.ass"), font)

    cmd = ["ffmpeg", "-y", "-hide_banner", "-i", src, "-i", hook_png,
           "-loop", "1", "-t", f"{end_seconds}", "-i", end_png,
           "-f", "lavfi", "-t", f"{end_seconds}", "-i", "anullsrc=r=48000:cl=stereo"]
    for png, _, _ in cards:
        cmd += ["-loop", "1", "-t", f"{body:.2f}", "-i", png]

    zw, zh = int(W * ZOOM) // 2 * 2, int(H * ZOOM) // 2 * 2
    f, labels = [], []
    for k, c in enumerate(plan):
        z = f",scale={zw}:{zh},crop={W}:{H}:{(zw - W) // 2}:{int((zh - H) * 0.3)}" if c.get("zoom") else ""
        f.append(f"[0:v]trim=start={c['start']}:end={c['end']},setpts=PTS-STARTPTS,"
                 f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1{z},fps=30[v{k}]")
        f.append(f"[0:a]atrim=start={c['start']}:end={c['end']},asetpts=PTS-STARTPTS,"
                 f"aresample=48000,aformat=channel_layouts=stereo[a{k}]")
        labels.append(f"[v{k}][a{k}]")
    f.append("".join(labels) + f"concat=n={len(plan)}:v=1:a=1[vc][acat]")
    f.append("[acat]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[an]")
    f.append("[vc][1:v]overlay=0:0[l0]")
    last = "l0"
    for i, (_, a, b) in enumerate(cards):
        inp = 4 + i
        fin = min(0.18, (b - a) / 3)
        f.append(f"[{inp}:v]format=rgba,fade=t=in:st={a:.2f}:d={fin:.2f}:alpha=1,"
                 f"fade=t=out:st={b - fin:.2f}:d={fin:.2f}:alpha=1[k{i}]")
        f.append(f"[{last}][k{i}]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[l{i + 1}]")
        last = f"l{i + 1}"
    f.append(f"[{last}]subtitles=subs.ass,format=yuv420p[vm]")
    f.append(f"[2:v]scale={W}:{H},setsar=1,fps=30,format=yuv420p[ev]")
    f.append("[vm][an][ev][3:a]concat=n=2:v=1:a=1[v][a]")

    cmd += ["-filter_complex", ";".join(f), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", out]
    _run(cmd, cwd=str(work))
    return body + end_seconds
