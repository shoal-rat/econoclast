"""Attacks: grounded LLM critiques, citation checks, and method audits."""

from econoclast.attacks.base import (
    CATEGORIES,
    SEVERITY_WEIGHT,
    Attack,
    AttackContext,
    Finding,
)
from econoclast.attacks.designs import design_label, detect_designs
from econoclast.attacks.registry import all_attacks, attacks_by_name, select_attacks

__all__ = [
    "CATEGORIES",
    "SEVERITY_WEIGHT",
    "Attack",
    "AttackContext",
    "Finding",
    "all_attacks",
    "attacks_by_name",
    "select_attacks",
    "detect_designs",
    "design_label",
]
