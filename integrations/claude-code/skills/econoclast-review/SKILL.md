---
name: econoclast-review
description: Check, referee, red-team, or stress-test an empirical economics paper for p-hacking, cherry-picking, specification search, weak identification, and reporting errors. Use whenever someone asks you to verify, check, audit, referee, or find problems in an economics or social-science paper, with or without its data.
---

# Econoclast: check an economics paper for a non-technical user

Your job is to take one request and finish the whole thing, asking as little as possible. The person
may not be technical. Do not make them learn any commands or config. Talk to them in plain language.

## 1. Understand the request, then ask only what is missing

Call the MCP tool `econoclast_intake(request)` with the user's message (or, if MCP is not available,
work it out yourself). It returns what you already have (a paper link, a path, a dataset, a specific
claim) and a short list of plain-language questions for anything missing.

- If it found the paper, just proceed. Do not ask redundant questions.
- If the paper is missing, ask the one question it gives you, in plain words, for example: "Which
  paper should I check? Paste a link, a file, or the exact title."
- The dataset and the specific claim are optional. Mention them once if helpful, but do not block on
  them: Econoclast will try to download the data itself and will default to the paper's headline
  result.

Keep it to one short round of questions. A non-technical economist should be able to answer in a
sentence.

## 2. Run the whole check

Call `econoclast_verify(paper, data)` (data only if the user gave it). One call does everything:

- the deterministic statistical forensics (statcheck, GRIM, p-curve, z-bunching, and so on),
- the adversarial critique (specification search, cherry-picking, identification, missing robustness,
  HARKing, over-claiming),
- for any method Econoclast does not cover, it researches the method's assumptions and checks the
  paper against them,
- it looks in the paper for a public dataset, downloads it, and re-runs the headline result across
  many defensible specifications.

If `econoclast_verify` is not available, run `econoclast verify "<paper>"` in the shell (install with
`pip install "econoclast[all] @ git+https://github.com/shoal-rat/econoclast"` if missing). For the
deepest pass on a hard method, add `--deep`.

## 3. Explain it in plain language

Translate the result for someone who does not know the jargon.

- Lead with the bottom line: the fragility score and band, in one sentence. For example: "The main
  result looks fragile: it holds in only about a fifth of the equally reasonable ways to run it."
- For each serious finding, say what it means and why it matters, in plain words, and quote the part
  of the paper it is about. Skip the nitpicks unless asked.
- If a reported number is internally impossible (statcheck, GRIM), say so plainly, and add that this
  is often an honest typo, not misconduct.
- Offer the full written report (`report.md` / `report.html`) if they want the detail.

## Rules

- A flagged result is a hypothesis to check, not an accusation. Never tell the user a paper is
  fraudulent. Say what is worth checking and why.
- Do not guess about a method you are unsure of. Econoclast retrieves the method's literature for you;
  rely on that, and say when something could not be verified.
- Blind yourself to who wrote the paper. Judge the work, not the authors.
