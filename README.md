# Librarian Email Agent

A small email assistant for the HKU Libraries mailbox. It reads incoming mail,
works out what each message is, answers the routine questions from the library's
own FAQ, and leaves everything else for a person.

It runs on your laptop. No cloud account, no API key, nothing to pay per
message, and no email leaves the machine.

I built this as a research assistant at HKU LITE Lab. What I measured, and what
broke along the way, is in `FINDINGS.md`.

## What it does

```
                 ┌── automated notification ──→ ignored
                 │
  an email ──→ classify ──→ meeting request ──→ flagged + one-line summary
                 │
                 └── enquiry ──→ search the FAQ ──→ draft a reply ──┬─→ sent
                                                                    └─→ held
```

A reply is held instead of sent if any of these are true:

- the FAQ match is too weak
- the model wrote the reply instead of quoting the FAQ
- the email is in Chinese (I haven't checked how good the Chinese replies are)
- auto-send is turned off

Every run also writes two reports.

The **gap report** lists enquiries that no FAQ entry answered. After a few weeks
that becomes a to-do list for whoever maintains the FAQ.

The **review queue** lists everything still waiting on a person, urgent ones
first. That is the only thing the urgency label is used for. The eval only
covered urgency on two emails, so I don't trust it enough to let it decide
anything. Sorting a reading list is about as much as it can safely do.

## Why there is no agent loop

Every email goes through the same steps in the same order, so there is nothing
for the model to decide while it runs. Python runs the sequence. The model only
does three text jobs: sorting, summarising and drafting.

I went this way after testing `phi-4-mini` with tools. Foundry Local lists it as
tool-capable but it didn't use them in practice (F5). Rather than fight that, I
removed the need for tools.

I think this applies to a lot of things people call agents. If you already know
the order of the steps, a fixed sequence is easier to trust, cheaper to run, and
a librarian can read it and know what will happen.

## Setup

```bash
pip3 install -r requirements.txt
cp .env.example .env
```

Then install a local model. It's free, it's Microsoft's, and it runs on your
machine:

```bash
brew tap microsoft/foundrylocal
brew trust --formula microsoft/foundrylocal/foundrylocal
brew install foundrylocal

foundry model download phi-4-mini
foundry model load phi-4-mini
foundry server status
```

The last command prints a port. Put it in `.env` as `MODEL_BASE_URL` with `/v1`
on the end. The port is different on every install, so don't copy mine.

## Running it

```bash
python3 run.py --selftest
python3 run.py --check
python3 run.py
python3 run.py --eval
```

| Command | What it does |
|---|---|
| `--selftest` | Runs the pipeline against a fake model. No real model needed. |
| `--check` | Checks the model is reachable and answering sensibly. |
| *(none)* | Processes `inbox/`. |
| `--eval` | Scores the classifier against 20 emails I labelled by hand. |

Run them in that order when something breaks. Each one tests a different layer,
so the first failure tells you where to look. If the self-test passes and the
check fails, the code is fine and the model is the problem.

## What's in here

| File | |
|---|---|
| `CODE_GUIDE.md` | Every file explained for someone new to programming. Start here. |
| `FINDINGS.md` | What I measured and what broke. |
| `pipeline.py` | The sequence. Read this first if you only read one file. |
| `run.py` | The commands above. |
| `knowledge.py` | Loads and searches the FAQ. The scoring is very simple on purpose. |
| `llm.py` | Model calls, including `pick_one`, which is worth a look. |
| `sources.py` | Where mail comes from: files (works) or Graph (never run). |
| `config.py` | Anything swappable: provider, email source, thresholds. |
| `evaluate.py` | Scores the classifier. This is the research part. |
| `selftest.py` | Runs everything against a fake model. |
| `knowledge_base/` | 23 real HKU FAQ entries as plain markdown. A librarian can edit these without touching code. |
| `eval/cases.json` | 20 labelled emails, two of them in Chinese. |

## Auto-send

It's on by default. Four things have to be true before anything sends on its
own:

1. the FAQ match scores at least 0.55
2. the reply is copied from the FAQ, not written by the model
3. the email is in English
4. `AUTO_SEND` is on

Number 2 is the one that matters. The model once invented library opening hours
and the program sent them (F10). A reply that quotes the FAQ word for word can't
invent anything.

Nothing actually leaves the machine either. With `EMAIL_SOURCE=files`, "sending"
just writes a file marked SENT, so you can read back every decision afterwards.

The threshold is the search's confidence, not the model's. A small model will
sound completely certain while making up a loan period. A match score is
something you can check later: "sent because 'Can I renew books online?' matched
at 0.667" is a sentence someone can verify.

One note on point 3. Until 28 August the language check was a model call. It
scored 60% and kept guessing "chinese" for plainly English mail, so it was
quietly holding back about 40% of the inbox for no good reason. That's fixed
(F12) and more mail is now eligible to send. I've left auto-send on anyway,
because the safety comes from points 1, 2 and 4, and from nothing leaving the
machine.

If you ever point this at a real shared mailbox, turn auto-send off first and get
someone to sign it off. A wrong reply from the library's address is a bigger
problem than a bug report.

## What I know is wrong with it

- **The search matches words, not meaning.** Ask "how long can I keep a book"
  and it won't find the entry that says "loan period". Embeddings would fix
  this, and it's the next thing I'd do.
- **The thresholds were tuned on ten emails.** That's enough to catch something
  badly broken. It isn't enough to call them calibrated.
- **The test emails are ones I wrote myself** from the public FAQ. Real
  anonymised enquiries would make the accuracy numbers mean a lot more.
- **Chinese has only been tested on two emails**, which is why it never sends
  automatically.
- **The Outlook code has never run.** `Mail.Read` consent was refused by an
  administrator in both tenants I tried, so please don't tell anyone it works.

## Where the FAQ came from

The answers in `knowledge_base/` are copied word for word from HKU Libraries,
with the source URL at the top of each file:
<https://lib.hku.hk/FAQ/> and <https://libguides.lib.hku.hk>
