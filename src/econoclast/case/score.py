"""The fragility score: how badly the Emperor is hurt.

Each wound weighs severity times grounded confidence. The deepest wound counts in
full and every further one counts less (x0.7 each, deepest first), then the total is
saturated. So the score is driven by how deep the worst wounds go, not by how many
blades were swung: one high wound grazes, a few high wounds wound, and only several
critical wounds fell the Emperor. An *integrity* wound (a reported number that cannot
be true, a result that does not reproduce) can never leave the decree merely grazed.
"""

from __future__ import annotations

import math

from econoclast.case.models import Wound
from econoclast.world import INTEGRITY_BLADES, band_for, blade, seal

# Blades whose deep wounds mean a reported number cannot be trusted (they floor the score);
# all INTEGRITY_BLADES feed the seal.
_INTEGRITY_BLADES = {"abacus", "speculum", "falsum", "palimpsestus"}


DECAY = 0.7


def compute_fragility(wounds: list[Wound]) -> dict:
    weights = sorted((w.weight for w in wounds), reverse=True)
    raw = sum(v * DECAY ** i for i, v in enumerate(weights))
    score = round(100 * (1 - math.exp(-raw / 12.0)), 1)

    integrity = any(
        w.blade in _INTEGRITY_BLADES
        and w.severity in ("high", "critical")
        and w.effective_confidence >= 0.6
        for w in wounds
    )
    if integrity:
        score = max(score, 45.0)

    band = band_for(score)
    integ = [w for w in wounds if w.blade in INTEGRITY_BLADES]
    if any(w.severity in ("high", "critical") and w.effective_confidence >= 0.6 for w in integ):
        seal_key = "fractum"
    elif any(w.severity != "info" for w in integ):
        seal_key = "dubium"
    else:
        seal_key = "integrum"
    sl = seal(seal_key)
    by_blade: dict[str, float] = {}
    by_severity: dict[str, int] = {}
    for w in wounds:
        by_blade[w.blade] = round(by_blade.get(w.blade, 0.0) + w.weight, 2)
        by_severity[w.severity] = by_severity.get(w.severity, 0) + 1

    return {
        "score": score,
        "band": band.key,
        "band_latin": band.latin,
        "band_en": band.en,
        "band_zh": band.zh,
        "blurb_en": band.blurb_en,
        "blurb_zh": band.blurb_zh,
        "pose": band.pose,
        "integrity": integrity,
        "seal": sl.key,
        "seal_latin": sl.latin,
        "seal_en": sl.en,
        "seal_zh": sl.zh,
        "seal_blurb_en": sl.blurb_en,
        "seal_blurb_zh": sl.blurb_zh,
        "integrity_wounds": len(integ),
        "n_wounds": len(wounds),
        "raw_weight": round(raw, 2),
        "by_blade": dict(sorted(by_blade.items(), key=lambda kv: kv[1], reverse=True)),
        "by_severity": by_severity,
    }


def blade_label(key: str, lang: str = "en") -> str:
    b = blade(key)
    if b is None:
        return key
    return f"{b.latin} · {b.zh if lang == 'zh' else b.en}"
