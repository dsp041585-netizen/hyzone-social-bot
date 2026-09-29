"""Reel files live on a separate 'media' branch of THIS repo, force-pushed as a single commit,
so videos never pile up in the main branch history. Instagram fetches them by public URL."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import ROOT, env

MEDIA = ROOT / "media"          # local working copy (git-ignored on main)
BRANCH = "media"


def _git(*args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd or ROOT, capture_output=True, text=True, check=check)


def _remote() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = env("GITHUB_REPOSITORY")
    return f"https://x-access-token:{token}@github.com/{repo}.git" if token else f"https://github.com/{repo}.git"


def pull() -> None:
    """Brings the media branch files into ./media (no-op if the branch doesn't exist yet)."""
    if MEDIA.exists():
        return
    MEDIA.mkdir(parents=True)
    r = _git("fetch", "--depth", "1", _remote(), BRANCH, check=False)
    if r.returncode != 0:
        return
    archive = subprocess.run(["git", "archive", "FETCH_HEAD"], cwd=ROOT, capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(MEDIA)], input=archive, check=True)


def push(keep: set[str]) -> None:
    """Force-pushes ./media as one fresh commit, keeping only files in `keep` (relative paths)."""
    for f in list(MEDIA.rglob("*")):
        if f.is_file() and str(f.relative_to(MEDIA)) not in keep:
            f.unlink()
    tmp = Path(tempfile.mkdtemp())
    try:
        shutil.copytree(MEDIA, tmp, dirs_exist_ok=True)
        _git("init", "-q", "-b", BRANCH, cwd=tmp)
        _git("add", "-A", cwd=tmp)
        _git("-c", "user.name=hyzone-bot", "-c", "user.email=hyzone-bot@users.noreply.github.com",
             "commit", "-q", "--allow-empty", "-m", "media", cwd=tmp)
        _git("push", "-q", "-f", _remote(), f"{BRANCH}:{BRANCH}", cwd=tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def url(rel: str) -> str:
    return f"https://raw.githubusercontent.com/{env('GITHUB_REPOSITORY')}/{BRANCH}/{rel}"
