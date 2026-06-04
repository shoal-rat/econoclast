"""Registry of all attacks."""

from __future__ import annotations

from econoclast.attacks.base import Attack
from econoclast.attacks.citations import CitationVerificationAttack
from econoclast.attacks.dynamic import DynamicCheckAttack
from econoclast.attacks.llm import build_llm_attacks
from econoclast.attacks.methodology import MethodologyAuditAttack


def all_attacks() -> list[Attack]:
    return ([CitationVerificationAttack()]
            + build_llm_attacks()
            + [MethodologyAuditAttack(), DynamicCheckAttack()])


def attacks_by_name() -> dict[str, Attack]:
    return {a.name: a for a in all_attacks()}


def select_attacks(names: list[str] | None = None) -> list[Attack]:
    if names is None:
        return all_attacks()
    return [a for a in all_attacks() if a.name in names]
