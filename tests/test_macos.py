from __future__ import annotations

import plistlib
import shutil
import sys
from pathlib import Path

import pytest

from econoclast.app import ICON
from econoclast.app.macos import BUNDLE_ID, app_icon, app_icon_png, info_plist, make_icns
from econoclast.version import __version__


def test_info_plist_names_the_app_and_version() -> None:
    p = info_plist()
    assert p["CFBundleIdentifier"] == BUNDLE_ID
    assert p["CFBundleExecutable"] == p["CFBundleName"] == "Econoclast"
    assert p["CFBundleShortVersionString"] == p["CFBundleVersion"] == __version__
    assert p["CFBundleIconFile"] == "Econoclast"
    assert "CFBundleIconFile" not in info_plist(icon=False)
    plistlib.dumps(info_plist(LSUIElement=False))  # serialisable with extras


def test_app_icon_sits_on_apples_grid() -> None:
    im = app_icon(Path(ICON), 1024)
    assert im.size == (1024, 1024) and im.mode == "RGBA"
    assert im.getpixel((10, 10))[3] == 0  # transparent margin
    assert im.getpixel((512, 512))[3] == 255  # opaque body
    assert im.getpixel((108, 108))[3] < 255  # rounded corner, not a square
    assert app_icon_png(Path(ICON), 64).startswith(b"\x89PNG")


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("iconutil"), reason="needs macOS iconutil")
def test_make_icns(tmp_path: Path) -> None:
    out = tmp_path / "Econoclast.icns"
    make_icns(Path(ICON), out)
    assert out.read_bytes()[:4] == b"icns"


darwin_only = pytest.mark.skipif(sys.platform != "darwin", reason="macOS app bundles")


@pytest.fixture
def source_install(tmp_path, monkeypatch):  # noqa: ANN001, ANN201
    """install-app as run from a source checkout, with ~ moved into tmp_path."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "executable", "/usr/local/bin/python3")
    monkeypatch.delenv("ECONOCLAST_BUNDLE", raising=False)
    return tmp_path / "Applications" / "Econoclast.app"


@darwin_only
def test_install_app_replaces_only_its_own_thin_launcher(source_install):
    from econoclast.app.macos import install, is_thin_launcher

    assert install() == source_install and is_thin_launcher(source_install)
    assert install() == source_install  # a second run replaces the launcher it wrote


@darwin_only
def test_install_app_never_touches_the_self_contained_app(source_install):
    from econoclast.app.macos import install

    (source_install / "Contents" / "MacOS").mkdir(parents=True)
    (source_install / "Contents" / "Resources" / "python").mkdir(parents=True)
    (source_install / "Contents" / "MacOS" / "Econoclast").write_bytes(b"\xcf\xfa\xed\xfe")
    with pytest.raises(SystemExit, match="self-contained"):
        install()
    assert (source_install / "Contents" / "Resources" / "python").is_dir()


@darwin_only
def test_install_app_refuses_to_run_from_inside_the_app(source_install, monkeypatch):
    from econoclast.app.macos import install

    monkeypatch.setenv("ECONOCLAST_BUNDLE", "1")
    with pytest.raises(SystemExit, match="already runs"):
        install()
    assert not source_install.exists()
