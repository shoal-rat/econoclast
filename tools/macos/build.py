#!/usr/bin/env python3
"""Build the self-contained Econoclast.app and its disk image.

  python3 tools/macos/build.py              # dist/Econoclast.app + dist/Econoclast-<version>-<arch>.dmg
  python3 tools/macos/build.py --install    # ...then install from the image into /Applications
  python3 tools/macos/build.py --app-only   # just the .app
  python3 tools/macos/build.py --install-only   # install the image already in dist/

The app carries its own relocatable CPython (python-build-standalone, fetched by uv) with
Econoclast and its dependencies installed into it, a small compiled launcher
(launcher.c), the mosaic icon, and an ad-hoc signature. Hunts, the arsenal MCP server and
the Fabrica all run on the bundled interpreter, so the app needs no Python on the machine.
Like the source install it still uses Claude Code or Codex as the agent, and uv / Node
when the workshop or the browser needs them.

Runs on any Python 3.10+ (standard library only). Needs uv, the Xcode command line tools
(clang, codesign) and hdiutil; dmgbuild is fetched with uvx. The app is ad-hoc signed and
the image is unsigned; neither is notarized. Built locally it opens directly; downloaded,
the first launch needs right-click > Open (or System Settings > Privacy & Security >
Open Anyway). The minimum macOS is whatever the bundled wheels need (written into
Info.plist; numpy and scipy's Accelerate builds currently need macOS 14).
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DIST = ROOT / "dist"
PY_VERSION = "3.12"
APP_NAME = "Econoclast"
# Extras that keep the bundle permissive (PyMuPDF is AGPL and stays opt-in; pyarrow is large).
EXTRA_PACKAGES = ("openpyxl",)
# Interpreter parts a desktop app never uses.
STDLIB_DROP = ("test", "idlelib", "turtledemo", "lib2to3", "tkinter", "lib-dynload/_tkinter.cpython-312-darwin.so")
# Where the interpreter will live; recorded in sysconfig and .pyc instead of this machine's paths.
INSTALLED_PYTHON = f"/Applications/{APP_NAME}.app/Contents/Resources/python"
MACHO_MAGIC = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--app-only", action="store_true", help="build the .app, skip the disk image")
    ap.add_argument("--install", action="store_true", help="install from the image into /Applications")
    ap.add_argument("--install-only", action="store_true", help="install the image already built in dist/")
    ap.add_argument("--keep-dev-launcher", action="store_true",
                    help="leave a thin ~/Applications/Econoclast.app from `econoclast install-app` in place")
    a = ap.parse_args()
    if sys.platform != "darwin":
        sys.exit("The macOS app can only be built on macOS.")
    for tool in ("uv", "clang", "codesign", "hdiutil", "iconutil"):
        if not shutil.which(tool):
            sys.exit(f"{tool} is required (uv: brew install uv; clang/codesign: xcode-select --install).")

    if a.install_only:
        dmg = DIST / f"{APP_NAME}-{read_version()}-{machine()}.dmg"
        if not dmg.exists():
            sys.exit(f"no {dmg.name} in dist/: build it first")
        print(f"installed {install(dmg, keep_dev_launcher=a.keep_dev_launcher)}")
        return
    t0 = time.time()
    app = build_app()
    print(f"built {app} ({du(app)}) in {time.time() - t0:.0f}s")
    if a.app_only:
        return
    dmg = build_dmg(app)
    print(f"built {dmg} ({du(dmg)})")
    if a.install:
        installed = install(dmg, keep_dev_launcher=a.keep_dev_launcher)
        print(f"installed {installed}")


# ---------------------------------------------------------------- the app
def build_app() -> Path:
    version = read_version()
    app = DIST / f"{APP_NAME}.app"
    if app.exists():
        shutil.rmtree(app)
    contents = app / "Contents"
    macos, res = contents / "MacOS", contents / "Resources"
    macos.mkdir(parents=True)
    res.mkdir()

    step("python")
    base = standalone_python()
    pyhome = res / "python"
    run("ditto", str(base), str(pyhome))
    for marker in pyhome.glob("lib/python*/EXTERNALLY-MANAGED"):
        marker.unlink()  # this interpreter belongs to the app; let uv install into it
    py = pyhome / "bin" / f"python{PY_VERSION}"
    if not py.exists():
        sys.exit(f"unexpected Python layout under {base}")

    step("econoclast and its dependencies")
    env = bundled_env()
    with tempfile.TemporaryDirectory(prefix="econoclast-wheel-") as wheels:
        # sdist first, then the wheel from it: what ships is what the package declares, never stale
        # leftovers of an in-tree build.
        run("uv", "build", "--quiet", "--out-dir", wheels, str(ROOT), quiet=True)
        wheel = next(Path(wheels).glob("econoclast-*.whl"))
        run("uv", "pip", "install", "--python", str(py), "--no-progress", "--link-mode", "copy", str(wheel),
            *EXTRA_PACKAGES, env=env)

    step("prune")
    relocate_text(pyhome, str(base))  # uv records its own install path in sysconfig and pkg-config
    prune(pyhome)

    step("launcher, command line, Info.plist, icon")
    build_launcher(pyhome, macos / APP_NAME)
    cli = res / "bin" / "econoclast"
    cli.parent.mkdir()
    cli.write_text(CLI_SHIM, encoding="utf-8")
    cli.chmod(0o755)
    minos = min_macos(app)
    run(str(py), "-c", ICON_AND_PLIST, str(contents), minos, env=env)
    plist = plistlib.loads((contents / "Info.plist").read_bytes())
    if plist.get("CFBundleShortVersionString") != version:
        sys.exit(f"bundled econoclast reports {plist.get('CFBundleShortVersionString')}, the repo says {version}")
    (contents / "PkgInfo").write_text("APPL????", encoding="ascii")

    step("bytecode")
    # Unchecked-hash .pyc: the bundle never changes after signing, so Python never needs to
    # compare sources (and the launcher forbids writing bytecode into the signed bundle).
    # Source paths recorded in the .pyc point at the installed location, not this build folder.
    proc = subprocess.run([str(py), "-m", "compileall", "-q", "-j", "0", "--invalidation-mode", "unchecked-hash",
                           "-s", str(pyhome), "-p", INSTALLED_PYTHON,
                           str(pyhome / "lib")], env=env, capture_output=True, text=True)
    bad = [ln for ln in proc.stdout.splitlines() if ln.startswith("***")]
    if bad:
        print(f"  {len(bad)} file(s) not compilable (templates or test data), left as source")

    step("smoke test")
    out = run(str(py), "-c", SMOKE, str(ROOT / "src" / "econoclast" / "app" / "web"), env=env, capture=True)
    print("  " + out.strip().replace("\n", "\n  "))
    smoke_launcher(macos / APP_NAME)
    print(f"  the launcher starts the app's command line; minimum macOS {minos}")
    leaks = find_leaks(app, (str(ROOT), str(base), str(Path.home()) + "/"))
    if leaks:
        sys.exit("build-machine paths inside the bundle:\n  " + "\n  ".join(leaks[:20]))

    step("sign (ad hoc)")
    sign(app)
    return app


def build_launcher(pyhome: Path, out: Path) -> None:
    """Compile launcher.c against the bundled libpython and point it (and the library) at the bundle."""
    lib = pyhome / "lib" / f"libpython{PY_VERSION}.dylib"
    inside = f"@executable_path/../Resources/python/lib/{lib.name}"
    run("install_name_tool", "-id", inside, str(lib), quiet=True)  # uv records its own absolute path
    run("clang", "-O2", "-Wall", "-mmacosx-version-min=11.0", "-arch", machine(),
        f"-I{pyhome / 'include' / f'python{PY_VERSION}'}", str(HERE / "launcher.c"), str(lib), "-o", str(out))
    linked = run("otool", "-L", str(out), capture=True)
    if inside not in linked:
        sys.exit(f"the launcher does not load libpython from the bundle:\n{linked}")


def relocate_text(pyhome: Path, old: str) -> None:
    """Rewrite the build machine's interpreter path in the text files that record it."""
    for p in pyhome.rglob("*"):
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 4_000_000:
            continue
        data = p.read_bytes()
        if old.encode() in data and b"\0" not in data[:8192]:
            p.write_bytes(data.replace(old.encode(), INSTALLED_PYTHON.encode()))


