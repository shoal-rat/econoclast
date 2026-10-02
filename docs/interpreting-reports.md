# Reading a Tabula

**Read this before you quote a wound in public.** Econoclast is a screening tool. It surfaces hypotheses
for a person to verify, not verdicts of misconduct.

## Two separate judgements

**Fragility** (0-100, the Emperor's fate) answers: *how much of the headline survives?* Each wound weighs
severity times grounded confidence; the deepest counts in full and each further wound counts 30% less, and the
total saturates. The score follows how deep the worst wounds go, not how many blades were swung: one high wound
grazes, a few wound, and only several critical wounds fell the Emperor.

| Score | Verdict | Read it as |
|---|---|---|
| below 15 | Imperator stat · the Emperor stands | nothing material landed |
| 15-35 | Laesus · grazed | small cuts; the headline is probably safe |
| 35-60 | Vulneratus · wounded | real weaknesses; it may not survive a hostile referee |
| 60-80 | Moribundus · mortally wounded | fragile to plausible alternative choices |
| 80+ | Cecidit · fallen | treat the claim as unsupported until the wounds are answered |

**The seal** (integrity) answers: *can the numbers and the presentation be taken at face value?* It reads only
the integrity blades (Abacus, Falsum, Speculum, Palimpsestus, Fucus).

| Seal | Means |
|---|---|
| Sigillum integrum · intact | no integrity flag survived the agent's judgement |
| Sigillum dubium · questioned | some flags deserve a human look; each may be innocent |
| Sigillum fractum · broken | serious flags: numbers that cannot be true, data or versions bent toward the conclusion |

A paper can be fragile with an intact seal (honest but over-sold), or robust with a questioned seal (the
result holds, but something in the presentation needs explaining). A deep integrity wound also floors the
fragility score at 45, because a result you cannot trust cannot be "grazed".

## What a wound does and does not mean

- **Text wounds** carry a verbatim quote, checked mechanically against the paper. If the quote was not found,
  the wound says so and counts for little. Read the quote: if it does not support the wound, discard it.
- **Computation wounds** point at the script and output that produced them, in the case folder. Rerun them.
- **Forum wounds** (Inversio, Theoria, Mundus) rest on the field brief: open `notes/field.md` and check the
  sources the agent relied on. They are arguments about the real world, and the right response to them is
  evidence about the real world.
- **Falsum** flags are statistical screens. GRIM fails on non-integer items; digit tests fail on rounded or
  coded data; bunching is a property of literatures. The agent is told to rule out innocent explanations and
  say which ones it could not rule out.
- **Palimpsestus** compares versions. Papers change for good reasons; the question is whether a change that
  favours the headline was disclosed.
- **An impossible number is often an honest typo.** Ask the authors before you assume anything else.
