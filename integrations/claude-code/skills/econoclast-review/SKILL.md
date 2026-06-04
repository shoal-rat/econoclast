---
name: econoclast-review
description: Check, referee, red-team, or stress-test an empirical economics paper for p-hacking, cherry-picking, specification search, weak identification, and reporting errors. Use whenever someone asks you to verify, check, audit, referee, or find problems in an economics or social-science paper, with or without its data.
---

# Econoclast: check an economics paper for a non-technical user

Your job is to take one request and finish the whole thing, asking as little as possible. The person
may not be technical. Do not make them learn any commands or config. Talk to them in plain language.

## 1. Understand the request; proceed on sensible defaults

Call the MCP tool `econoclast_intake(request)` with the user's message (or, if MCP is not available,
work it out yourself). It returns what you already have (a paper link, a path, a dataset, a specific
claim), a one-line `plan`, and a `blocking_question`.

- If `ready` is true, do not open a question round. State the `plan` in one line so the user knows
  what is about to happen and roughly how long ("I'll check the main result: re-derive the numbers,
  look for the choices that produced it, find the public data and re-run it. A couple of minutes."),
  then go. This is feedforward, not a question.
- Ask `blocking_question` only when it is non-empty, which happens only when the paper itself is
  missing: "Which paper should I check? Paste a link, a file, or the exact title."
- The dataset and the specific claim are never gates. Econoclast downloads the data itself and
  defaults to the paper's headline result. Do not ask for them; the plan already says what it assumes,
  and the user can correct it in passing.

## 2. Run the whole check

Call `econoclast_verify(paper, data)` (data only if the user gave it). One call does everything:

- the grounded adversarial critique (specification search, cherry-picking, identification,
  robustness coverage, HARKing, over-claiming, literature contradiction), with every finding tied to
  a verbatim quote from the paper,
- for any method Econoclast does not cover, a research-then-verify methodology audit that pulls the
  method's assumptions and checks the paper against them,
- a citation check against Crossref,
- it looks in the paper for a public dataset, downloads it, and re-runs the headline result across
  many defensible specifications.

A referee pass writes the synthesis; unquoted findings are discounted.

The call runs for a couple of minutes and returns once. You already told the user what it is doing, so
do not go silent wondering; wait for it. If the data turns out not to be public, this is not a failure:
Econoclast still returns the full text-based verdict (the critique and the methodology audit) and says
plainly that it could not re-run the data. Pass that on, and offer to add the re-run if they can share
the file.

If `econoclast_verify` is not available, run `econoclast verify "<paper>"` in the shell (install with
`pip install "econoclast[all] @ git+https://github.com/shoal-rat/econoclast"` if missing). For the
deepest pass on a hard method, add `--deep`.

## 3. Explain it in plain language

Translate the result for someone who does not know the jargon.

- Lead with the bottom line: the fragility score and band, in one sentence. For example: "The main
  result looks fragile: it holds in only about a fifth of the equally reasonable ways to run it."
- For each serious finding, say what it means and why it matters, in plain words, and quote the part
  of the paper it is about. Skip the nitpicks unless asked.
- If the check finds a reported number that is internally inconsistent, say so plainly, and add that
  this is often an honest typo, not misconduct.
- Offer the full written report (`report.md` / `report.html`) if they want the detail.

Then let them refine without starting over. Answer follow-ups ("what about Table 4?", "show me the
full report") straight from the report you already have. Only re-run `econoclast_verify` when they
give you something new, like the dataset file or a different claim, and say what changed.

## Rules

- A flagged result is a hypothesis to check, not an accusation. Never tell the user a paper is
  fraudulent. Say what is worth checking and why.
- Do not guess about a method you are unsure of. Econoclast retrieves the method's literature for you;
  rely on that, and say when something could not be verified.
- Blind yourself to who wrote the paper. Judge the work, not the authors.
