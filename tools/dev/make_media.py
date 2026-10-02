#!/usr/bin/env python3
"""Rebuild the README stills and GIFs from recorded hunts (the film is tools/dev/roast_film.py).

  .venv/bin/python tools/dev/make_media.py --en <case> --zh <case>

Needs the UI preview running (`econoclast app --browser --no-open`), Node with playwright-core on
NODE_PATH (see tools/dev/capture.mjs) and ffmpeg. Capture moments are found from each hunt's events.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from econoclast.case.store import Case

ROOT = Path(__file__).resolve().parents[2]
MEDIA = ROOT / "docs" / "media"
CAPTURE = ROOT / "tools" / "dev" / "capture.mjs"


def run(*cmd: str) -> None:
    subprocess.run(list(cmd), check=True)


def capture(query: str, out: Path, seconds: float, captions: Path | None = None) -> None:
    args = ["node", str(CAPTURE), query, str(out), str(seconds)]
    if captions:
        args.append(str(captions))
    run(*args)


def moments(case_id: str) -> dict:
    evs = Case.load(case_id).events()
    st = {e["station"]: e["seq"] for e in evs if e["kind"] == "station"}
    blades = [e for e in evs if e["kind"] in ("wound", "parry")]
    pal = [e["seq"] for e in blades if e["seq"] > st.get("palatium", 0)]
    return {"forum_from": max(0, st.get("forum", 0) + 2), "palace_from": max(0, st.get("palatium", 0) - 2),
            "palace_at": pal[min(3, len(pal) - 1)] if pal else st.get("palatium", 0)}


def gif(src: Path, start: float, dur: float, out: Path, width: int = 600, fps: int = 8) -> None:
    run("ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", str(dur), "-i", str(src), "-vf",
        f"fps={fps},scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=160:stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle", str(out))


def still(src: Path, out: Path) -> None:
    Image.open(src).convert("RGB").resize((1600, 1000), Image.LANCZOS).save(out, quality=82, optimize=True,
                                                                             progressive=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--en", required=True)
    ap.add_argument("--zh", required=True)
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="econoclast-media-"))
    for lang, cid in (("en", a.en), ("zh", a.zh)):
        out = MEDIA / lang
        out.mkdir(parents=True, exist_ok=True)
        m = moments(cid)
        capture(f"view=atrium&lang={lang}", tmp / f"atrium_{lang}.png", 3.2)
        capture(f"case={cid}&at={m['palace_at']}&lang={lang}", tmp / f"theatre_{lang}.png", 7)
        capture(f"case={cid}&view=tabula&lang={lang}", tmp / f"tabula_{lang}.png", 5)
        for name in ("atrium", "theatre", "tabula"):
            still(tmp / f"{name}_{lang}.png", out / f"{name}.jpg")
        capture(f"view=prologue&lang={lang}", tmp / f"prologue_{lang}.webm", 31)
        capture(f"case={cid}&replay=1&from={m['forum_from']}&speed=1.4&lang={lang}", tmp / f"forum_{lang}.webm", 14)
        capture(f"case={cid}&replay=1&from={m['palace_from']}&speed=1.6&lang={lang}", tmp / f"palace_{lang}.webm", 16)
        gif(tmp / f"prologue_{lang}.webm", 12.5, 12, out / "prologue.gif")
        gif(tmp / f"forum_{lang}.webm", 0.5, 9, out / "forum.gif")
        gif(tmp / f"palace_{lang}.webm", 0.5, 10, out / "palace.gif")
    print(json.dumps({"media": str(MEDIA), "scratch": str(tmp)}))


if __name__ == "__main__":
    main()
