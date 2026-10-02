"""Paint the disk-image window: the lapis vault, a gold tesserae frame, the Sicarius's dagger
pointing at Applications, and gold plaques under the two icons so Finder's labels stay legible.

  python dmg_background.py <out_dir>    -> background.png (660x400) and background@2x.png

Runs on the Python inside the built app (it needs Pillow and Econoclast's own art).
Keep in step with icon_locations in dmg_settings.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from econoclast.app.api import WEB

W, H = 660, 400
ICONS = {"app": (165, 206), "apps": (495, 206)}
ICON = 112
GOLD = (233, 196, 106)
IVORY = (244, 236, 218)
CJK_FONTS = ("/System/Library/Fonts/Supplemental/Songti.ttc", "/System/Library/Fonts/STHeiti Light.ttc",
             "/System/Library/Fonts/Hiragino Sans GB.ttc")


def paint(s: int) -> Image.Image:
    a = WEB / "assets"
    img = tile(Image.open(a / "tex" / "lapis.jpg").convert("RGB"), W * s, H * s, scale=0.55 * s)
    img = ImageEnhance.Brightness(img).enhance(0.62)
    img = vignette(img, 0.55)
    d = ImageDraw.Draw(img)

    # gold tesserae frame with a thin red inner line, as on the app's panels
    gold = tile(Image.open(a / "tex" / "gold.jpg").convert("RGB"), W * s, H * s, scale=0.35 * s)
    band = 9 * s
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rectangle([0, 0, W * s - 1, H * s - 1], fill=255)
    ImageDraw.Draw(mask).rectangle([band, band, W * s - band - 1, H * s - band - 1], fill=0)
    img.paste(gold, (0, 0), mask)
    d.rectangle([band, band, W * s - band - 1, H * s - band - 1], outline=(150, 38, 34), width=2 * s)

    # title
    cinzel = font(WEB / "fonts" / "Cinzel-normal.woff2", 30 * s)
    italic = font(WEB / "fonts" / "CormorantGaramond-italic.woff", 19 * s)
    cjk = font(next((f for f in CJK_FONTS if Path(f).exists()), ""), 14 * s)
    centered(d, (W * s // 2, 58 * s), "E C O N O C L A S T", cinzel, GOLD, shadow=s)
    centered(d, (W * s // 2, 92 * s), "the mosaics are awake", italic, IVORY, shadow=s)

    # plaques under the labels (Finder draws black text in light mode, white in dark mode)
    plaque = ImageEnhance.Brightness(gold).enhance(0.82)
    for x, y in ICONS.values():
        box = [(x - 70) * s, (y + ICON // 2 + 3) * s, (x + 70) * s, (y + ICON // 2 + 27) * s]
        m = Image.new("L", img.size, 0)
        ImageDraw.Draw(m).rounded_rectangle(box, radius=5 * s, fill=255)
        img.paste(plaque, (0, 0), m)
        d.rounded_rectangle(box, radius=5 * s, outline=(120, 84, 30), width=s)

    # the dagger, pointing from the app to Applications
    sica = Image.open(a / "res" / "sica.png").convert("RGBA").rotate(-47, resample=Image.BICUBIC, expand=True)
    sica = sica.crop(sica.getbbox())
    tw = 150 * s
    sica = sica.resize((tw, round(sica.height * tw / sica.width)), Image.LANCZOS)
    cx, cy = (ICONS["app"][0] + ICONS["apps"][0]) // 2, ICONS["app"][1] - 4
    pos = (cx * s - sica.width // 2, cy * s - sica.height // 2)
    shadow = Image.new("RGBA", sica.size, (0, 0, 0, 0))
    shadow.putalpha(sica.getchannel("A").point(lambda v: v * 0.6))
    img.paste(shadow.filter(ImageFilter.GaussianBlur(4 * s)), (pos[0] + 2 * s, pos[1] + 4 * s), shadow)
    img.paste(sica, pos, sica)

    # instructions
    centered(d, (W * s // 2, 330 * s), "Drag Econoclast into Applications", italic, IVORY, shadow=s)
    centered(d, (W * s // 2, 356 * s), "把 Econoclast 拖进「应用程序」", cjk, (214, 205, 186), shadow=s)
    return img


def tile(tex: Image.Image, w: int, h: int, scale: float) -> Image.Image:
    tex = tex.resize((max(1, round(tex.width * scale)), max(1, round(tex.height * scale))), Image.LANCZOS)
    out = Image.new("RGB", (w, h))
    for y in range(0, h, tex.height):
        for x in range(0, w, tex.width):
            out.paste(tex, (x, y))
    return out


def vignette(img: Image.Image, strength: float) -> Image.Image:
    w, h = img.size
    m = Image.radial_gradient("L").resize((w, h), Image.BICUBIC)
    dark = Image.new("RGB", (w, h), (4, 8, 26))
    return Image.composite(dark, img, m.point(lambda v: int(v * strength)))


def font(path: Path | str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size)


def centered(d: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, f: ImageFont.FreeTypeFont,
             fill: tuple[int, int, int], shadow: int = 0) -> None:
    if shadow:
        d.text((xy[0] + shadow, xy[1] + shadow), text, font=f, fill=(0, 0, 0), anchor="mm")
    d.text(xy, text, font=f, fill=fill, anchor="mm")


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    big = paint(2)
    big.save(out / "background@2x.png")
    big.resize((W, H), Image.LANCZOS).save(out / "background.png")
    print(out / "background.png")
