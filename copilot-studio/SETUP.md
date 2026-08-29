# Copilot Studio build — setup order and the reasoning behind it

Written 2026-08-29, when the Copilot Studio create screen turned out to be
reachable at last (see FINDINGS.md F6). This builds the same agent as
`librarian-agent/` — Agent 1, General Enquiry — inside Microsoft's own tool, so
the two can be compared on the same 20 cases.

## 0. Publish an empty agent BEFORE building anything

Name it, save, press Publish, and record exactly what happens.

The Copilot Studio path was blocked by a **publish licence**, never by the
builder. Being able to open this screen does not mean the agent can ship. Five
minutes here either unblocks the whole comparison or produces the concrete error
message that turns F6 from "an administrator declined" into product evidence.

Do not skip this because the Publish button looks available.

## 1. Instructions

Paste the block from `INSTRUCTIONS.md`.

Note what it asks for: not a reply, but a **structured decision** —
CATEGORY / LANGUAGE / SOURCE / ACTION / REPLY. The send-or-hold choice is then
made by the flow around the agent, reading `ACTION`, rather than by the model
deciding for itself to send.

That is the same architecture as `pipeline.py` and for the same reason (F7,
F11): let the model do the text work, keep the irreversible decision in code you
can read. It also makes the two systems comparable — both emit a category, a
source and a routing decision, so the same answer key scores both.

## 2. Knowledge — and remove what is already there

**Remove the "Search all websites" chip.** It ships enabled. An agent that can
search the whole web will answer library policy questions from anywhere it
finds an answer, which destroys the one property this design depends on: that
every factual sentence is traceable to an HKU FAQ entry. This is the single
most important setting on the page.

Then add the FAQ itself, as either:

- the 23 entries in `librarian-agent/knowledge_base/*.md`, uploaded as a
  document, or
- the HKU Libraries FAQ pages as a website source, scoped to the library domain
  only

Prefer the uploaded document. It is the same 23 entries the Python agent uses,
which keeps the comparison honest — otherwise a difference in scores might just
mean the two systems read different source material.

## 3. Settings to change before testing

- **"Allow ungrounded responses" — off.** With it on, the model answers from
  general knowledge when the FAQ has no answer, which is precisely the F10
  failure: fluent, confident, invented.
- **"Use information from the web" — off**, for the same reason as the chip.

## 4. The email trigger

A chat agent answers when spoken to. This one has to wake on incoming mail,
which is a trigger — "when a new email arrives in a shared mailbox" for a real
library inbox, or "when a new email arrives" while testing against your own.
Set it to split on the value property so it handles one email at a time rather
than a batch.

Point it at a test mailbox first. Not the library's.

## 5. The measurement — this is the point of building it twice

Run the same 20 cases from `eval/cases.json` through it and score them with the
same answer key. The Evaluate tab is the place to try first.

That produces the first genuine like-for-like comparison in this project:

| | Python pipeline (phi-4-mini, local) | Copilot Studio |
|---|---|---|
| category | 15/20 — 75.0% | ? |
| topic | 4/8 asked — 50.0% | ? |
| language | 20/20 — 100% | ? |
| FAQ retrieval | 9/10 — 90.0% | ? |
| invented a fact | observed once (F10) | ? |
| cost | free, offline | licensed |

Whatever the numbers say, the comparison is the contribution. Nobody at HKU has
a measured answer to "should we build this ourselves or buy the Microsoft
tool?", and after this you would.

## 6. What this build cannot do, and say so plainly

The Python agent enforces a hard rule: **only a verbatim template reply may ever
be auto-sent** (F10, F13). That is enforced in code — model prose physically
cannot reach the send path.

Copilot Studio has no equivalent. Step 4 of the instructions asks the model to
choose `send` only under four conditions, but that is an instruction, and F10 is
the finding that **a prompt instruction is not a control**: phi-4-mini invented
opening hours while the correct text sat in its context and the prompt forbade
inventing them.

So the comparable safety property has to be built into the flow instead: have
the flow send only when `ACTION: send` AND `SOURCE` is not NONE, and consider
having it verify that any number in REPLY appears in the cited FAQ entry — the
same check `verify_draft()` performs.

If that verification cannot be built in the flow, then the honest position is
that this version drafts for a human and does not auto-send at all. That is a
finding, not a failure.
