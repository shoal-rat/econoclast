"""Plain-language intake, so a non-technical user can be served in one message.

The idea is that someone says "check this paper for me" and the agent works out
what it already has and asks only for what it still needs, in plain words. No
jargon, no config files. This turns a free-text request into a structured
understanding plus a short list of questions a human can answer.
"""

from __future__ import annotations

from econoclast.llm.base import Message
from econoclast.logging import get_logger

log = get_logger("agent.intake")

_SYSTEM = (
    "You are the intake for a paper-checking tool used by economists who are not technical. From the "
    "user's message, extract what they want checked. Keep it factual and short."
)
_CONTRACT = (
    'Return ONLY JSON: {"paper": str (a URL, a file path, or a title; "" if none given), '
    '"paper_kind": "url" | "path" | "title" | "none", "data": str (a dataset path/URL the user gave, '
    'or ""), "claim": str (the specific result they want stress-tested, or "")}'
)


def understand_request(text: str, backend) -> dict:  # noqa: ANN001
    """Read a free-text request and return {paper, paper_kind, data, claim}."""
    try:
        resp = backend.complete("extractor",
                                [Message(role="system", content=_SYSTEM + "\n\n" + _CONTRACT),
                                 Message(role="user", content=text[:4000])],
                                response_format="json")
        data = resp.json()
        if isinstance(data, dict) and data.get("paper_kind"):
            return _clean(data)
    except Exception as exc:  # noqa: BLE001
        log.warning("intake parse failed: %s", exc)
    return {"paper": "", "paper_kind": "none", "data": "", "claim": ""}


def _clean(d: dict) -> dict:
    return {
        "paper": str(d.get("paper", "")).strip(),
        "paper_kind": d.get("paper_kind", "none"),
        "data": str(d.get("data", "")).strip(),
        "claim": str(d.get("claim", "")).strip(),
    }


def needed_questions(state: dict) -> list[dict]:
    """The short list of plain-language questions still worth asking.

    Only the paper is ever required. The data and the claim are optional: the agent
    states what it will assume (see ``default_plan``) and proceeds, rather than opening
    a question round. They are returned here only so the agent can mention them in
    passing, never to block.
    """
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


def default_plan(state: dict) -> str:
    """A one-line, plain-language statement of what the agent will do without asking.

    This is feedforward, not a question: the user hears what is about to happen and roughly
    how long, and can change it, but nothing blocks. It encodes the defaults (headline claim,
    auto-download the public data) so a non-technical user never has to choose.
    """
    target = f"the result about {state['claim']}" if state.get("claim") else "the paper's main result"
    if state.get("data"):
        data = "re-run it on the dataset you gave me"
    else:
        data = "find the public data it cites and re-run it"
    return (f"I'll check {target}: re-derive the numbers, look for the choices that produced it, "
            f"research any method I don't cover, and {data}. This takes a couple of minutes.")


def build_intake(request: str, settings=None, *, backend=None) -> dict:  # noqa: ANN001
    """Top-level: understand the request and return what to ask, if anything."""
    if backend is None:
        from econoclast.config import Settings
        from econoclast.llm.backend import detect_backend

        backend = detect_backend(settings or Settings.load())
    state = understand_request(request, backend)
    questions = needed_questions(state)
    ready = bool(state.get("paper"))
    return {
        "understood": state,
        "questions": questions,
        "blocking_question": next((q["ask"] for q in questions if q["required"]), ""),
        "plan": default_plan(state) if ready else "",
        "ready": ready,
        "next": "verify" if ready else "ask_user",
    }
