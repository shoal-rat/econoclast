"""Shared test fixtures.

Econoclast has no offline mode in production: it runs on Claude Code or Codex.
For tests we inject a tiny in-process ``FakeBackend`` that mimics the backend's
``complete(role, ...)`` contract with canned responses, so the pipeline runs
without spawning a real CLI.
"""

from __future__ import annotations

from pathlib import Path

from econoclast.llm.base import LLMResponse


def _write_all(work_dir, items) -> list[Path]:  # noqa: ANN001
    out: list[Path] = []
    for rel, content in items or []:
        p = Path(work_dir) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode())
        out.append(p)
    return out


class FakeBackend:
    """A stand-in for econoclast.llm.backend.Backend used in tests."""

    label = "fake"

    def __init__(self, *, responses: dict | None = None, default: str = "[]",
                 downloads: list | None = None) -> None:
        self.responses = responses or {}
        self.default = default
        self.downloads = downloads or []  # (relpath, content) written by fetch_into
        self.calls: list[str] = []
        self.fetch_orders: list[str] = []

    def complete(self, role, messages, *, response_format=None,  # noqa: ANN001
                 temperature=None, max_tokens=4096, stop=None) -> LLMResponse:
        self.calls.append(role)
        r = self.responses.get(role, self._default_for(role))
        text = r(messages) if callable(r) else r
        return LLMResponse(text=text, model="fake", provider="fake")

    def fetch_into(self, work_dir, *, url="", what="", timeout=300.0):  # noqa: ANN001
        self.fetch_orders.append(f"{url}|{what}")
        return _write_all(work_dir, self.downloads)

    def _default_for(self, role: str) -> str:
        if role == "referee":
            return '{"headline":"Fake verdict","assessment":"a","what_would_change_my_mind":"b"}'
        if role == "extractor":
            return "{}"
        return self.default

    def summary(self) -> dict:
        return {"backend": self.label, "model": "fake", "calls": len(self.calls)}


class FakeProvider:
    """A stand-in LLMProvider whose ``run_task`` writes canned files into work_dir."""

    name = "fake"

    def __init__(self, *, writes: list | None = None, text: str = "done") -> None:
        self.writes = writes or []
        self.text = text
        self.tasks: list[str] = []

    def complete(self, messages, *, model="", **kw):  # noqa: ANN001
        return LLMResponse(text=self.text, model="fake", provider="fake")

    def run_task(self, prompt, *, work_dir, timeout=300.0, **kw) -> str:  # noqa: ANN001
        self.tasks.append(prompt)
        _write_all(work_dir, self.writes)
        return self.text