def min_macos(app: Path) -> str:
    """The newest LC_BUILD_VERSION minos among the bundle's binaries for this architecture."""
    best = (11, 0)
    for p in app.rglob("*"):
        if not (p.is_file() and not p.is_symlink() and is_macho(p)):
            continue
        out = subprocess.run(["otool", "-arch", machine(), "-l", str(p)], capture_output=True, text=True).stdout
        cmd = ""
        for line in out.splitlines():
            key, _, value = line.strip().partition(" ")
            if key == "cmd":
                cmd = value
            elif (cmd, key) in (("LC_BUILD_VERSION", "minos"), ("LC_VERSION_MIN_MACOSX", "version")):
                major, _, minor = value.partition(".")
                best = max(best, (int(major), int(minor.split(".")[0] or 0)))
    return f"{best[0]}.{best[1]}"


def smoke_launcher(exe: Path) -> None:
    """Start the real launcher (embedded interpreter, bundle paths) on `app --help`, which exits."""
    with tempfile.TemporaryDirectory(prefix="econoclast-home-") as home:
        env = {"HOME": home, "PATH": "/usr/bin:/bin"}
        proc = subprocess.run([str(exe), "--help"], env=env, capture_output=True, text=True, timeout=120)
        log = Path(home, ".econoclast", "app.log")
        out = proc.stdout + proc.stderr + (log.read_text(errors="replace") if log.exists() else "")
        if proc.returncode != 0 or "Usage:" not in out:
            sys.exit(f"the launcher failed ({proc.returncode}):\n{out[-2000:]}")


