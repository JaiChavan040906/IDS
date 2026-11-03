"""Render every SVG in this folder to a PNG at 2x resolution (needs Playwright + Microsoft Edge)."""
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    for svg in sorted(HERE.glob("*.svg")):
        head = svg.read_text(encoding="utf-8")[:300]
        w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', head).groups())
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
        page.goto(svg.as_uri())
        page.screenshot(path=str(svg.with_suffix(".png")), full_page=False)
        page.close()
        print("rendered", svg.with_suffix(".png").name)
    browser.close()
