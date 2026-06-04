"""Plain-language intake, so a non-technical user can be served in one message.

The idea is that someone says "check this paper for me" and the agent works out
what it already has and asks only for what it still needs, in plain words. No
jargon, no config files. This turns a free-text request into a structured
understanding plus a short list of questions a human can answer.
"""

from __future__ import annotations

import re

from econoclast.llm.base import Message
from econoclast.logging import get_logger

log = get_logger("agent.intake")

_URL = re.compile(r"https?://\S+")
_PATH = re.compile(r"[\w./\\~-]+\.(?:pdf|tex|txt|md|csv|dta|xlsx|parquet)", re.IGNORECASE)
_DATA_EXT = (".csv", ".dta", ".xlsx", ".parquet", ".zip", ".tsv")

_SYSTEM = (
    "You are the intake for a paper-checking tool used by economists who are not technical. From the "
    "user's message, extract what they want checked. Keep it factual and short."
)
_CONTRACT = (
    'Return ONLY JSON: {"paper": str (a URL, a file path, or a title; "" if none given), '
    '"paper_kind": "url" | "path" | "title" | "none", "data": str (a dataset path/URL the user gave, '
    'or ""), "claim": str (the specific result they want stress-tested, or "")}'
)


def understand_request(text: str, router=None) -> dict:  # noqa: ANN001
    """Parse a free-text request into {paper, paper_kind, data, claim}."""
    if router is not None and router.is_live():
        try:
            resp = router.complete("extractor",
                                   [Message(role="system", content=_SYSTEM + "\n\n" + _CONTRACT),
                                    Message(role="user", content=text[:4000])],
                                   response_format="json")
            data = resp.json()
            if isinstance(data, dict) and data.get("paper_kind"):
                return _clean(data)
        except Exception as exc:  # noqa: BLE001
            log.warning("intake LLM parse failed, using heuristics: %s", exc)
    return _heuristic(text)


def _heuristic(text: str) -> dict:
    paper = data = ""
    kind = "none"
    for u in _URL.findall(text):
        if u.lower().endswith(_DATA_EXT):
            data = data or u
        elif not paper:
            paper, kind = u, "url"
    for m in _PATH.finditer(text):
        tok = m.group(0)
        if tok.lower().endswith(_DATA_EXT):
            data = data or tok
        elif not paper:
            paper, kind = tok, "path"
    return {"paper": paper, "paper_kind": kind, "data": data, "claim": ""}


def _clean(d: dict) -> dict:
    return {
        "paper": str(d.get("paper", "")).strip(),
        "paper_kind": d.get("paper_kind", "none"),
        "data": str(d.get("data", "")).strip(),
        "claim": str(d.get("claim", "")).strip(),
    }


def needed_questions(state: dict) -> list[dict]:
    """The short list of plain-language questions still worth asking."""
    qs: list[dict] = []
    if not state.get("paper"):
        qs.append({
            "ask": "Which paper should I check? Paste a link (arXiv, a journal page, or a PDF), "
                   "a file on your computer, or just the exact title and I will find it.",
            "required": True,
        })
        return qs  # nothing else matters until we have the paper
    if not state.get("data"):
        qs.append({
            "ask": "Do you already have the paper's dataset on your computer? If yes, tell me where. "
                   "If not, I will try to download the data the paper points to.",
            "required": False,
        })
    if not state.get("claim"):
        qs.append({
            "ask": "Is there one result you most want me to stress-test? If you are not sure, I will "
                   "check the paper's main finding.",
            "required": False,
        })
    return qs


def build_intake(request: str, settings=None) -> dict:  # noqa: ANN001
    """Top-level: understand the request and return what to ask, if anything."""
    router = None
    if settings is not None:
        from econoclast.llm.router import ModelRouter

        router = ModelRouter(settings)
    state = understand_request(request, router)
    questions = needed_questions(state)
    return {
        "understood": state,
        "questions": questions,
        "ready": bool(state.get("paper")),
        "next": "verify" if state.get("paper") else "ask_user",
    }
