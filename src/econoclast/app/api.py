"""The bridge between the window and the engine.

The app's window calls these methods directly (``window.pywebview.api.<name>``); there is
no HTTP API. Every return value is plain JSON. The same object also backs the developer
preview server (``econoclast app --browser``) so the UI can be inspected in a browser.
"""

from __future__ import annotations

import base64
import json
import locale
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from econoclast import world
from econoclast.case.store import Case, home, list_cases
from econoclast.config import Settings
from econoclast.log import get_logger
from econoclast.version import __version__

log = get_logger("app")

WEB = Path(__file__).parent / "web"
_MAX_EVENTS = 600


class Api:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings.load()
        self._window = None  # set by the window launcher; underscore keeps pywebview from exposing it

    # -------------------------------------------------------------- boot
    def hello(self) -> dict[str, Any]:
        from econoclast.sicarius import reap_orphans

        reap_orphans()
        return {
            "version": __version__,
            "world": world.as_dict(),
            "doctor": self.doctor(),
            "lang": self._default_lang(),
            "prefs": self._prefs(),
            "cases": list_cases(40),
            "native": self._window is not None,
        }

    def doctor(self) -> dict[str, Any]:
        from econoclast import fabrica

        s = self._settings
        claude, codex = s.claude_path(), s.codex_path()
        picked = s.pick_backend()
        return {
            "claude": claude,
            "codex": codex,
            "backend": picked[0] if picked else None,
            "preference": s.backend,
            "permissions": s.permissions,
            "browser_mcp": bool(s.browser_mcp and shutil.which("npx")),
            "fabrica": fabrica.status(),
            "home": str(home()),
        }

    def _default_lang(self) -> str:
        if self._settings.lang in ("en", "zh"):
            return self._settings.lang
        loc = (os.environ.get("LANG") or "").lower()
        if not loc:
            try:
                loc = (locale.getlocale()[0] or "").lower()
            except ValueError:
                loc = ""
        if not loc and sys.platform == "darwin":
            try:
                out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True,
                                     text=True, timeout=3).stdout
                loc = out.lower()
            except (OSError, subprocess.TimeoutExpired):
                loc = ""
        return "zh" if "zh" in loc else "en"

    # ------------------------------------------------------------ prefs
    def _prefs_path(self) -> Path:
        return home() / "prefs.json"

    def _prefs(self) -> dict[str, Any]:
        try:
            return json.loads(self._prefs_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def set_pref(self, key: str, value: Any) -> dict[str, Any]:
        prefs = self._prefs()
        prefs[str(key)] = value
        self._prefs_path().write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")
        return prefs

    # ------------------------------------------------------------ cases
    def list_cases(self) -> list[dict[str, Any]]:
        return list_cases(60)

    def open_case(self, case_id: str) -> dict[str, Any]:
        from econoclast.case.tabula import tabula_data

        case = Case.load(case_id)
        meta = case.meta()
        data = tabula_data(case)
        data.update({"meta": meta, "status": meta.get("status"), "n_events": len(case.events())})
        return data

    def events(self, case_id: str, since: int = 0) -> dict[str, Any]:
        case = Case.load(case_id)
        evs = case.events(int(since))[:_MAX_EVENTS]
        meta = case.meta()
        return {"events": evs, "status": meta.get("status"), "waiting_plea": meta.get("waiting_plea")}

    def begin(self, params: dict[str, Any]) -> dict[str, Any]:
        """Start a hunt. params: paper (URL/DOI/title/path), paper_file, paper_upload {name,b64},
        data_file, data_upload, claim, lang, backend, depth."""
        from econoclast.sicarius import NoAgent, launch_detached

        p = params or {}
        paper = str(p.get("paper") or "").strip()
        if not paper and not p.get("paper_file") and not p.get("paper_upload"):
            return {"ok": False, "error": "no_paper"}
        if self._settings.pick_backend(p.get("backend")) is None:
            return {"ok": False, "error": "no_agent"}
        label = paper or Path(str(p.get("paper_file") or (p.get("paper_upload") or {}).get("name", ""))).name
        case = Case.create(paper=label, claim=str(p.get("claim") or "").strip(),
                           lang=str(p.get("lang") or self._default_lang()),
                           backend=str(p.get("backend") or "auto"), depth=str(p.get("depth") or "thorough"))
        local_paper = self._take(case, "paper", p.get("paper_file"), p.get("paper_upload"))
        local_data = self._take(case, "offerings", p.get("data_file"), p.get("data_upload"))
        updates: dict[str, Any] = {}
        if local_paper:
            updates["paper_input"] = f"{local_paper} (a local file the traveller provided" + \
                                     (f"; they also said: {paper}" if paper else "") + ")"
        if local_data:
            updates["data_input"] = local_data
        if updates:
            case.update_meta(**updates)
        try:
            launch_detached(case)
        except NoAgent:
            return {"ok": False, "error": "no_agent"}
        return {"ok": True, "case_id": case.id}

    def _take(self, case: Case, sub: str, path: Any, upload: Any) -> str:
        """Copy a picked file or an uploaded blob into the case; return its case-relative path."""
        dest_dir = case.path(sub)
        if path:
            src = Path(str(path)).expanduser()
            if src.is_file():
                dst = dest_dir / _safe(src.name)
                shutil.copy2(src, dst)
                return str(dst.relative_to(case.root))
            if src.is_dir():
                dst = dest_dir / _safe(src.name)
                shutil.copytree(src, dst, dirs_exist_ok=True)
                return str(dst.relative_to(case.root))
        if isinstance(upload, dict) and upload.get("b64"):
            dst = dest_dir / _safe(str(upload.get("name") or "upload.bin"))
            dst.write_bytes(base64.b64decode(upload["b64"].split(",")[-1]))
            return str(dst.relative_to(case.root))
        return ""

    def abort(self, case_id: str) -> dict[str, Any]:
        from econoclast.sicarius import stop

        stop(Case.load(case_id))
        return {"ok": True}

    def answer_plea(self, case_id: str, plea_id: str, answer: dict[str, Any]) -> dict[str, Any]:
        case = Case.load(case_id)
        a = answer or {}
        files = []
        for path in a.get("files") or []:
            rel = self._take(case, "offerings", path, None)
            if rel:
                files.append(str(case.root / rel))
        for up in a.get("uploads") or []:
            rel = self._take(case, "offerings", None, up)
            if rel:
                files.append(str(case.root / rel))
        case.answer_plea(plea_id, files=files, url=str(a.get("url") or ""), note=str(a.get("note") or ""),
                         declined=bool(a.get("declined")))
        return {"ok": True, "files": [Path(f).name for f in files]}

    def forget(self, case_id: str) -> dict[str, Any]:
        """Delete a finished case folder (asked for explicitly in the archive)."""
        case = Case.load(case_id)
        if case.meta().get("status") in ("running", "starting"):
            return {"ok": False, "error": "running"}
        trash = home() / ".trash"
        trash.mkdir(exist_ok=True)
        shutil.move(str(case.root), str(trash / case.id))
        return {"ok": True}

    # ------------------------------------------------------------ native
    def pick_file(self, kind: str = "paper") -> str | None:
        if self._window is None:
            return None
        import webview

        types = {
            "paper": ("Papers (*.pdf;*.tex;*.txt;*.md;*.html)", "All files (*.*)"),
            "data": ("Data (*.csv;*.dta;*.xlsx;*.xls;*.parquet;*.tsv;*.zip;*.sav)", "All files (*.*)"),
        }.get(kind, ("All files (*.*)",))
        dialog = getattr(webview, "FileDialog", None)
        mode = dialog.OPEN if dialog else webview.OPEN_DIALOG
        res = self._window.create_file_dialog(mode, allow_multiple=False, file_types=types)
        return str(res[0]) if res else None

    def reveal(self, case_id: str, rel: str = "") -> dict[str, Any]:
        case = Case.load(case_id)
        target = (case.root / rel) if rel else case.root
        if not str(target.resolve()).startswith(str(case.root.resolve())):
            return {"ok": False}
        _open(target, reveal=bool(rel))
        return {"ok": True}

    def open_external(self, case_id: str, rel: str) -> dict[str, Any]:
        case = Case.load(case_id)
        target = (case.root / rel).resolve()
        if not str(target).startswith(str(case.root.resolve())) or not target.exists():
            return {"ok": False}
        _open(target)
        return {"ok": True}

    def read_artifact(self, case_id: str, rel: str) -> dict[str, Any]:
        case = Case.load(case_id)
        target = (case.root / rel).resolve()
        if not str(target).startswith(str(case.root.resolve())):
            return {"ok": False}
        if not target.is_file():
            packed = any(rel == f.get("path") for f in self._vault_files(case))
            return {"ok": False, "packed": packed}
        if target.stat().st_size > 8 * 1024 * 1024:
            return {"ok": False, "error": "too large"}
        data = target.read_bytes()
        if target.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".svg"):
            mime = {"svg": "image/svg+xml", "jpg": "image/jpeg"}.get(target.suffix[1:].lower(),
                                                                      f"image/{target.suffix[1:].lower()}")
            return {"ok": True, "data_url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}
        return {"ok": True, "text": data.decode("utf-8", errors="replace")[:200000]}

    def _vault_files(self, case: Case) -> list[dict]:
        try:
            return json.loads(case.path("vault.json").read_text()).get("files", [])
        except (OSError, json.JSONDecodeError):
            return []

    def unpack(self, case_id: str) -> dict[str, Any]:
        from econoclast.case.vault import unpack

        return {"ok": True, "files": unpack(Case.load(case_id))}

    def demo(self, lang: str = "en") -> dict[str, Any]:
        """The recorded demonstration hunt, in the traveller's language when one was recorded."""
        for name in (f"card-krueger.{lang}.json", "card-krueger.en.json", "card-krueger.zh.json"):
            path = WEB / "demo" / name
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
        return {"events": []}


def _safe(name: str) -> str:
    name = re.sub(r"[^\w.\- ]+", "_", name).strip() or "file"
    return name[:120]


def _open(path: Path, reveal: bool = False) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)] if reveal else ["open", str(path)])
    elif os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(path.parent if reveal else path)])
