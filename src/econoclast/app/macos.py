"""Install Econoclast as a real macOS app (Dock, Launchpad, Spotlight).

    econoclast install-app            # ~/Applications/Econoclast.app
    econoclast install-app --system   # /Applications/Econoclast.app

The bundle is a thin launcher around the Python that has Econoclast installed, so
upgrading the package upgrades the app.
"""

from __future__ import annotations

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
    base = Path("/Applications") if system else Path.home() / "Applications"
    base.mkdir(parents=True, exist_ok=True)
    app = base / "Econoclast.app"
    if app.exists():
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

    icon_name = ""
    if Path(ICON).exists() and shutil.which("iconutil"):
        icon_name = "Econoclast"
        _make_icns(Path(ICON), res / f"{icon_name}.icns")

    plist = {
        "CFBundleName": "Econoclast",
        "CFBundleDisplayName": "Econoclast",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": __version__,
        "CFBundleShortVersionString": __version__,
        "CFBundleExecutable": "Econoclast",
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.education",
    }
    if icon_name:
        plist["CFBundleIconFile"] = icon_name
    with open(app / "Contents" / "Info.plist", "wb") as fh:
        plistlib.dump(plist, fh)
    subprocess.run(["touch", str(app)], check=False)
    return app


def _make_icns(png: Path, out: Path) -> None:
    from PIL import Image

    src = Image.open(png).convert("RGBA")
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "Econoclast.iconset"
        iconset.mkdir()
        for size in (16, 32, 64, 128, 256, 512):
            src.resize((size, size), Image.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
            src.resize((size * 2, size * 2), Image.LANCZOS).save(iconset / f"icon_{size}x{size}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
