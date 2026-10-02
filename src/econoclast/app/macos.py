"""Install Econoclast as a real macOS app (Dock, Launchpad, Spotlight).

    econoclast install-app            # ~/Applications/Econoclast.app
    econoclast install-app --system   # /Applications/Econoclast.app

This bundle is a thin launcher around the Python that has Econoclast installed, so
upgrading the package upgrades the app: the developer's install. The self-contained app
and its disk image (own Python, no setup) are built by ``tools/macos/build.py``; both
share the Info.plist and icon made here.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from econoclast.app import ICON
from econoclast.version import __version__

BUNDLE_ID = "io.github.shoal-rat.econoclast"


def install(system: bool = False) -> Path:
    if sys.platform != "darwin":
        raise SystemExit("install-app builds a macOS .app; on other systems run `econoclast` directly.")
    if os.environ.get("ECONOCLAST_BUNDLE") or any(p.suffix == ".app" for p in Path(sys.executable).parents):
        raise SystemExit("This Econoclast already runs from the self-contained Econoclast.app; there is "
                         "nothing to install. Keep that app in /Applications.")
    base = Path("/Applications") if system else Path.home() / "Applications"
    base.mkdir(parents=True, exist_ok=True)
    app = base / "Econoclast.app"
    if app.exists():
        if not is_thin_launcher(app):
            raise SystemExit(f"{app} is the self-contained app from the disk image; not replacing it. "
                             "Move it to the Trash first if you want the source-install launcher instead.")
        shutil.rmtree(app)
    macos = app / "Contents" / "MacOS"
    res = app / "Contents" / "Resources"
    macos.mkdir(parents=True)
    res.mkdir(parents=True)

    launcher = macos / "Econoclast"
    launcher.write_text(
        "#!/bin/bash\n"
        "# Econoclast launcher: a login shell PATH so the app can find claude / codex / npx / uv.\n"
        'export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"\n'
        'mkdir -p "$HOME/.econoclast"\n'
        f'exec "{sys.executable}" -m econoclast app "$@" >> "$HOME/.econoclast/app.log" 2>&1\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)

    has_icon = Path(ICON).exists() and shutil.which("iconutil") is not None
    if has_icon:
        make_icns(Path(ICON), res / "Econoclast.icns")
    with open(app / "Contents" / "Info.plist", "wb") as fh:
        plistlib.dump(info_plist(icon=has_icon), fh)
    subprocess.run(["touch", str(app)], check=False)
    return app


def is_thin_launcher(app: Path) -> bool:
    """True for the launcher install-app writes (a shell script around some Python), False for the
    self-contained app, whose executable is a compiled launcher with its own interpreter beside it."""
    exe = app / "Contents" / "MacOS" / "Econoclast"
    try:
        return exe.read_bytes()[:2] == b"#!" and not (app / "Contents" / "Resources" / "python").exists()
    except OSError:
        return not (app / "Contents" / "Resources" / "python").exists()


def info_plist(*, icon: bool = True, **extra: object) -> dict:
    plist: dict = {
        "CFBundleName": "Econoclast",
        "CFBundleDisplayName": "Econoclast",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": __version__,
        "CFBundleShortVersionString": __version__,
        "CFBundleExecutable": "Econoclast",
        "CFBundlePackageType": "APPL",
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.education",
        "NSHumanReadableCopyright": "MIT License · github.com/shoal-rat/econoclast",
    }
    if icon:
        plist["CFBundleIconFile"] = "Econoclast"
    plist.update(extra)
    return plist


def make_icns(png: Path, out: Path) -> None:
    from PIL import Image

    src = app_icon(png)
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "Econoclast.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            src.resize((size, size), Image.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
            src.resize((size * 2, size * 2), Image.LANCZOS).save(iconset / f"icon_{size}x{size}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)


def app_icon(png: Path, size: int = 1024):  # noqa: ANN201 - a PIL image
    """The square mosaic medallion on Apple's icon grid: an 824/1024 rounded square with a soft shadow,
    so the app sits among the others in the Dock and Launchpad."""
    from PIL import Image, ImageDraw, ImageFilter

    k = size / 1024
    body, inset, radius = round(824 * k), round(100 * k), 185 * k
    art = Image.open(png).convert("RGBA").resize((body, body), Image.LANCZOS)
    ss = 4  # supersampled mask for a clean edge
    mask = Image.new("L", (body * ss, body * ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, body * ss - 1, body * ss - 1], radius=radius * ss, fill=255)
    mask = mask.resize((body, body), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow = Image.new("L", (size, size), 0)
    shadow.paste(mask.point(lambda v: v * 0.45), (inset, inset + round(12 * k)))
    out.putalpha(shadow.filter(ImageFilter.GaussianBlur(14 * k)))
    out = Image.composite(Image.new("RGBA", (size, size), (0, 0, 0, 255)), Image.new("RGBA", (size, size)), out)
    art.putalpha(mask)
    out.alpha_composite(art, (inset, inset))
    return out


def app_icon_png(png: Path, size: int = 512) -> bytes:
    import io

    buf = io.BytesIO()
    app_icon(png, size).save(buf, format="PNG")
    return buf.getvalue()
