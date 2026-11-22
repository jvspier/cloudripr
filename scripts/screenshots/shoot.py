"""Take the README screenshots from a seeded demo (see seed.py).

    uv run --with playwright python scripts/screenshots/shoot.py DEMO_DIR docs/images

Starts cloudripr on the demo data with the icloudpd simulator (nothing talks to Apple),
then captures laptop and phone screens in light and dark, the 2FA code screen, and a
composite hero image. Uses the installed Google Chrome when there is one.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import Browser, Page, sync_playwright


REPO = Path(__file__).resolve().parents[2]
PORT = 18765
BASE = f"http://127.0.0.1:{PORT}"
PASSWORD = "demo-password"
LAPTOP = {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 2}
PHONE = {
    "viewport": {"width": 393, "height": 852},
    "device_scale_factor": 3,
    "is_mobile": True,
    "has_touch": True,
}


def start_server(demo: Path) -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "CLOUDRIPR_ICLOUDPD_CMD": f"{sys.executable} {REPO / 'tests/fixtures/icloudpd_sim.py'}",
        "ICLOUDPD_SIM_MODE": "twofa",  # the re-auth screenshot waits for a code
    }
    proc = subprocess.Popen(
        [shutil.which("cloudripr") or "cloudripr", "--data-dir", str(demo / "data"),
         "--host", "127.0.0.1", "--port", str(PORT)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )  # fmt: skip
    for _ in range(50):
        try:
            urllib.request.urlopen(f"{BASE}/api/auth/status", timeout=1)
            return proc
        except OSError:
            time.sleep(0.2)
    proc.kill()
    raise SystemExit("cloudripr did not start")


def login(page: Page) -> None:
    page.goto(BASE + "/")
    page.fill("input[type=password]", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_selector("nav[aria-label=Main]")


def shot(page: Page, path: str, out: Path) -> None:
    page.goto(BASE + path)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(600)  # thumbnails decode
    page.screenshot(path=str(out))


def latest_run(page: Page) -> str:
    runs = json.loads(page.evaluate("fetch('/api/library/runs').then(r => r.text())"))
    return runs[0]["run"]["id"]


def capture(browser: Browser, out: Path) -> None:
    month = time.strftime("%Y-%m")
    for device, opts in (("laptop", LAPTOP), ("phone", PHONE)):
        for theme in ("light", "dark"):
            ctx = browser.new_context(color_scheme=theme, **opts)
            page = ctx.new_page()
            login(page)
            run = latest_run(page)
            for name, path in (
                ("home", "/"),
                ("photos", "/photos"),
                ("month", f"/photos/month/{month}"),
                ("run", f"/runs/{run}"),
                ("settings", "/settings"),
            ):
                shot(page, path, out / f"{device}-{theme}-{name}.png")
            ctx.close()
    # The 2FA screen: start a sign-in; the simulator then waits for a code.
    for theme in ("light", "dark"):
        ctx = browser.new_context(color_scheme=theme, **PHONE)
        page = ctx.new_page()
        login(page)
        page.evaluate("fetch('/api/account/reauth', {method: 'POST'})")
        page.goto(BASE + "/account/reauth")
        page.wait_for_selector("input[inputmode=numeric]", timeout=15_000)
        page.wait_for_timeout(500)
        page.screenshot(path=str(out / f"phone-{theme}-reauth.png"))
        page.evaluate("fetch('/api/account/reauth', {method: 'DELETE'})")
        ctx.close()


def hero(browser: Browser, out: Path) -> None:
    compose(browser, out, "hero", {"width": 1600, "height": 900}, scale=2)
    # GitHub's social preview: 1280x640, under 1 MB (Settings → General → Social preview).
    compose(browser, out, "social", {"width": 1280, "height": 640}, scale=1)


def compose(
    browser: Browser, out: Path, name: str, viewport: dict[str, int], *, scale: int
) -> None:
    html = (Path(__file__).parent / f"{name}.html").read_text()
    html = html.replace("{{ICON}}", (REPO / "web/public/icon-512.png").as_uri())
    page_file = out / f".{name}.html"  # a file:// page may load the screenshots next to it
    page_file.write_text(html)
    page = browser.new_page(viewport=viewport, device_scale_factor=scale)
    try:
        page.goto(page_file.resolve().as_uri())
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(out / f"{name}.png"))
    finally:
        page.close()
        page_file.unlink(missing_ok=True)


# What the README uses; everything else captured is only input for these.
KEEP = {"hero.png", "social.png", "phones.png", "laptop-dark-home.png", "laptop-light-month.png"}
PHONES = ("phone-light-home.png", "phone-light-reauth.png", "phone-dark-photos.png")


def phone_strip(out: Path) -> None:
    """Three phone screens side by side, rounded like a phone, on a transparent canvas."""
    width, gap, radius = 560, 48, 64
    shots = []
    for name in PHONES:
        with Image.open(out / name) as img:
            shot = img.convert("RGB").resize((width, round(img.height * width / img.width)))
        mask = Image.new("L", shot.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([(0, 0), shot.size], radius, fill=255)
        shot.putalpha(mask)
        shots.append(shot)
    strip = Image.new("RGBA", (len(shots) * width + (len(shots) - 1) * gap, shots[0].height))
    for i, shot in enumerate(shots):
        strip.paste(shot, (i * (width + gap), 0), shot)
    strip.save(out / "phones.png", optimize=True)


def tidy(out: Path) -> None:
    for png in out.glob("*.png"):
        if png.name not in KEEP:
            png.unlink()
            continue
        with Image.open(png) as img:
            img.load()
        if img.width > 2400:
            img = img.resize((2400, round(img.height * 2400 / img.width)), Image.LANCZOS)
        img.save(png, optimize=True)


def main(demo: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    proc = start_server(demo)
    try:
        with sync_playwright() as p:
            chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
            browser = p.chromium.launch(channel="chrome") if chrome else p.chromium.launch()
            capture(browser, out)
            hero(browser, out)
            browser.close()
        phone_strip(out)
        tidy(out)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    print(f"screenshots in {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]))
