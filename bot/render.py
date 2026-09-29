"""Renders poster templates to 1080x1350 JPEGs, and Reel overlays to transparent PNGs."""
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

from .config import CFG, TEMPLATES_DIR

# Shrinks text marked .fit until its [data-fit-box] container stops overflowing.
FIT_JS = """() => {
  const depth = el => { let d = 0; while (el.parentElement) { el = el.parentElement; d++; } return d; };
  const boxes = [...document.querySelectorAll('[data-fit-box]')].sort((a, b) => depth(b) - depth(a));
  for (const box of boxes) {
    const kids = [...box.querySelectorAll('.fit')];
    for (let i = 0; i < 40 && box.scrollHeight > box.clientHeight + 1; i++) {
      kids.forEach(k => { k.style.fontSize = (parseFloat(getComputedStyle(k).fontSize) * 0.95) + 'px'; });
    }
  }
}"""

_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(["html"]))


def html_for(content: dict, meta: dict) -> str:
    return _env.get_template(f"{content['format']}.html").render(c=content, m=meta, brand=CFG["brand"])


def _shoot(page, html: str, out: str, **shot) -> None:
    page.set_content(html, wait_until="networkidle")
    page.evaluate("document.fonts.ready.then(() => true)")
    page.evaluate(FIT_JS)
    page.screenshot(path=out, **shot)


def render(jobs: list[tuple[dict, dict, str]]) -> None:
    """Posters. jobs: (content, meta, output_path). meta has series and number."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350})
        for content, meta, out in jobs:
            _shoot(page, html_for(content, meta), out, type="jpeg", quality=92)
        browser.close()


def render_overlays(jobs: list[tuple[str, dict, str, bool]]) -> None:
    """Reel graphics at 1080x1920. jobs: (template name, context, output .png, transparent)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1920})
        for name, ctx, out, transparent in jobs:
            html = _env.get_template(name).render(brand=CFG["brand"], **ctx)
            _shoot(page, html, out, type="png", omit_background=transparent)
        browser.close()
