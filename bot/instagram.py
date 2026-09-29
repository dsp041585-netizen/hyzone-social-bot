"""Instagram API with Instagram Login: publish image posts and Reels."""
import time

import requests

from .config import CFG, env


def _base() -> str:
    return f"https://graph.instagram.com/{CFG['instagram']['graph_version']}"


def _check(r: requests.Response) -> dict:
    data = r.json()
    if r.status_code != 200 or "error" in data:
        raise RuntimeError(f"Instagram error: {data.get('error', data)}")
    return data


def _publish(fields: dict, wait_tries: int) -> str:
    token, user = env("IG_ACCESS_TOKEN"), env("IG_USER_ID")
    container = _check(requests.post(f"{_base()}/{user}/media", timeout=60,
                                     data={**fields, "access_token": token}))["id"]
    for _ in range(wait_tries):
        status = _check(requests.get(f"{_base()}/{container}", timeout=30, params={
            "fields": "status_code", "access_token": token})).get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram could not process the media ({status})")
        time.sleep(5)
    else:
        raise RuntimeError("Instagram is still processing the media; will retry next run")
    return _check(requests.post(f"{_base()}/{user}/media_publish", timeout=60, data={
        "creation_id": container, "access_token": token}))["id"]


def publish(image_url: str, caption: str) -> str:
    return _publish({"image_url": image_url, "caption": caption[:2200]}, wait_tries=12)


def publish_reel(video_url: str, caption: str) -> str:
    return _publish({"media_type": "REELS", "video_url": video_url, "caption": caption[:2200],
                     "share_to_feed": "true"}, wait_tries=72)


def refresh_token(token: str) -> str:
    """Long-lived tokens last 60 days; refreshing gives a fresh 60 days."""
    r = requests.get("https://graph.instagram.com/refresh_access_token", timeout=30, params={
        "grant_type": "ig_refresh_token", "access_token": token})
    return _check(r)["access_token"]