def find_leaks(app: Path, needles: tuple[str, ...]) -> list[str]:
    hits = []
    for p in app.rglob("*"):
        if p.is_file() and not p.is_symlink():
            data = p.read_bytes()
            for n in needles:
                if n.encode() in data:
                    hits.append(f"{p.relative_to(app)}: {n}")
                    break
    return hits


def standalone_python() -> Path:
    """A python-build-standalone CPython (relocatable), installed by uv if needed."""
    find = ["uv", "python", "find", "--managed-python", "--system", PY_VERSION]  # never a venv
    proc = subprocess.run(find, capture_output=True, text=True)
    if proc.returncode != 0:
        run("uv", "python", "install", PY_VERSION)
        proc = subprocess.run(find, capture_output=True, text=True, check=True)
    exe = Path(proc.stdout.strip()).resolve()
    base = exe.parents[1]
    if not (base / "lib" / f"python{PY_VERSION}" / "os.py").exists():
        sys.exit(f"{exe} is not a standalone CPython {PY_VERSION}")
    return base


def prune(pyhome: Path) -> None:
    lib = pyhome / "lib" / f"python{PY_VERSION}"
    for rel in STDLIB_DROP:
        shutil.rmtree(lib / rel, ignore_errors=True)
    site = lib / "site-packages"
    shutil.rmtree(site / "PyObjCTest", ignore_errors=True)  # PyObjC's own test suite
    for d in sorted(site.rglob("tests"), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
    for d in list(pyhome.rglob("__pycache__")):
        shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(pyhome / "share", ignore_errors=True)
    for rel in ("lib/libtcl9.0.dylib", "lib/libtcl9tk9.0.dylib"):
        (pyhome / rel).unlink(missing_ok=True)
    for pattern in ("lib/tcl9*", "lib/tk9*", "lib/itcl*", "lib/thread*"):
        for d in pyhome.glob(pattern):
            shutil.rmtree(d, ignore_errors=True)
    for d in list(site.glob("pip")) + list(site.glob("pip-*.dist-info")) + list(site.rglob("*.dSYM")):
        shutil.rmtree(d, ignore_errors=True)  # venvs get pip from ensurepip; debug symbols are dead weight
    for f in site.glob("*.dist-info/direct_url.json"):
        f.unlink()  # records the build machine's checkout path
    # Console scripts carry absolute shebangs to the build folder: keep only the interpreter.
    for f in (pyhome / "bin").iterdir():
        if not re.fullmatch(r"python[0-9.]*", f.name):
            f.unlink()


def sign(app: Path) -> None:
    machos = [p for p in app.rglob("*") if p.is_file() and not p.is_symlink() and is_macho(p)]
    arch = machine()
    for p in machos:  # universal wheels carry a slice this Mac never runs
        if p.read_bytes()[:4] in (b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"):
            archs = run("lipo", "-archs", str(p), capture=True).split()
            if arch in archs and len(archs) > 1:
                run("lipo", "-thin", arch, str(p), "-output", str(p), quiet=True)
    main = app / "Contents" / "MacOS" / APP_NAME
    inner = [str(p) for p in machos if p != main]
    for i in range(0, len(inner), 200):
        run("codesign", "--force", "--sign", "-", "--timestamp=none", *inner[i:i + 200], quiet=True)
    run("codesign", "--force", "--sign", "-", "--timestamp=none", str(app))
    run("codesign", "--verify", "--deep", "--strict", str(app))
    print(f"  signed {len(machos)} binaries and the bundle")


def is_macho(p: Path) -> bool:
    try:
        with open(p, "rb") as fh:
            return fh.read(4) in MACHO_MAGIC
    except OSError:
        return False


# ---------------------------------------------------------------- the image
def build_dmg(app: Path) -> Path:
    version = read_version()
    dmg = DIST / f"{APP_NAME}-{version}-{machine()}.dmg"
    if dmg.exists():
        dmg.unlink()
    with tempfile.TemporaryDirectory(prefix="econoclast-dmg-") as tmp:
        tmp = Path(tmp)
        step("background")
        py = app / "Contents" / "Resources" / "python" / "bin" / f"python{PY_VERSION}"
        run(str(py), str(HERE / "dmg_background.py"), str(tmp), env=bundled_env())
        run("tiffutil", "-cathidpicheck", str(tmp / "background.png"), str(tmp / "background@2x.png"), "-out",
            str(tmp / "background.tiff"), quiet=True)
        step("disk image")
        defines = {"app": str(app), "background": str(tmp / "background.tiff"),
                   "icon": str(app / "Contents" / "Resources" / f"{APP_NAME}.icns")}
        run("uvx", "--quiet", "dmgbuild", "-s", str(HERE / "dmg_settings.py"),
            *[x for k, v in defines.items() for x in ("-D", f"{k}={v}")], f"{APP_NAME} {version}", str(dmg))
    run("hdiutil", "verify", str(dmg), quiet=True)
    with tempfile.TemporaryDirectory(prefix="econoclast-mnt-") as mnt:  # the copy inside must still verify
        run("hdiutil", "attach", str(dmg), "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", mnt, quiet=True)
        try:
            run("codesign", "--verify", "--deep", "--strict", str(Path(mnt) / f"{APP_NAME}.app"), quiet=True)
        finally:
            run("hdiutil", "detach", mnt, "-quiet", quiet=True)
    return dmg


# ---------------------------------------------------------------- installing
def install(dmg: Path, *, keep_dev_launcher: bool = False) -> Path:
    target = Path("/Applications") / f"{APP_NAME}.app"
    with tempfile.TemporaryDirectory(prefix="econoclast-mnt-") as mnt:
        run("hdiutil", "attach", str(dmg), "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", mnt, quiet=True)
        try:
            src = Path(mnt) / f"{APP_NAME}.app"
            if target.exists():
                ours = plistlib.loads((target / "Contents" / "Info.plist").read_bytes()).get("CFBundleIdentifier")
                if ours != bundle_id(src):
                    sys.exit(f"{target} exists and is not Econoclast ({ours}); not touching it.")
                quit_running(target)
                shutil.rmtree(target)
            run("ditto", str(src), str(target))
        finally:
            run("hdiutil", "detach", mnt, "-quiet", quiet=True)
    subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(target)], capture_output=True)
    run("codesign", "--verify", "--deep", "--strict", str(target))
    lsregister = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/"
                  "Support/lsregister")
    if os.path.exists(lsregister):
        subprocess.run([lsregister, "-f", str(target)], capture_output=True)
    dev = Path.home() / "Applications" / f"{APP_NAME}.app"
    launcher = dev / "Contents" / "MacOS" / APP_NAME
    if not keep_dev_launcher and launcher.exists() and launcher.read_bytes()[:2] == b"#!":
        trash = Path.home() / ".Trash" / f"{APP_NAME} (dev launcher) {time.strftime('%Y%m%d-%H%M%S')}.app"
        shutil.move(str(dev), str(trash))
        print(f"  moved the thin dev launcher {dev} to the Trash so Launchpad shows one Econoclast")
    return target


