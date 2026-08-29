# Librarian Email Agent

An email assistant for HKU Libraries staff. It reads incoming mail, sorts it,
answers what it can from the library's own FAQ, and hands everything else to a
human with a note explaining why.

Runs entirely on your own machine. No cloud account, no API key, no per-message
cost, no data leaving the laptop.

---

## What it does

```
                 ┌── automated notification ──→ ignored
                 │
  an email ──→ classify ──→ meeting request ──→ flagged + one-line summary
                 │
                 └── enquiry ──→ search the FAQ ──→ draft a reply ──┬─→ sent
                                                                    └─→ held
```

It is **held** rather than sent whenever any of these is true:

- the FAQ match is weak
- the reply was written by the model rather than quoted from the FAQ
- the mail is in Chinese — drafting quality there is unverified
- auto-send is switched off

It also keeps a **knowledge-base gap report**: every enquiry no FAQ entry could
answer. Over a few weeks that becomes a prioritised list of FAQ entries worth
writing — the agent improves the system instead of only reacting to it.

And a **review queue**: everything still waiting on a person, urgent first. This
is the only use made of the urgency label, deliberately. Urgency is the model's
guess, measured on two cases and so effectively unmeasured, which is exactly why
it orders a list rather than gating a send. Wrong urgency costs a librarian
reading two items out of order; wrong anything in the send path costs a student
acting on false information.

## It is not an agent loop, deliberately

Every step has a known position in the sequence, so nothing needs deciding at
runtime. Python controls the order; the model is asked to do three text tasks
(classify, summarise, draft) and nothing else.

That choice came from a measurement, not a preference. `phi-4-mini` is listed
as tool-capable in Foundry Local's catalog but does not use tools in practice
(FINDINGS.md F5). Rather than fight it, we removed the need for it.

The wider point, worth carrying into the cookbook: **most tasks people describe
as "agentic" are this shape.** True tool-calling autonomy is for when the
sequence genuinely cannot be known in advance. Where it can, a fixed pipeline is
more reliable, cheaper, and something a librarian can read and predict.

## Setup

```bash
pip3 install -r requirements.txt
cp .env.example .env
```

Install a local model — free, Microsoft, runs on your machine:

```bash
brew tap microsoft/foundrylocal
brew trust --formula microsoft/foundrylocal/foundrylocal
brew install foundrylocal

foundry model download phi-4-mini
foundry model load phi-4-mini
foundry server status
```

The last command prints the port.

Put that port in `.env` as `MODEL_BASE_URL` (with `/v1` on the end — the port
is assigned per install, it is not the same on every machine).

## Run

```bash
python3 run.py --selftest
python3 run.py --check
python3 run.py
python3 run.py --eval
```

| Command | What it does |
|---|---|
| `--selftest` | Verifies the pipeline. No model needed. |
| `--check` | Verifies the model is reachable and sane. |
| *(none)* | Processes `inbox/`. |
| `--eval` | Scores the classifier against 20 labelled cases. |

Run them in that order when something breaks — each isolates a different layer.
If `--selftest` passes and `--check` fails, the code is fine and the model is
the problem.

## What's in here

| File | |
|---|---|
| `CODE_GUIDE.md` | **Every file explained for a beginner** — start here. |
| `FINDINGS.md` | What we measured and what broke. The research record. |
| `run.py` | The commands above. Start here to see how the pieces are wired. |
| `pipeline.py` | **The sequence.** Read this first — it is what the agent does. |
| `knowledge.py` | Loads and searches the FAQ. Deliberately simple scoring. |
| `llm.py` | Model calls. Note `pick_one` and why it exists. |
| `sources.py` | Where mail comes from: files (works) or Graph (unverified). |
| `config.py` | Everything swappable: provider, source, thresholds. |
| `evaluate.py` | Scores the classifier. This is the research part. |
| `selftest.py` | Runs the pipeline against a fake model. |
| `knowledge_base/` | Real HKU FAQ content, 23 entries. Plain markdown — **editable by librarians, no code**. |
| `eval/cases.json` | 20 hand-labelled emails, including 2 in Chinese. |

## Auto-send

On by default. Four conditions must all hold before anything is sent without a
human, and it is worth reading them together, because each one closes a
different failure:

1. **The FAQ match scores at least `AUTO_SEND_THRESHOLD`** (0.55) — the FAQ
   plausibly answers the question at all.
2. **The reply is a verbatim template**, not model-written prose. This is the
   F10 rule and the load-bearing one: a model that invented library opening
   hours cannot invent anything when the reply quotes the FAQ word for word.
3. **The email is in English** — Chinese drafting quality is unverified, so it
   is held rather than guessed at.
4. **`AUTO_SEND` is on.**

Safe as shipped for a further reason that is independent of all four: with
`EMAIL_SOURCE=files` nothing leaves the machine. "Sending" writes a file marked
SENT, so every decision stays observable.

**Confidence is the search's, not the model's.** A small model will cheerfully
claim certainty while inventing a loan period. A match score can be checked:
*"sent because the FAQ entry 'Can I renew books online?' matched at 0.667"* is
auditable in a way *"the model seemed sure"* never is.

One honest note on condition 3. Until 2026-08-28 the language test was a model
call scoring 60% and biased toward answering `chinese`, so it was holding back
roughly 40% of English mail — auto-send looked more conservative than it was
designed to be, for a reason nobody chose. That is fixed (FINDINGS.md F12), and
more mail is now genuinely eligible. Auto-send stays on by default anyway: the
safety was never resting on that bug, it rests on conditions 1, 2 and 4, and on
nothing actually leaving the machine.

Before pointing this at a real shared mailbox: turn auto-send off, and get
explicit sign-off. A confidently wrong reply from the library's official address
is an institutional problem, not a bug report.

## Honest limitations

- **FAQ search matches words, not meaning.** "How long can I keep a book" will
  not find an entry phrased as "loan period". Embeddings are the obvious next
  step and the single clearest improvement available.
- **Thresholds were tuned on ten cases.** Enough to avoid something obviously
  broken; nowhere near calibrated. Re-tune on real enquiry data.
- **The eval set is synthetic**, written from the public FAQ. Real anonymised
  enquiries would make the accuracy number far more defensible.
- **Chinese is untested** beyond two eval cases, which is why it is never
  auto-sent.
- **The Graph email source has never run.** It is written to spec but
  `Mail.Read` consent was refused by an administrator in both tenants tried.
  Do not report it as working.

## Sources

FAQ content copied verbatim from HKU Libraries, with source URLs in each
`knowledge_base/*.md` file:
<https://lib.hku.hk/FAQ/> · <https://libguides.lib.hku.hk>
