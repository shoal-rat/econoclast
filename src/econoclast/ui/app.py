"""Streamlit UI for Econoclast.

Run it with `econoclast ui` (or `streamlit run src/econoclast/ui/app.py`).
Install the extra first: `pip install econoclast[ui]`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    raise SystemExit("Streamlit is not installed. Run `pip install econoclast[ui]`.") from None

from econoclast.agent.harness import Econoclast
from econoclast.attacks.registry import all_attacks
from econoclast.config import Settings
from econoclast.report import render_html, render_markdown

_BAND_COLOR = {
    "Robust": "#1a7f37", "Minor concerns": "#9a6700", "Material concerns": "#bc4c00",
    "Fragile": "#cf222e", "Severe": "#82071e",
}


def main() -> None:
    st.set_page_config(page_title="Econoclast", layout="wide")
    st.title("Econoclast")
    st.caption("An adversarial AI referee that red-teams empirical-economics papers "
               "for p-hacking, cherry-picking and specification search.")

    settings = Settings.load()

    with st.sidebar:
        st.header("Settings")
        use_lit = st.checkbox("Retrieve online literature", value=True)
        st.divider()
        st.subheader("Attacks")
        names = [a.name for a in all_attacks()]
        chosen = st.multiselect("Run subset (empty = all)", names, default=[])

    uploaded = st.file_uploader("Upload a paper (PDF, LaTeX, or text)", type=["pdf", "tex", "txt", "md"])
    path_input = st.text_input("…or paste a local path", "")

    if st.button("Attack the paper", type="primary"):
        target = _resolve_target(uploaded, path_input)
        if target is None:
            st.error("Provide a file or a valid path.")
            return
        try:
            eco = Econoclast(settings=settings)
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
            return
        with st.spinner("Reading the paper and running the adversarial attacks…"):
            report = eco.review(target, attack_names=chosen or None, use_literature=use_lit)
        _render(report)


def _resolve_target(uploaded, path_input: str):
    if uploaded is not None:
        suffix = Path(uploaded.name).suffix or ".txt"
        tmp = Path(tempfile.gettempdir()) / f"econoclast_upload{suffix}"
        tmp.write_bytes(uploaded.getvalue())
        return tmp
    if path_input and Path(path_input).exists():
        return Path(path_input)
    return None


def _render(report) -> None:
    frag = report.fragility
    color = _BAND_COLOR.get(frag["band"], "#656d76")
    c1, c2, c3 = st.columns([1, 1, 2])
    c1.metric("Fragility", f"{frag['score']}/100")
    c2.markdown(f"<h3 style='color:{color}'>{frag['band']}</h3>", unsafe_allow_html=True)
    c3.write(frag["band_blurb"])
    if frag.get("integrity_violation"):
        st.warning("Integrity flag: a reported statistic is internally impossible or inconsistent.")

    if report.referee.get("headline"):
        st.subheader("Referee verdict")
        st.markdown(f"**{report.referee['headline']}**")
        st.write(report.referee.get("assessment", ""))
        if report.referee.get("what_would_change_my_mind"):
            st.info("**What would change the verdict:** " + report.referee["what_would_change_my_mind"])

    st.subheader(f"Findings ({len(report.findings)})")
    for f in report.findings_sorted():
        with st.expander(f"[{f.severity}] {f.title}  ·  {f.category}  ·  {f.confidence*100:.0f}%"):
            st.write(f.detail)
            for q in f.evidence:
                st.markdown(f"> {q}")
            if f.recommendation:
                st.success("**Fix:** " + f.recommendation)

    st.divider()
    d1, d2, d3 = st.columns(3)
    d1.download_button("JSON", report.to_json(), "econoclast-report.json", "application/json")
    d2.download_button("Markdown", render_markdown(report), "econoclast-report.md", "text/markdown")
    d3.download_button("HTML", render_html(report), "econoclast-report.html", "text/html")


if __name__ == "__main__":
    main()