def quit_running(target: Path) -> None:
    """Close the installed app's window process before replacing it; refuse while a hunt runs from it."""
    ps = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    launcher = str(target / "Contents" / "MacOS" / APP_NAME)
    python = str(target / "Contents" / "Resources" / "python" / "bin") + "/"
    window, hunts = [], []
    for line in ps.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if cmd == launcher or cmd.startswith(launcher + " "):
            window.append(int(pid))
        elif cmd.startswith(python) and " -m econoclast " in f"{cmd} ":
            (window if " -m econoclast app" in cmd else hunts).append(int(pid))
    if hunts:
        sys.exit(f"{len(hunts)} Econoclast process(es) still run from {target} (a hunt?): let them finish or "
                 "stop them, then install again.")
    for pid in window:
        os.kill(pid, 15)
    deadline = time.time() + 10
    while window and time.time() < deadline:
        window = [p for p in window if subprocess.run(["kill", "-0", str(p)], capture_output=True).returncode == 0]
        time.sleep(0.2)


# ---------------------------------------------------------------- helpers
CLI_SHIM = """#!/bin/sh
# Econoclast's command line, running on the Python inside Econoclast.app. To use it from a terminal:
#   ln -s /Applications/Econoclast.app/Contents/Resources/bin/econoclast /usr/local/bin/econoclast
src="$0"
while [ -L "$src" ]; do
  dir="$(cd "$(dirname "$src")" && pwd)"; src="$(readlink "$src")"
  case "$src" in /*) ;; *) src="$dir/$src" ;; esac
done
here="$(cd "$(dirname "$src")" && pwd)"
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 ECONOCLAST_BUNDLE=1
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV
exec "$here/../python/bin/python3.12" -s -B -P -m econoclast "$@"
"""

