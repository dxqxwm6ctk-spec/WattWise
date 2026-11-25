"""Draws the WattWise app icon and splash images, then writes every size Android, iOS and web need.

Run from the mobile/ folder:  python tool/make_icons.py
Needs: Pillow and CairoSVG (pip install pillow cairosvg).

The design: a lavender house outline with a lightning bolt inside, on the dark "ink" colour
used across the app. House = smart home, bolt = electricity.
"""
import io
import json
from pathlib import Path

from PIL import Image
import cairosvg

INK = "#0B0B0F"
INK_LIGHT = "#1B1B22"
LIME = "#A9A4F7"
ROOT = Path(__file__).resolve().parent.parent

# The mark (house + bolt) drawn on a 1024 x 1024 canvas, centred on (512, 512).
MARK = f"""
<g transform="translate(0,-23)">
  <path d="M290 470 L512 280 L734 470 V756 Q734 790 700 790 H324 Q290 790 290 756 Z"
        fill="none" stroke="{LIME}" stroke-width="52" stroke-linejoin="round"/>
  <path d="M556 382 L440 580 H506 L474 712 L590 506 H522 Z" fill="{LIME}" stroke="{LIME}"
        stroke-width="18" stroke-linejoin="round"/>
</g>"""


def mark(scale):
    """The mark scaled around the canvas centre."""
    return f'<g transform="translate(512,512) scale({scale}) translate(-512,-512)">{MARK}</g>'


def background(rounded):
    radius = 230 if rounded else 0
    return f"""
<defs><radialGradient id="bg" cx="25%" cy="15%" r="95%">
  <stop offset="0" stop-color="{INK_LIGHT}"/><stop offset="1" stop-color="{INK}"/>
</radialGradient></defs>
<rect width="1024" height="1024" rx="{radius}" fill="url(#bg)"/>"""


def svg(body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">{body}</svg>'


DESIGNS = {
    # Full square icon (iOS rounds the corners itself, Android legacy icons too).
    "icon": svg(background(False) + mark(1.0)),
    # Rounded preview for docs and the web favicon.
    "icon_rounded": svg(background(True) + mark(1.0)),
    # Android adaptive icon foreground: mark only, inside the 66/108 safe circle.
    "foreground": svg(mark(0.80)),
    # Splash: mark only, inside the 192/288 circle Android 12 shows (same size everywhere).
    "splash": svg(mark(0.90)),
}


def render_all():
    """Turns each SVG drawing into a 1024 x 1024 PNG image."""
    return {
        name: Image.open(io.BytesIO(cairosvg.svg2png(bytestring=code.encode()))).convert("RGBA")
        for name, code in DESIGNS.items()
    }


def save(img, path, size, opaque=False):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    out = img.resize((size, size), Image.LANCZOS)
    if opaque:  # iOS refuses icons with transparency
        out = out.convert("RGB")
    out.save(path, optimize=True)


def main():
    img = render_all()
    branding = "assets/branding"
    for name, code in DESIGNS.items():
        (ROOT / branding / f"{name}.svg").write_text(code)
    save(img["icon"], f"{branding}/icon_1024.png", 1024, opaque=True)
    save(img["icon_rounded"], f"{branding}/icon_rounded_1024.png", 1024)

    # Android: legacy icons, adaptive foreground, splash images.
    densities = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
    res = "android/app/src/main/res"
    for d, k in densities.items():
        save(img["icon"], f"{res}/mipmap-{d}/ic_launcher.png", round(48 * k))
        save(img["foreground"], f"{res}/drawable-{d}/ic_launcher_foreground.png", round(108 * k))
        save(img["splash"], f"{res}/drawable-{d}/splash_logo.png", round(288 * k))

    # iOS: every size listed in the asset catalogue, plus the launch image.
    icons = ROOT / "ios/Runner/Assets.xcassets/AppIcon.appiconset"
    for entry in json.loads((icons / "Contents.json").read_text())["images"]:
        pt = float(entry["size"].split("x")[0])
        scale = int(entry["scale"][0])
        save(img["icon"], icons.relative_to(ROOT) / entry["filename"], round(pt * scale), opaque=True)
    launch = "ios/Runner/Assets.xcassets/LaunchImage.imageset"
    for suffix, k in (("", 1), ("@2x", 2), ("@3x", 3)):
        save(img["splash"], f"{launch}/LaunchImage{suffix}.png", 288 * k)

    # Web build.
    save(img["icon_rounded"], "web/favicon.png", 32)
    save(img["icon_rounded"], "web/icons/Icon-192.png", 192)
    save(img["icon_rounded"], "web/icons/Icon-512.png", 512)
    save(img["icon"], "web/icons/Icon-maskable-192.png", 192, opaque=True)
    save(img["icon"], "web/icons/Icon-maskable-512.png", 512, opaque=True)
    print("done")


if __name__ == "__main__":
    main()
