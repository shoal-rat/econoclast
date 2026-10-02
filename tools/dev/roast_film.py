#!/usr/bin/env python3
"""The Ravenna Roast: a stand-up parody film cut from a real hunt.

  .venv/bin/python tools/dev/roast_film.py <case> --lang zh|en [--out docs/media/roast-zh.mp4]

Each beat replays one moment of the hunt (tools/dev/capture.mjs), an MC voice delivers a
punchline written from the agent's own findings (edge-tts), and an original score is
synthesised here: a tiptoe assassin tune, rimshots, a drumroll for the verdict and a sad
trombone. Needs the UI preview (`econoclast app --browser --no-open`), Node with
playwright-core on NODE_PATH, ffmpeg, and EDGE_TTS pointing at an edge-tts executable.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from functools import cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "tools" / "dev" / "capture.mjs"
SR = 44100
LEAD = 1.0  # seconds of page load trimmed off every clip

TITLE = ("<div><div style='font-size:20px;letter-spacing:.5em;color:#c9a23a'>{kicker}</div>"
         "<div style='font-size:60px;line-height:1.15;margin:22px 0'>THE RAVENNA ROAST</div>"
         "<small>{sub}</small></div>")
END = ("<div><div style='font-size:54px'>ECONOCLAST</div><small>github.com/shoal-rat/econoclast<br><br>{line}</small></div>")

# Each beat: what the wall shows, and what the MC says. Every claim is from the hunt's own findings.
BEATS = [
    {"id": "title", "query": "view=atrium", "card": "title", "sting": None,
     "zh": "女士们先生们，欢迎来到拉文纳吐槽大会！今晚的嘉宾，是一篇拿过诺贝尔奖的论文。掌声送给它，因为一会儿它就笑不出来了。",
     "en": "Ladies and gentlemen, welcome to the Ravenna Roast! Tonight's guest of honor: a paper with a Nobel Prize. "
           "Give it a hand. It won't be clapping for long."},
    {"id": "prologue", "query": "view=prologue", "skip": 11.4, "sting": "rimshot",
     "zh": "我们的刺客：一千五百岁，玻璃做的，一篇顶刊都没发过。所以他谁都不怕。",
     "en": "Our assassin: fifteen hundred years old, made of glass, zero top-five publications. Which is why he fears nobody."},
    {"id": "decree", "query": "replay=1&from=30&until=70&speed=1", "sting": None,
     "zh": "论文是这么说的：当年殖民者死得多的地方，就懒得建好制度，所以今天穷。这逻辑，优美！优美到我第一反应——查它数据。",
     "en": "The paper's story: where settlers dropped dead, they didn't bother building good institutions, so those places "
           "are poor today. Beautiful logic. So beautiful, my first instinct was: check the data."},
    {"id": "forum", "query": "replay=1&from=72&until=107&speed=0.8", "sting": "rimshot",
     "zh": "刺客先去问了当地人。当地人说：你们给我们的制度打分，问的是外国投资者的资产会不会被没收。投资人问了一圈，就是没问我们。",
     "en": "So the assassin asked the locals. The locals said: you scored our institutions by asking whether foreign "
           "investors get their assets seized. You asked every investor in the room. You just didn't ask us."},
    {"id": "albouy", "query": "replay=1&from=236&until=248&speed=0.7", "sting": "rimshot",
     "zh": "然后 Albouy 一查：六十四个国家的死亡率，有三十六个是从别的国家借来的。这不叫数据，这叫拼单。",
     "en": "Then Albouy checked: of the sixty-four mortality rates, thirty-six were borrowed from other countries. "
           "That's not a dataset. That's a potluck."},
    {"id": "speculum", "query": "replay=1&from=158&until=200&speed=1", "sting": "rimshot",
     "zh": "好消息：零点九四，一位不差，复现了。造假信号：零。坏消息是……这就是今晚最后一个好消息。",
     "en": "Good news: zero point nine four reproduces to the decimal. Fabrication signals: zero. "
           "The bad news: that was the last good news of the night."},
    {"id": "persona", "query": "replay=1&from=299&until=303&speed=0.8", "sting": "rimshot",
     "zh": "殖民者死亡率预测教育，比预测制度还准。把教育一控制，第一阶段 F 值：零点五。零点五！我奶奶量血压都比这显著。",
     "en": "Settler mortality predicts schooling better than it predicts institutions. Hold schooling fixed, and the "
           "first-stage F is zero point five. Zero point five! My grandma's blood pressure cuff has a stronger first stage."},
    {"id": "novacula", "query": "replay=1&from=335&until=338&speed=0.8", "sting": "rimshot",
     "zh": "IV 估计比 OLS 还大，怎么解释？论文说：测量误差。奥卡姆剃刀说：要不就是你的工具变量本身不干净？更简单，还省一个附录。",
     "en": "Why is the IV bigger than OLS? The paper says: measurement error. Occam's razor says: or maybe your "
           "instrument is just dirty? Simpler. And you save an appendix."},
    {"id": "mundus", "query": "replay=1&from=338&until=342&speed=0.8", "sting": "rimshot",
     "zh": "按论文的系数，投资风险评分涨一分，收入差两点六倍。早说嘛！发展中国家还搞什么工业化，直接去找评级机构就完了。",
     "en": "By the paper's own coefficient, one point on a risk rating is worth a two-point-six-fold income gap. "
           "Somebody tell the developing world: forget industrialization, just call the rating agency."},
    {"id": "aula", "query": "replay=1&from=369&until=383&speed=1", "sting": "rimshot",
     "zh": "七百六十八条路：方向对的有百分之九十六，稳健显著的只剩百分之四十二。条条大路通罗马，可惜一半是土路。",
     "en": "Seven hundred sixty-eight roads. Ninety-six percent point the right way. Forty-two percent actually arrive. "
           "All roads lead to Rome. Half of them are dirt tracks."},
    {"id": "verdict", "query": "replay=1&from=385&speed=1", "sting": "drumroll", "lead_pad": 2.4,
     "zh": "裁决：负伤！方向站得住，归因站不住。诺贝尔奖不用退，皇帝掉几块镶片就行。",
     "en": "The verdict: wounded! The direction survives. The attribution does not. They can keep the Nobel. "
           "The emperor just loses a few tiles."},
    {"id": "end", "query": "view=atrium", "card": "end", "sting": "trombone",
     "zh": "Econoclast，专治各种优美的假设。友情提示：每一道伤口，都是待核查的假设，不是指控。",
     "en": "Econoclast. We treat beautiful assumptions. Friendly reminder: every wound is a hypothesis to check, "
           "not an accusation."},
]
VOICE = {"zh": ("zh-CN-YunxiNeural", "+8%", "+2Hz"), "en": ("en-US-AndrewNeural", "+6%", "+0Hz")}


# ------------------------------------------------------------------ the voice
def tts(text: str, lang: str, out: Path) -> float:
    voice, rate, pitch = VOICE[lang]
    exe = os.environ.get("EDGE_TTS", "edge-tts")
    subprocess.run([exe, "--voice", voice, f"--rate={rate}", f"--pitch={pitch}", "--text", text,
                    "--write-media", str(out)], check=True, capture_output=True)
    wav = out.with_suffix(".wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-ar", str(SR), "-ac", "1", str(wav)], check=True)
    return len(read_wav(wav)) / SR


def read_wav(path: Path) -> np.ndarray:
    from scipy.io import wavfile

    sr, x = wavfile.read(path)
    x = x.astype(np.float32)
    if x.ndim > 1:
        x = x.mean(axis=1)
    return x / max(1.0, float(np.abs(x).max()) if x.dtype != np.int16 else 32768.0)


# ------------------------------------------------------------------ the band
def _t(d: float) -> np.ndarray:
    return np.arange(int(d * SR)) / SR


def adsr(n: int, a: float = 0.01, d: float = 0.05, s: float = 0.7, r: float = 0.05) -> np.ndarray:
    a_, d_, r_ = int(a * SR), int(d * SR), int(r * SR)
    e = np.full(n, s, dtype=np.float32)
    e[:a_] = np.linspace(0, 1, max(a_, 1))[: len(e[:a_])]
    e[a_:a_ + d_] = np.linspace(1, s, max(d_, 1))[: len(e[a_:a_ + d_])]
    if r_:
        e[-r_:] *= np.linspace(1, 0, r_)
    return e


def midi(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def reed(f: float, d: float, v: float = 0.25) -> np.ndarray:
    """A bassoon-ish staccato reed: odd harmonics, a little vibrato."""
    t = _t(d)
    ph = 2 * np.pi * f * t + 0.12 * np.sin(2 * np.pi * 5.5 * t)
    x = sum((1 / k) * np.sin(k * ph) for k in (1, 3, 5, 7)) + 0.3 * np.sin(2 * ph)
    return (v * x * adsr(len(t), 0.008, 0.04, 0.55, min(0.04, d / 3))).astype(np.float32)


@cache
def pluck(f: float, d: float, v: float = 0.35) -> np.ndarray:
    """Karplus-Strong pizzicato (cached: the vamp repeats the same few notes)."""
    n = int(d * SR)
    p = max(2, int(SR / f))
    buf = np.random.default_rng(int(f)).uniform(-1, 1, p).astype(np.float32)
    out = np.zeros(n, dtype=np.float32)
    for i in range(n):
        out[i] = buf[i % p]
        buf[i % p] = 0.497 * (buf[i % p] + buf[(i + 1) % p])
    return v * out


def tuba(f: float, d: float, v: float = 0.4) -> np.ndarray:
    t = _t(d)
    x = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(4 * np.pi * f * t) + 0.25 * np.sin(6 * np.pi * f * t)
    return (v * x * adsr(len(t), 0.02, 0.08, 0.5, 0.06)).astype(np.float32)


def noise(d: float, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).uniform(-1, 1, int(d * SR)).astype(np.float32)


def hp(x: np.ndarray, fc: float) -> np.ndarray:
    from scipy.signal import butter, lfilter

    b, a = butter(2, fc / (SR / 2), "high")
    return lfilter(b, a, x).astype(np.float32)


def bp(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    from scipy.signal import butter, lfilter

    b, a = butter(2, [lo / (SR / 2), hi / (SR / 2)], "band")
    return lfilter(b, a, x).astype(np.float32)


def tom(f0: float, f1: float, d: float = 0.18, v: float = 0.6) -> np.ndarray:
    t = _t(d)
    f = np.linspace(f0, f1, len(t))
    return (v * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 18)).astype(np.float32)


def snare(d: float = 0.14, v: float = 0.4, seed: int = 1) -> np.ndarray:
    t = _t(d)
    return (v * (bp(noise(d, seed), 1500, 7000) * 1.6 + 0.4 * np.sin(2 * np.pi * 190 * t)) * np.exp(-t * 26)).astype(np.float32)


def hat(d: float = 0.05, v: float = 0.15) -> np.ndarray:
    t = _t(d)
    return (v * hp(noise(d, 7), 7000) * np.exp(-t * 70)).astype(np.float32)


def crash(d: float = 1.6, v: float = 0.35) -> np.ndarray:
    t = _t(d)
    return (v * hp(noise(d, 9), 5000) * np.exp(-t * 2.6)).astype(np.float32)


def kick(v: float = 0.7) -> np.ndarray:
    return tom(120, 45, 0.25, v)


def rimshot() -> np.ndarray:
    """Ba-dum-tss."""
    out = np.zeros(int(1.3 * SR), dtype=np.float32)
    put(out, tom(210, 120, 0.16, 0.55), 0.0)
    put(out, snare(0.12, 0.3, 3), 0.0)
    put(out, tom(150, 90, 0.2, 0.6), 0.17)
    put(out, crash(1.0, 0.32), 0.36)
    return out


def drumroll(d: float = 2.2) -> np.ndarray:
    out = np.zeros(int((d + 1.8) * SR), dtype=np.float32)
    step = 1 / 26
    k = 0
    while k * step < d:
        put(out, snare(0.07, 0.08 + 0.22 * (k * step / d), seed=k), k * step)
        k += 1
    put(out, crash(1.8, 0.45), d)
    put(out, kick(0.8), d)
    return out


def trombone() -> np.ndarray:
    """Wah, wah, wah, waaah."""
    from scipy.signal import butter, lfilter

    notes = [(58, 0.42), (57, 0.42), (56, 0.42), (55, 1.6)]
    parts = []
    for i, (m, d) in enumerate(notes):
        t = _t(d)
        f = midi(m - 12) * (1 + (0.012 * np.sin(2 * np.pi * 6 * t) * (t > 0.4) if i == 3 else 0))
        ph = 2 * np.pi * np.cumsum(f * np.ones_like(t)) / SR
        saw = 2 * ((ph / (2 * np.pi)) % 1.0) - 1
        wah = 0.5 - 0.5 * np.cos(2 * np.pi * min(1 / d, 2.5) * t)
        y = np.zeros_like(saw)
        zi = np.zeros(2)
        for j in range(0, len(t), 256):  # a sweeping low-pass: the trombone's "wah"
            fc = 350 + 1600 * float(wah[j])
            b, a = butter(2, fc / (SR / 2))
            y[j:j + 256], zi = lfilter(b, a, saw[j:j + 256], zi=zi)
        parts.append((0.38 * y * adsr(len(t), 0.03, 0.05, 0.85, 0.08)).astype(np.float32))
    return np.concatenate(parts)


def swish(v: float = 0.12) -> np.ndarray:
    d = 0.35
    t = _t(d)
    return (v * bp(noise(d, 11), 800, 6000) * np.sin(np.pi * t / d) ** 2).astype(np.float32)


def put(buf: np.ndarray, x: np.ndarray, at: float) -> None:
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i]


def score(total: float) -> np.ndarray:
    """An original tiptoe tune in D Phrygian dominant, oom-pah bass, looped to length."""
    bpm = 126
    beat = 60 / bpm
    bars = int(np.ceil(total / (4 * beat))) + 1
    out = np.zeros(int((bars * 4 * beat + 2) * SR), dtype=np.float32)
    # melody: (bar, beat-in-bar, midi, length-in-beats); 8 bars, repeated
    mel = [
        (0, 0, 74, .4), (0, 1, 78, .2), (0, 1.25, 79, .2), (0, 1.5, 81, .4), (0, 2.5, 82, .2), (0, 2.75, 81, .2), (0, 3, 79, .4),
        (1, 0, 78, .4), (1, .75, 75, .2), (1, 1, 74, .8), (1, 3, 69, .2), (1, 3.25, 70, .2), (1, 3.5, 73, .4),
        (2, 0, 74, .2), (2, .5, 74, .2), (2, 1, 78, .2), (2, 1.5, 81, .2), (2, 2, 86, .6), (2, 2.75, 84, .2), (2, 3, 82, .4), (2, 3.5, 81, .4),
        (3, 0, 79, .4), (3, .5, 78, .4), (3, 1, 75, .4), (3, 1.5, 74, 1.2),
        (4, 0, 74, .4), (4, 1, 78, .2), (4, 1.25, 79, .2), (4, 1.5, 81, .4), (4, 2.5, 82, .2), (4, 2.75, 81, .2), (4, 3, 79, .4),
        (5, 0, 81, .2), (5, .5, 82, .2), (5, 1, 84, .4), (5, 2, 82, .2), (5, 2.5, 81, .2), (5, 3, 79, .4),
        (6, 0, 81, .3), (6, .5, 80, .3), (6, 1, 79, .3), (6, 1.5, 78, .3), (6, 2, 77, .3), (6, 2.5, 76, .3), (6, 3, 75, .3),
        (7, 0, 74, .3), (7, 1, 69, .3), (7, 2, 62, .6),
    ]
    roots = [50, 50, 55, 57, 50, 46, 57, 50]  # D D G A D Bb A D (oom-pah roots)
    chords = {50: (62, 66, 69), 55: (67, 70, 74), 57: (69, 73, 76), 46: (58, 62, 65)}
    for b in range(bars):
        t0 = b * 4 * beat
        k = b % 8
        r = roots[k]
        for q in range(4):  # oom-pah
            at = t0 + q * beat
            if q % 2 == 0:
                put(out, tuba(midi(r - 12 if q == 0 else r - 5), beat * 0.8, 0.32), at)
                put(out, kick(0.35), at)
            else:
                for m in chords[r]:
                    put(out, pluck(midi(m), beat * 0.6, 0.12), at)
                put(out, hat(0.05, 0.12), at)
                put(out, hat(0.05, 0.08), at + beat / 2)
        if b >= 1:  # the melody enters after a bar of vamp
            for bb, bt, m, ln in mel:
                if bb == k:
                    put(out, reed(midi(m), ln * beat, 0.16), t0 + bt * beat)
    return out


# ------------------------------------------------------------------ the film
def capture(query: str, out: Path, seconds: float, captions: list[dict] | None = None) -> None:
    args = ["node", str(CAPTURE), query, str(out), f"{seconds:.2f}"]
    if captions:
        cj = out.with_suffix(".json")
        cj.write_text(json.dumps(captions, ensure_ascii=False))
        args.append(str(cj))
    subprocess.run(args, check=True, capture_output=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--lang", default="zh", choices=["zh", "en"])
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    lang, other = a.lang, ("en" if a.lang == "zh" else "zh")
    tmp = Path(tempfile.mkdtemp(prefix=f"roast-{lang}-"))
    out = Path(a.out) if a.out else ROOT / "docs" / "media" / f"ravenna-roast-{lang}.mp4"

    plan, t = [], 0.0
    for i, b in enumerate(BEATS):
        vo = tts(b[lang], lang, tmp / f"vo{i}.mp3")
        pad = b.get("lead_pad", 0.5)
        tail = 1.25 if b["sting"] == "rimshot" else 3.4 if b["sting"] == "trombone" else 0.7
        dur = pad + vo + tail
        plan.append({"i": i, "beat": b, "vo": vo, "pad": pad, "dur": dur, "start": t})
        t += dur
    total = t

    clips = []
    for p in plan:
        b, i = p["beat"], p["i"]
        caps = [{"at": LEAD + b.get("skip", 0) + 0.25, "until": LEAD + b.get("skip", 0) + p["dur"] - 0.2,
                 "t": f"{b[lang]}<br><span style='font-size:.72em;opacity:.78'>{b[other]}</span>"}]
        if b.get("card") == "title":
            kicker = "ECONOCLAST 吐槽大会" if lang == "zh" else "ECONOCLAST PRESENTS"
            sub = ("Acemoglu, Johnson &amp; Robinson (2001) · 每一个梗都来自刺客的真实发现" if lang == "zh" else
                   "Acemoglu, Johnson &amp; Robinson (2001) · every joke is built on the agent's own findings")
            caps.append({"at": 0, "until": 999, "card": TITLE.format(kicker=kicker, sub=sub)})
        if b.get("card") == "end":
            line = ("每一道伤口都是待人核查的假设，不是指控。<br>Every wound is a hypothesis to check, not an accusation.")
            caps = [{"at": 0, "until": 999, "card": END.format(line=line)}]
        q = f"case={a.case}&{b['query']}&lang={lang}" if b["query"].startswith("replay") else f"{b['query']}&lang={lang}"
        raw = tmp / f"clip{i}.webm"
        capture(q, raw, LEAD + b.get("skip", 0) + p["dur"] + 0.3, caps)
        cut = tmp / f"cut{i}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{LEAD + b.get('skip', 0):.2f}", "-t", f"{p['dur']:.3f}",
                        "-i", str(raw), "-vf", "fps=30,scale=1280:800,format=yuv420p", "-an", "-c:v", "libx264",
                        "-preset", "fast", "-crf", "18", str(cut)], check=True)
        clips.append(cut)
        print(f"beat {i} {b['id']}: {p['dur']:.1f}s", flush=True)

    lst = tmp / "clips.txt"
    lst.write_text("".join(f"file '{c}'\n" for c in clips))
    video = tmp / "video.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264",
                    "-preset", "slow", "-crf", "29", "-movflags", "+faststart", str(video)], check=True)

    # the mix: score ducked under the MC, stings on the punchlines
    music = score(total + 3)
    voice = np.zeros_like(music)
    fx = np.zeros_like(music)
    for p in plan:
        b = p["beat"]
        v = read_wav(tmp / f"vo{p['i']}.wav")
        put(voice, v * 0.95, p["start"] + p["pad"])
        end = p["start"] + p["pad"] + p["vo"]
        if p["i"]:
            put(fx, swish(), p["start"])
        if b["sting"] == "rimshot":
            put(fx, rimshot(), end + 0.12)
        elif b["sting"] == "drumroll":
            put(fx, drumroll(2.2), p["start"])
        elif b["sting"] == "trombone":
            put(fx, trombone(), end + 0.2)
    env = np.abs(voice)
    k = int(0.25 * SR)
    env = np.convolve(env, np.ones(k) / k, mode="same")
    duck = 1.0 - 0.72 * np.clip(env / (env.max() * 0.15 + 1e-9), 0, 1)
    end_i = int(total * SR)
    fade = np.ones_like(music)
    fade[end_i - int(2.5 * SR):end_i] = np.linspace(1, 0, int(2.5 * SR))
    fade[end_i:] = 0
    mix = 0.55 * music * duck * fade + voice + 0.75 * fx
    mix = mix[: end_i + int(0.5 * SR)]
    mix = mix / max(1e-6, np.abs(mix).max()) * 0.92
    from scipy.io import wavfile

    wav = tmp / "mix.wav"
    wavfile.write(wav, SR, (mix * 32767).astype(np.int16))
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(wav), "-c:v", "copy", "-af",
                    "acompressor=threshold=-20dB:ratio=3:attack=5:release=150,loudnorm=I=-16:TP=-1.5:LRA=11,"
                    f"aresample={SR}", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out)],
                   check=True)
    print(json.dumps({"out": str(out), "seconds": round(total, 1), "scratch": str(tmp)}))


if __name__ == "__main__":
    main()
