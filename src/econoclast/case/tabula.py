"""The Tabula: the hunt written down, as Markdown, JSON and one self-contained HTML page."""

from __future__ import annotations

import base64
import html
import json
from datetime import datetime
from pathlib import Path

from econoclast.case.score import compute_fragility
from econoclast.case.store import Case
from econoclast.world import SEVERITY_LATIN, blade

_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def tabula_data(case: Case) -> dict:
    meta = case.meta()
    wounds = sorted(case.wounds(), key=lambda w: (_SEV_ORDER.get(w.severity, 5), -w.weight))
    verdict = case.verdict() or {}
    frag = verdict.get("fragility") or compute_fragility(wounds)
    speculum = [e for e in case.events() if e.get("kind") == "speculum"]
    events = case.events()
    viae = next((e for e in reversed(events) if e.get("kind") == "viae" and e.get("status") == "done"), None)
    final = next((e.get("text") for e in reversed(events) if e.get("kind") == "final"), "")
    return {
        "id": case.id,
        "title": meta.get("title") or meta.get("paper_input"),
        "paper_input": meta.get("paper_input"),
        "lang": meta.get("lang", "en"),
        "backend": meta.get("backend_used") or meta.get("backend"),
        "target": case.target(),
        "fragility": frag,
        "verdict": verdict,
        "wounds": [w.to_dict() for w in wounds],
        "parries": [p.to_dict() for p in case.parries()],
        "speculum": [{k: v for k, v in e.items() if k not in ("kind", "ts", "seq")} for e in speculum],
        "viae": viae and {"summary": viae.get("summary"), "preferred": viae.get("preferred"),
                          "points": viae.get("points")},
        "final": final,
        "field": _field(case),
    }


