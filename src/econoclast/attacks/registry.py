"""Registry of all attacks."""

from __future__ import annotations

from econoclast.attacks.base import Attack
from econoclast.attacks.citations import CitationVerificationAttack
from econoclast.attacks.forensic import build_forensic_attacks
from econoclast.attacks.llm import build_llm_attacks


def all_attacks() -> list[Attack]:
    return build_forensic_attacks() + [CitationVerificationAttack()] + build_llm_attacks()


def attacks_by_name() -> dict[str, Attack]:
    return {a.name: a for a in all_attacks()}


def select_attacks(
    names: list[str] | None = None,
    *,
    include_forensic: bool = True,
    include_llm: bool = True,
) -> list[Attack]:
    chosen = []
    for a in all_attacks():
        if names is not None and a.name not in names:
            continue
        if a.kind == "deterministic" and not include_forensic:
            continue
        if a.kind == "llm" and not include_llm:
            continue
        chosen.append(a)  # "network" attacks (e.g. citation-check) are always eligible
    return chosen
