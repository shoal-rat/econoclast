# Contributing to Econoclast

Thanks for helping make empirical work harder to fake and easier to check.

## Setup

```bash
git clone https://github.com/shoal-rat/econoclast && cd econoclast
uv venv && uv pip install -e ".[dev,pdf]"
pytest && ruff check src tests tools
```

The tests never call a real agent.

## Adding a blade

1. Add it to `BLADES` in `src/econoclast/world.py` (Latin name, English, Chinese, what it hunts).
2. Tell the agent when and how to swing it in `src/econoclast/arsenal/doctrine.py`, in the station where it
   belongs.
3. If it needs evidence the agent cannot produce by itself, add an arsenal tool: a plain method on `Arsenal`
   in `arsenal/tools.py` that does the work and emits an event, wrapped in `arsenal/server.py`.
4. Give it a place on the wall in `app/web/js/director.js` and a line in the chronicle (`ui.js`).
5. Regenerate the lexicon doc: `python tools/dev/world_doc.py`.

## Adding a statistical screen or estimator

Put it in `tesserae/forensics.py`, `viae/forensics.py` or `viae/`, and add a known-answer test against
synthetic data with a known truth **and** a check that it stays quiet on realistic honest data. A screen that
cries wolf is worse than no screen.

## Working on the stage

`econoclast app --browser` serves the UI in a browser. `tools/dev/rehearsal.py <paper.pdf> <data.csv>` plays a
scripted hunt through the real arsenal so every animation can be watched without an agent.
