"""Telegram Bot API: send posters and Reel previews, read your replies, download your videos."""
import requests

from .config import env

API = "https://api.telegram.org/bot{token}/{method}"
MAX_DOWNLOAD = 20 * 1024 * 1024   # Telegram bots can only download files up to 20 MB


def _call(method: str, timeout: int = 60, **kw):
    r = requests.post(API.format(token=env("TELEGRAM_BOT_TOKEN"), method=method), timeout=timeout, **kw)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data["result"]


def chat_id() -> str:
    return env("TELEGRAM_CHAT_ID")


def send_message(text: str, reply_to: int | None = None) -> int:
    payload = {"chat_id": chat_id(), "text": text[:4096], "disable_web_page_preview": True}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
        payload["allow_sending_without_reply"] = True
    return _call("sendMessage", data=payload)["message_id"]


def _send_media(method: str, field: str, path: str, caption: str) -> list[int]:
    ids = []
    short = caption if len(caption) <= 1000 else caption.split("\n")[0][:1000]
    with open(path, "rb") as f:
        ids.append(_call(method, timeout=300, data={"chat_id": chat_id(), "caption": short},
                         files={field: f})["message_id"])
    if short != caption:
        ids.append(send_message(caption, reply_to=ids[0]))
    return ids


def send_photo(path: str, caption: str) -> list[int]:
    return _send_media("sendPhoto", "photo", path, caption)


def send_video(path: str, caption: str) -> list[int]:
    return _send_media("sendVideo", "video", path, caption)


def video_in(msg: dict) -> dict | None:
    """The video attached to a message, whether sent as a video, a file, or a round video note."""
    if msg.get("video"):
        return msg["video"]
    if msg.get("video_note"):
        return msg["video_note"]
    doc = msg.get("document") or {}
    if str(doc.get("mime_type", "")).startswith("video/"):
        return doc
    return None


def download(file: dict, dest: str) -> None:
    if file.get("file_size", 0) > MAX_DOWNLOAD:
        raise ValueError("too big")
    path = _call("getFile", data={"file_id": file["file_id"]})["file_path"]
    url = f"https://api.telegram.org/file/bot{env('TELEGRAM_BOT_TOKEN')}/{path}"
    with requests.get(url, stream=True, timeout=300) as r, open(dest, "wb") as f:
        r.raise_for_status()
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)


def get_updates(offset: int) -> list[dict]:
    return _call("getUpdates", data={"offset": offset, "timeout": 0, "allowed_updates": '["message"]'})
