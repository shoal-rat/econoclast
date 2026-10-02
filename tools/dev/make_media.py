#!/usr/bin/env python3
"""Rebuild the README media (stills, GIFs, the film) from recorded hunts.

  .venv/bin/python tools/dev/make_media.py --en <case> --zh <case> [--film <case> --captions film.json]

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
    ap.add_argument("--film")
    ap.add_argument("--captions")
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
    if a.film:
        film = tmp / "film.webm"
        capture(f"case={a.film}&replay=1&from=0&speed=3&lang=en", film, 240, Path(a.captions) if a.captions else None)
        pro = tmp / "prologue_en.webm"
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(film)], capture_output=True, text=True).stdout)
        video = tmp / "film.mp4"
        run("ffmpeg", "-v", "error", "-y", "-i", str(film), "-i", str(pro), "-filter_complex",
            "[0:v]trim=0:5.4,setpts=PTS-STARTPTS,fps=30,scale=1280:800[a];"
            "[1:v]trim=12.5:25,setpts=PTS-STARTPTS,fps=30,scale=1280:800[b];"
            f"[0:v]trim=5.4:{dur},setpts=PTS-STARTPTS,fps=30,scale=1280:800[c];"
            "[a][b][c]concat=n=3:v=1:a=0,format=yuv420p[v]", "-map", "[v]", "-c:v", "libx264", "-preset", "slow",
            "-crf", "30", "-movflags", "+faststart", str(video))
        total = dur - 5.4 + 5.4 + 12.5
        drone = tmp / "drone.wav"
        run("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
            "aevalsrc='0.10*sin(2*PI*110*t)*(0.7+0.3*sin(2*PI*0.07*t))+0.07*sin(2*PI*164.81*t)*(0.6+0.4*sin(2*PI*0.05*t+1))"
            f"+0.05*sin(2*PI*220*t)+0.03*sin(2*PI*329.63*t)*(0.5+0.5*sin(2*PI*0.11*t))+0.02*sin(2*PI*55*t)':s=44100:d={total}",
            "-af", f"afade=t=in:d=3,afade=t=out:st={total - 4}:d=4,lowpass=f=2000", str(drone))
        final = MEDIA / "sicarius-vs-colonial-origins.mp4"
        run("ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(drone), "-c:v", "copy", "-c:a", "aac", "-b:a",
            "96k", "-shortest", "-movflags", "+faststart", str(final))
        verdict_at = total - 14
        run("ffmpeg", "-v", "error", "-y", "-i", str(final), "-filter_complex",
            f"[0:v]trim=0.5:4.5,setpts=PTS-STARTPTS[a];[0:v]trim={verdict_at}:{verdict_at + 8},setpts=PTS-STARTPTS[b];"
            "[a][b]concat=n=2:v=1:a=0,fps=10,scale=640:-1:flags=lanczos,split[x][y];"
            "[x]palettegen=max_colors=160:stats_mode=diff[p];[y][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
            str(MEDIA / "film_teaser.gif"))
    print(json.dumps({"media": str(MEDIA), "scratch": str(tmp)}))


if __name__ == "__main__":
    main()
