"""The Econoclast desktop app: a native window onto the living mosaic.

``econoclast`` (or ``econoclast app``) opens it. Hunts run in their own background
processes, so closing the window never kills a hunt; reopening the app picks the story
up from the case's event log.
"""

from __future__ import annotations

import sys
from pathlib import Path

from econoclast.app.api import WEB, Api
from econoclast.log import get_logger

log = get_logger("app")

ICON = WEB / "assets" / "icon.png"


def run(*, debug: bool = False) -> None:
    try:
        import webview
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("The app needs pywebview: pip install 'econoclast[app]'") from exc

    _macos_identity()
    api = Api()
    window = webview.create_window(
        "Econoclast",
        url=str(WEB / "index.html"),
        js_api=api,
        width=1480,
        height=940,
        min_size=(1120, 720),
        background_color="#0b1430",
        text_select=True,
    )
    api._window = window
    window.events.loaded += lambda: _wire_drop(window)
    webview.start(_after_start, debug=debug, http_server=True, private_mode=False)


def _after_start() -> None:
    _macos_dock_icon()


def _wire_drop(window) -> None:  # noqa: ANN001
    """Files dropped on the window arrive with their real paths only on the Python side."""
    import json

    try:
        from webview.dom import DOMEventHandler
    except ImportError:  # pragma: no cover - older pywebview
        return

    def on_drop(event: dict) -> None:
        files = (event.get("dataTransfer") or {}).get("files") or []
        log.info("drop: %d file(s) %s", len(files), [f.get("pywebviewFullPath") for f in files])
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if paths:
            window.evaluate_js(f"window.__nativeDrop && window.__nativeDrop({json.dumps(paths)})")

    try:
        window.dom.document.events.dragover += DOMEventHandler(lambda e: None, True, True)
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
    except Exception as exc:  # noqa: BLE001 - drag and drop is a convenience
        log.warning("native drag and drop unavailable: %s", exc)


def _macos_identity() -> None:
    """Show 'Econoclast' (not 'Python') in the menu bar and the app switcher."""
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSBundle

        info = NSBundle.mainBundle().infoDictionary()
        info["CFBundleName"] = "Econoclast"
        info["CFBundleDisplayName"] = "Econoclast"
    except Exception:  # noqa: BLE001 - cosmetic only
        pass


def _macos_dock_icon() -> None:
    if sys.platform != "darwin" or not Path(ICON).exists():
        return
    try:
        from AppKit import NSApplication, NSImage
        from PyObjCTools import AppHelper

        def apply() -> None:
            img = NSImage.alloc().initWithContentsOfFile_(str(ICON))
            if img is not None:
                NSApplication.sharedApplication().setApplicationIconImage_(img)

        AppHelper.callAfter(apply)
    except Exception:  # noqa: BLE001 - cosmetic only
        pass