ICON_AND_PLIST = """
import plistlib, sys
from pathlib import Path
from econoclast.app import ICON
from econoclast.app.macos import info_plist, make_icns
contents = Path(sys.argv[1])
make_icns(Path(ICON), contents / "Resources" / "Econoclast.icns")
plist = info_plist(icon=True, LSMinimumSystemVersion=sys.argv[2])
(contents / "Info.plist").write_bytes(plistlib.dumps(plist))
"""

SMOKE = """
import sys, importlib
mods = ["econoclast.cli", "econoclast.app.api", "econoclast.arsenal.server", "econoclast.sicarius",
        "econoclast.viae", "econoclast.tesserae.pdf", "webview", "objc", "AppKit", "WebKit", "mcp",
        "pandas", "numpy", "scipy", "statsmodels.api", "matplotlib", "openpyxl", "PIL"]
for m in mods:
    importlib.import_module(m)
from pathlib import Path
from econoclast.app.api import WEB
from econoclast.version import __version__
def files(d):
    return {str(p.relative_to(d)) for p in Path(d).rglob("*") if p.is_file() and p.name != ".DS_Store"}
missing = files(sys.argv[1]) - files(WEB)
assert not missing, f"web files missing from the bundle: {sorted(missing)[:10]}"
print(f"econoclast {__version__} on Python {sys.version.split()[0]}: {len(mods)} modules import, "
      f"all {len(files(WEB))} web files present")
"""


def bundled_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV")}
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", UV_PYTHON_DOWNLOADS="automatic")
    return env


def read_version() -> str:
    text = (ROOT / "src" / "econoclast" / "version.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', text).group(1)


def bundle_id(app: Path) -> str:
    return plistlib.loads((app / "Contents" / "Info.plist").read_bytes())["CFBundleIdentifier"]


def machine() -> str:
    return os.uname().machine


def du(p: Path) -> str:
    return subprocess.run(["du", "-sh", str(p)], capture_output=True, text=True).stdout.split()[0]


def step(name: str) -> None:
    print(f"· {name}", flush=True)


def run(*cmd: str, env: dict | None = None, capture: bool = False, quiet: bool = False) -> str:
    proc = subprocess.run(list(cmd), env=env, capture_output=capture or quiet, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-2000:] if (capture or quiet) else ""
        sys.exit(f"failed ({proc.returncode}): {' '.join(cmd)[:300]}\n{detail}")
    return proc.stdout or ""


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except subprocess.CalledProcessError as exc:
        sys.exit(json.dumps({"failed": exc.cmd, "code": exc.returncode}))
