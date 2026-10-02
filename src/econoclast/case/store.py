"""A case on disk: the workspace one hunt lives in, and its append-only event log.

Three processes write here at once: the runner (parsing the agent's stream), the
arsenal MCP server (spawned by the agent, recording wounds and stations), and the forum
(answering the traveller's uploads). They coordinate only through files: each event is
one JSON line appended under an exclusive lock, and everyone else tails the log.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from econoclast.case.models import Parry, Wound

try:
    import fcntl
except ImportError:  # Windows: appends of one short line are atomic enough there
    fcntl = None  # type: ignore[assignment]

SUBDIRS = ("paper", "data", "code", "out", "offerings")


def home() -> Path:
    """Econoclast's home: cases, the shared quant workshop, settings."""
    root = Path(os.environ.get("ECONOCLAST_HOME") or Path.home() / ".econoclast")
    root.mkdir(parents=True, exist_ok=True)
    return root


def cases_root() -> Path:
    p = home() / "cases"
    p.mkdir(parents=True, exist_ok=True)
    return p


def new_case_id(hint: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", hint.lower()).strip("-")[:24]
    tail = secrets.token_hex(2)
    return f"{stamp}-{slug}-{tail}" if slug else f"{stamp}-{tail}"


class Case:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    # ------------------------------------------------------------ creation
    @classmethod
    def create(cls, *, paper: str, data: str = "", claim: str = "", lang: str = "en",
               backend: str = "auto", depth: str = "thorough", note: str = "") -> Case:
        hint = Path(paper).stem if paper and not paper.startswith("http") else ""
        if not hint and paper:
            hint = re.sub(r"^https?://(www\.)?", "", paper).split("/")[0]
        case = cls(cases_root() / new_case_id(hint))
        case.root.mkdir(parents=True, exist_ok=False)
        for d in SUBDIRS:
            (case.root / d).mkdir()
        case.write_meta({
            "id": case.id,
            "created": time.time(),
            "paper_input": paper,
            "data_input": data,
            "claim": claim,
            "lang": lang if lang in ("en", "zh") else "en",
            "backend": backend,
            "depth": depth,
            "note": note,
            "status": "new",
        })
        return case

    @classmethod
    def load(cls, case_id: str) -> Case:
        root = cases_root() / case_id
        if not (root / "case.json").exists():
            raise FileNotFoundError(case_id)
        return cls(root)

    @property
    def id(self) -> str:
        return self.root.name

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    # ---------------------------------------------------------------- meta
    def meta(self) -> dict[str, Any]:
        try:
            return json.loads(self.path("case.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"id": self.id}

    def write_meta(self, meta: dict[str, Any]) -> None:
        tmp = self.path("case.json.tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path("case.json"))

    def update_meta(self, **changes: Any) -> dict[str, Any]:
        with _locked(self.path(".meta.lock")):
            meta = self.meta()
            meta.update(changes)
            self.write_meta(meta)
            return meta

    # -------------------------------------------------------------- events
    def emit(self, kind: str, /, **data: Any) -> dict[str, Any]:
        data.pop("kind", None)  # the event's kind is the first argument, never a payload field
        data.pop("ts", None)
        event = {"kind": kind, "ts": round(time.time(), 3), **data}
        line = json.dumps(event, ensure_ascii=False, default=str) + "\n"
        with open(self.path("events.jsonl"), "a", encoding="utf-8") as fh:
            _flock(fh, True)
            try:
                fh.write(line)
                fh.flush()
            finally:
                _flock(fh, False)
        return event

    def events(self, start: int = 0) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            with open(self.path("events.jsonl"), encoding="utf-8") as fh:
                for i, line in enumerate(fh):
                    if i < start or not line.strip():
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ev["seq"] = i
                    out.append(ev)
        except FileNotFoundError:
            pass
        return out

    # -------------------------------------------------------- derived views
    def wounds(self) -> list[Wound]:
        return [Wound.from_dict(e["wound"]) for e in self.events() if e.get("kind") == "wound"]

    def parries(self) -> list[Parry]:
        return [Parry(**e["parry"]) for e in self.events() if e.get("kind") == "parry"]

    def target(self) -> dict[str, Any]:
        """The decree under attack, as last reported by the Sicarius."""
        tgt: dict[str, Any] = {}
        for e in self.events():
            if e.get("kind") == "intel" and e.get("about") in ("paper", "target"):
                tgt.update({k: v for k, v in e.items() if k not in ("kind", "ts", "seq", "about")})
        return tgt

    def verdict(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.path("verdict.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def summary(self) -> dict[str, Any]:
        meta = self.meta()
        v = self.verdict() or {}
        return {
            "id": self.id,
            "created": meta.get("created"),
            "status": meta.get("status"),
            "title": meta.get("title") or meta.get("paper_input"),
            "paper_input": meta.get("paper_input"),
            "lang": meta.get("lang"),
            "backend": meta.get("backend_used") or meta.get("backend"),
            "score": (v.get("fragility") or {}).get("score"),
            "band": (v.get("fragility") or {}).get("band"),
        }

    # ------------------------------------------------------------ offerings
    def offering_path(self, plea_id: str) -> Path:
        return self.path("offerings", f"{plea_id}.json")

    def answer_plea(self, plea_id: str, *, files: list[str] | None = None, url: str = "",
                    note: str = "", declined: bool = False) -> dict[str, Any]:
        answer = {"plea_id": plea_id, "files": files or [], "url": url, "note": note,
                  "declined": declined, "ts": time.time()}
        tmp = self.offering_path(plea_id).with_suffix(".tmp")
        tmp.write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.offering_path(plea_id))
        self.emit("plea.answered", plea_id=plea_id, files=[Path(f).name for f in answer["files"]],
                  url=url, declined=declined)
        return answer


def list_cases(limit: int = 50) -> list[dict[str, Any]]:
    roots = sorted((p for p in cases_root().iterdir() if (p / "case.json").exists()),
                   key=lambda p: p.name, reverse=True)
    return [Case(p).summary() for p in roots[:limit]]


class _locked:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fh = None

    def __enter__(self):
        self.fh = open(self.path, "a")  # noqa: SIM115
        _flock(self.fh, True)
        return self.fh

    def __exit__(self, *exc):
        _flock(self.fh, False)
        self.fh.close()


def _flock(fh, exclusive: bool) -> None:  # noqa: ANN001
    if fcntl is not None:
        fcntl.flock(fh, fcntl.LOCK_EX if exclusive else fcntl.LOCK_UN)