def _field(case: Case) -> dict | None:
    try:
        return json.loads(case.path("notes", "field.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_tabula(case: Case) -> dict[str, str]:
    data = tabula_data(case)
    case.path("tabula.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    case.path("tabula.md").write_text(render_markdown(data), encoding="utf-8")
    case.path("tabula.html").write_text(render_html(data, case.root), encoding="utf-8")
    return {"html": "tabula.html", "markdown": "tabula.md", "json": "tabula.json"}


# ------------------------------------------------------------------ markdown
def render_markdown(d: dict) -> str:
    zh = d.get("lang") == "zh"
    f = d["fragility"]
    v = d.get("verdict") or {}
    band = f.get("band_zh") if zh else f.get("band_en")
    lines = [f"# {d['title']}", ""]
    lines.append(f"**{f.get('band_latin', '')} · {band}** · fragility {f['score']}/100")
    lines.append("")
    if v.get("headline"):
        lines += [f"> {v['headline']}", ""]
    if v.get("assessment"):
        lines += [v["assessment"], ""]
    tgt = d.get("target") or {}
    if tgt.get("claim"):
        lines += ["## " + ("诏书（被检验的结论）" if zh else "The decree under test"), "", tgt["claim"], ""]
    fld = d.get("field") or {}
    if fld.get("real_mechanism") or fld.get("setting"):
        lines += ["## " + ("真实世界" if zh else "The real world"), ""]
        for key in ("setting", "claimed_mechanism", "real_mechanism", "institutions", "magnitudes", "theory"):
            if fld.get(key):
                lines += [fld[key], ""]
        if fld.get("sources"):
            lines += [f"- {x}" for x in fld["sources"]] + [""]
    lines += ["## " + ("伤口" if zh else "Wounds"), ""]
    if not d["wounds"]:
        lines.append("_None._")
    for w in d["wounds"]:
        b = blade(w["blade"])
        bl = f"{b.latin}" if b else w["blade"]
        mark = "" if w.get("verified") is not False else " (quote not found in the paper)"
        lines.append(f"### [{w['severity']}] {w['title']}")
        lines.append(f"*{bl} · {SEVERITY_LATIN.get(w['severity'], '')} · confidence "
                     f"{w['effective_confidence']:.0%}{mark}*")
        lines.append("")
        if w.get("quote"):
            lines += [f"> {w['quote']}", ""]
        if w.get("detail"):
            lines += [w["detail"], ""]
        if w.get("artifacts"):
            lines += ["Artifacts: " + ", ".join(f"`{a}`" for a in w["artifacts"]), ""]
        if w.get("remedy"):
            lines += [f"**{'补救' if zh else 'Remedy'}:** {w['remedy']}", ""]
    if d["parries"]:
        lines += ["## " + ("挡下的刀" if zh else "Parried"), ""]
        for p in d["parries"]:
            b = blade(p["blade"])
            lines.append(f"- **{b.latin if b else p['blade']}**: {p['note']}")
        lines.append("")
    if v.get("change_my_mind"):
        lines += ["## " + ("什么能改变裁决" if zh else "What would change the verdict"), "", v["change_my_mind"], ""]
    if v.get("survived"):
        lines += ["## " + ("站得住的部分" if zh else "What survived"), ""] + [f"- {s}" for s in v["survived"]] + [""]
    lines += ["---", "_" + ("每道伤口都是供人复核的假设，不是指控。" if zh else
                          "Every wound is a hypothesis for a human to check, not an accusation.") + "_"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------- html
_CSS = """
:root{--gold:#c9a23a;--gold2:#e8cf7a;--lapis:#1f3a7a;--night:#0e1b3d;--porph:#5b1f4a;--red:#9e2a2b;
--marble:#efe8d8;--ink:#2a2018;--grout:#3a3128;--green:#2e7d4f}
*{box-sizing:border-box}body{margin:0;background:var(--night);color:var(--ink);
font:17px/1.6 "Cormorant Garamond","Noto Serif SC",Georgia,serif}
.wall{max-width:900px;margin:32px auto;padding:14px;background:
repeating-linear-gradient(90deg,var(--gold) 0 9px,var(--grout) 9px 10px),var(--gold);
background-size:10px 10px}
.tab{background:var(--marble);padding:40px 46px;border:3px solid var(--grout)}
h1{font:600 30px/1.2 Cinzel,"Noto Serif SC",serif;letter-spacing:.04em;margin:0 0 6px;color:var(--night)}
h2{font:600 18px Cinzel,"Noto Serif SC",serif;letter-spacing:.12em;text-transform:uppercase;color:var(--porph);
border-bottom:2px solid var(--gold);padding-bottom:4px;margin-top:38px}
.band{display:flex;gap:22px;align-items:center;margin:18px 0;padding:18px;background:var(--night);color:var(--gold2)}
.score{font:700 54px Cinzel,serif}.latin{font:600 22px Cinzel,serif;letter-spacing:.08em}
.head{font-size:21px;font-style:italic;margin:14px 0}
.w{margin:18px 0;padding:16px 18px;background:#fff8ec;border-left:8px solid var(--red)}
.w.medium{border-color:#c8742a}.w.low{border-color:var(--lapis)}.w.info{border-color:#8a8178}
.w h3{margin:0 0 4px;font:600 19px "Cormorant Garamond","Noto Serif SC",serif}
.meta{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:#7a6a58}
blockquote{margin:10px 0;padding:8px 14px;background:var(--marble);border-left:3px solid var(--gold);font-style:italic}
.unv{color:var(--red);font-size:13px}.rem{color:var(--green)}
.p{margin:8px 0}.p b{font-family:Cinzel,serif;color:var(--green)}
img{max-width:100%;border:3px solid var(--grout)}code{font-size:14px}
.foot{margin-top:40px;font-size:14px;color:#7a6a58;font-style:italic}
"""


def render_html(d: dict, root: Path | None = None) -> str:
    zh = d.get("lang") == "zh"
    e = html.escape
    f = d["fragility"]
    v = d.get("verdict") or {}
    parts = [f"<h1>{e(str(d['title']))}</h1>",
             f"<div class=meta>Econoclast · {datetime.now():%Y-%m-%d} · {e(str(d.get('backend') or ''))}</div>",
             "<div class=band>"
             f"<div class=score>{f['score']:.0f}</div>"
             f"<div><div class=latin>{e(f.get('band_latin', ''))}</div>"
             f"<div>{e(f.get('band_zh') if zh else f.get('band_en', ''))} · "
             f"{e(f.get('blurb_zh') if zh else f.get('blurb_en', ''))}</div></div></div>"]
    if v.get("headline"):
        parts.append(f"<p class=head>{e(v['headline'])}</p>")
    if v.get("assessment"):
        parts.append(f"<p>{e(v['assessment'])}</p>")
    tgt = d.get("target") or {}
    if tgt.get("claim"):
        parts.append(f"<h2>{'诏书' if zh else 'The decree'}</h2><p>{e(tgt['claim'])}</p>")
    fld = d.get("field") or {}
    if fld.get("real_mechanism") or fld.get("setting"):
        parts.append(f"<h2>{'真实世界' if zh else 'The real world'}</h2>")
        for key in ("setting", "claimed_mechanism", "real_mechanism", "institutions", "magnitudes", "theory"):
            if fld.get(key):
                parts.append(f"<p>{e(fld[key])}</p>")
        if fld.get("sources"):
            parts.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in fld["sources"]) + "</ul>")
    parts.append(f"<h2>{'伤口' if zh else 'Wounds'} ({len(d['wounds'])})</h2>")
    for w in d["wounds"]:
        b = blade(w["blade"])
        bl = f"{b.latin} · {b.zh if zh else b.en}" if b else w["blade"]
        unv = (f" <span class=unv>{'引文未在论文中找到' if zh else 'quote not found in the paper'}</span>"
               if w.get("verified") is False else "")
        parts.append(f"<div class='w {e(w['severity'])}'><h3>{e(w['title'])}</h3>"
                     f"<div class=meta>{e(bl)} · {e(SEVERITY_LATIN.get(w['severity'], ''))} · "
                     f"{w['effective_confidence']:.0%}{unv}</div>")
        if w.get("quote"):
            parts.append(f"<blockquote>{e(w['quote'])}</blockquote>")
        if w.get("detail"):
            parts.append(f"<p>{e(w['detail'])}</p>")
        if w.get("artifacts"):
            parts.append("<p>" + ", ".join(f"<code>{e(a)}</code>" for a in w["artifacts"]) + "</p>")
        if w.get("remedy"):
            parts.append(f"<p class=rem><b>{'补救' if zh else 'Remedy'}:</b> {e(w['remedy'])}</p>")
        parts.append("</div>")
    if d["parries"]:
        parts.append(f"<h2>{'挡下的刀' if zh else 'Parried'}</h2>")
        for p in d["parries"]:
            b = blade(p["blade"])
            parts.append(f"<div class=p><b>{e(b.latin if b else p['blade'])}</b> {e(p['note'])}</div>")
    png = root / "out" / "spec_curve.png" if root else None
    if png and png.exists():
        b64 = base64.b64encode(png.read_bytes()).decode()
        parts.append(f"<h2>Mille Viae</h2><img alt='specification curve' src='data:image/png;base64,{b64}'>")
    if v.get("change_my_mind"):
        parts.append(f"<h2>{'什么能改变裁决' if zh else 'What would change the verdict'}</h2>"
                     f"<p>{e(v['change_my_mind'])}</p>")
    if v.get("survived"):
        parts.append(f"<h2>{'站得住的部分' if zh else 'What survived'}</h2><ul>"
                     + "".join(f"<li>{e(s)}</li>" for s in v["survived"]) + "</ul>")
    parts.append("<p class=foot>" + ("每道伤口都是供人复核的假设，不是指控。" if zh else
                                     "Every wound is a hypothesis for a human to check, not an accusation.")
                 + "</p>")
    return ("<!doctype html><html><head><meta charset=utf-8><meta name=viewport "
            "content='width=device-width,initial-scale=1'><title>Tabula · " + e(str(d["title"]))[:80]
            + "</title><style>" + _CSS + "</style></head><body><div class=wall><div class=tab>"
            + "".join(parts) + "</div></div></body></html>")
