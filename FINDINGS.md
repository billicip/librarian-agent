# Findings — Librarian Email Agent

Evidence levels: **Observed** (we ran it) · **Documented** (vendor primary
source) · **Reported** (secondary source) · **Inferred** (our conclusion) ·
**Untested** (believed, not verified).

See also `../OUTPUT/findings.md` for F1–F5 (provider landscape, tool calling).

---

## F6 — Building outside Copilot Studio at HKU is blocked by access policy, not technology
**2026-08-24 · Observed · Confirmed**

Three independent attempts to build a working agent outside Copilot Studio,
three walls. None technical:

| Attempt | Result |
|---|---|
| Publish an agent in Copilot Studio | *"You currently do not have a user license that allows you to publish"* |
| Register an app in the Azure portal (HKU account) | HTTP 401, `subscriptionId` empty |
| Consent `Mail.Read` in Graph Explorer | Administrator restriction — **in two separate tenants**, HKU and a Microsoft Student Ambassadors tenant |

Notably, Copilot Studio agent *creation, configuration and testing* all worked.
Only publish was refused. And Graph authentication itself succeeded (`GET /me`
returned a profile) — it was the mail scope specifically that was blocked.

**Implication.** For a student researcher, the binding constraint on this
project is institutional permission, not capability. Every technical component
was obtainable free; none of the access was. This is the central finding for
the comparison study, and it is what makes the Copilot Studio publish licence a
critical path rather than a convenience.

**Cookbook relevance.** A guide that says "register an app and call Graph"
will fail for most staff readers at step one. Any recipe involving M365 data
needs to state its permission prerequisites up front, and name who grants them.

---

> **Update 2026-08-29 — the builder is reachable; publishing is still untested.**
>
> Alex opened the Copilot Studio agent builder at
> `copilotstudio.microsoft.com/environments/Default-.../agents/new`, signed in
> on the `connect.hku.hk` tenant, with a model picker offering Claude Opus 5.
> The create screen, Knowledge, Tools, Channels and a Publish button are all
> visible.
>
> **Tested the same day. F6 is confirmed, and the wall is earlier than we
> thought.** The agent was filled in completely — name, the full instructions,
> "Search all websites" removed, and the 23-entry FAQ document attached. On
> "Add to agent", Copilot Studio returned:
>
> > **You don't have permission to create agents.** Ask your admin to grant you
> > the right role, then try again. *User license not found.*
>
> > **You don't have permission to upload files to this agent.** Ask your admin
> > to grant you the right role, then try again. *User license not found.*
>
> Screenshots: `copilot-studio/F6_copilot_studio_license_error.png` and
> `F6_copilot_studio_full_screen.jpg`.
>
> Three things this changes:
>
> 1. **The block is on `create`, not `publish`.** We had recorded it as a
>    publish-licence refusal. The product says an unlicensed user cannot create
>    an agent at all. Nothing can be saved, so nothing can be measured.
> 2. **The entire builder works right up to the point of persistence.** Every
>    field accepted input, the model picker offered Claude Opus 5, the knowledge
>    dialog accepted the upload. Only the server-side write failed. A person
>    evaluating Copilot Studio by clicking around would reasonably conclude they
>    had access.
> 3. **The evidence is now first-hand.** F6 previously rested on remembered
>    refusals. It now rests on the product's own message, with a timestamp and a
>    screenshot. `User license not found` is a specific, checkable claim someone
>    in HKU IT can act on.
>
> **The comparison against the Python agent therefore cannot be run** — not
> "has not been run yet". Every number in F11 exists because the local model
> needed no permission from anyone. That is the sharpest statement of F6 the
> project has: the free offline prototype produced measurements; the licensed
> enterprise tool produced an error dialog.
>
> Build materials are complete and waiting in `librarian-agent/copilot-studio/`
> — INSTRUCTIONS.md, SETUP.md and the FAQ document. If Brian gets the licence
> granted, the build is about ten minutes of clicking, and SETUP.md §5 has the
> comparison table ready to fill in.

## F7 — A fixed pipeline removes the need for tool calling entirely
**2026-08-24 · Observed · Confirmed**

F5 established that `phi-4-mini` does not use tools in practice. Rather than
change model, we changed architecture: because every step of this task has a
known position in the sequence, Python can control the order and the model can
be restricted to text tasks it handles reliably.

*Observed:* the full pipeline — classification into 5 categories, FAQ
retrieval, reply drafting, routing — runs on `phi-4-mini` with no tool calling
at any point. Self-test passes; all routing decisions correct.

**Implication.** "This model can't do tool calling" is often the wrong problem.
The right question is whether the task actually requires runtime decisions. For
the four agents in the Librarian AI Agent draft, none do.

---

## F8 — Small models are more reliable answering one narrow question at a time
**2026-08-24 · Observed (design) + Untested (quantified) · PROVISIONAL**

The natural approach to classification is one call returning JSON with all
fields. Small models handle this poorly — prose around the JSON, missing
fields, values outside the allowed set, and one malformed brace loses
everything.

We instead make one call per field, each offering a fixed menu and demanding a
single word, parsed leniently with a safe fallback. Cost: 4 calls per email
instead of 1. On a free local model, that cost is time only.

**Untested:** we have not run the JSON-blob variant head to head, so the size
of the difference is unmeasured. The design is chosen on well-known small-model
behaviour, not on our own numbers. Worth a direct comparison — it would make a
crisp cookbook recipe.

---

## F9 — Naive keyword FAQ retrieval reached 9/10 on a small labelled set
**2026-08-24 · Observed · PROVISIONAL (n=10)**

Word-overlap scoring, no embeddings, no vector store, retrieved the correct FAQ
entry for 9 of 10 labelled enquiries. With the send threshold at 0.55, 8 would
auto-send and the single wrong match scored 0.5 — **below threshold, so it would
have been held for review.** The failure mode was safe.

Two scoring approaches were tried and rejected, both instructive:

- Normalising by the *query's* length made all scores tiny (a chatty email is
  punished for being chatty). Ranking was unaffected — the divisor is constant
  per query — but no score cleared a usable threshold.
- Normalising by the *FAQ question's* length fixed magnitudes and broke
  ranking, rewarding short entries. Retrieval fell 9/10 → 4/10.

A saturating function on the raw overlap count kept the working ranking and
produced usable magnitudes.

**Limitation, stated plainly:** n=10, synthetic cases, thresholds tuned on the
same ten. This is enough to reject something broken and not enough to call
calibrated. The known weakness is that it matches words, not meaning.

**Implication.** Worth reporting that the naive baseline is decent, because the
reflex is to reach for embeddings immediately. Establish the simple baseline
first — you may not need the machinery, and you cannot tell whether embeddings
helped without it.

---

## Open

- [x] Run `--eval` against `phi-4-mini` and record classification accuracy here — **F11**
- [x] Does `phi-4-mini` classify Chinese enquiries correctly? Yes (2/2) — but it also
      labels English mail as Chinese 8 times in 20. See F11.
- [ ] Fix the language classifier (script detection in Python) — F11, blocks auto-send
- [ ] Score reply *quality*, not just classification — the gap F10 exposed
- [ ] Head-to-head: one JSON call vs four single-word calls (completes F8)
- [ ] Re-tune thresholds on real enquiry data if any becomes available
- [ ] Compare against the same task built in Copilot Studio, once publishable

---

## F10 — A small local model invented library opening hours, and auto-sent them
**2026-08-27 · Observed · Confirmed**

First live run against `phi-4-mini` via Foundry Local. Two distinct failures in
the same batch of 12 emails.

### Failure 1 — invented facts (the serious one)

Enquiry: *"what time does the Main Library open during reading week?"*

The FAQ says only that hours vary by period and to check the Libraries
homepage. The model replied, and this was **auto-sent**:

> "The Main Library operates from 9 am to 5 pm on Mondays and Tuesdays
> (Reading Week days 2 and 3)."

Every specific in that sentence is invented. There are no such hours in the
source. The system prompt explicitly instructed *"Never invent policies,
numbers, dates, opening hours or fees."* The instruction was ignored.

Note what did NOT fail: retrieval found the correct FAQ entry and scored it
0.7. The pipeline worked. **The model fabricated while holding the correct
source text in its context.**

### Failure 2 — degenerate repetition

A borrowing enquiry produced the prompt's own "Reference information: --- ..."
block echoed back and repeated until the token budget ran out. No reply, just a
loop.

### Why this matters more than the accuracy number

A prompt instruction is not a control. "Never invent numbers" reads like a
constraint and behaves like a suggestion — a small model will violate it while
looking entirely fluent and confident. Fluency is not calibrated to accuracy,
so **the reply that gets auto-sent is exactly the one that reads most
convincingly.**

### What we changed

1. **Templates are now the safe default.** A reply is assembled in Python from
   the FAQ answer **quoted verbatim**. Zero invention is possible because no
   generation occurs. Reads stiffly; is correct.
2. **Generated drafts must pass verification.** Every number, time and price in
   a model-written draft must appear in the source text, plus a degeneration
   check. Failure falls back to the template.
3. **Only template replies may be auto-sent.** Model-written prose is always
   held for a human, however high the retrieval score.
4. **Repetition controls** — `frequency_penalty`, `presence_penalty` and `stop`
   sequences, with a retry for endpoints that reject them.
5. **Both failures are now regression tests** in `selftest.py`, replayed on
   every run.

### Cookbook relevance — arguably the most important entry here

The instinct is to use an LLM for the whole task. The safer pattern is to use
it **only where being wrong is cheap**:

| Step | Who does it | Why |
|---|---|---|
| Classify into a fixed list | Model | Wrong label = misrouted mail, recoverable |
| Retrieve the FAQ entry | Python | Deterministic and auditable |
| State the policy | **Template, verbatim** | **Wrong = a student acts on false information** |
| Polish the wording | Model, then verified | Nice to have, never trusted |

Guidance for any recipe that answers users from a knowledge base: **retrieve
with code, answer with the source text, and use the model for classification
and phrasing — not for facts.**

### Honest limitations

- The fact-checker matches numbers, times and prices. Invented *non-numeric*
  policy ("you may renew unlimited times") would pass. Not solved.
- Untested whether a larger model (`qwen3-8b`, or GPT-4o via Azure OpenAI)
  hallucinates less here. Plausible, unmeasured — and the mitigation should
  stay regardless, since it costs nothing.
- n=12 emails, one run.

---

## F11 — Measured classification accuracy: the deterministic step beat every model-judged one
**2026-08-28 · Observed · Confirmed (n=20, single run)**

First full run of `python3 run.py --eval` against `phi-4-mini` on Foundry Local,
scored on the 20 hand-labelled cases in `eval/cases.json`.

| Field | Score | Judged by |
|---|---|---|
| category | 15/20 — **75.0%** | model |
| topic | 4/12 — **33.3%** | model | *(corrected 2026-08-29 — see below)*
| urgency | 2/2 — 100% | model |
| language | 12/20 — **60.0%** | model |
| **FAQ match** | 9/10 — **90.0%** | **Python (keyword search)** |

### The headline: code outperformed the model on the task it owns

The single deterministic step scored higher than any field the model judged.
This is the same shape as F10, arrived at from the opposite direction: there we
found the model inventing facts while the retrieval was correct; here we find
the retrieval measurably more accurate than the model's own labelling. Taken
together they make the case for the division of labour in F10's table —
**retrieve with code, classify with the model, and never let the model supply a
fact.**

(Retrieval's 90% is the same 9/10 reported in F9, now re-run against the current
scoring function rather than re-derived — it is a confirmation, not an
independent second measurement.)

### Category — 75%, and every error failed in the safe direction

All 5 category errors moved mail *toward* human review, never away from it:

```
enquiry -> needs_human      (4x)   001-renew, 005-remote, 015-urgent, 020-recall
enquiry -> meeting_request  (1x)   011-room
```

Zero errors in the dangerous direction (something that needed a human being
labelled a routine enquiry). The cost is unnecessary human work; the cost of
the opposite would be an unreviewed auto-send. Given the choice, this is the
error distribution to have — though it is an observation about this run, not a
property the design guarantees.

### Language — 60%, and this one is an actual bug with a behavioural consequence

Eight plainly English emails were labelled `chinese`. Both genuinely Chinese
cases were labelled correctly. The classifier is therefore not confused in both
directions — it is **biased toward answering `chinese`**.

This matters because `pipeline.process()` blocks auto-send for any non-English
mail (Chinese drafting quality being unverified). So a mislabel here silently
converts a sendable reply into a held one. On this set that is **8 of 20 emails
— 40% of the mail — losing auto-send for a reason unrelated to the reply's
quality**, and doing so invisibly: the log records `language=chinese` and the
held draft looks like a normal cautious hold.

It fails safe, but it defeats the feature. Likely fixes, in order of effort:
detect script in Python (a CJK character-range test is deterministic and would
almost certainly beat 60%), or reword the `pick_one` prompt, which currently
appears to prime the less common answer.

> **Superseded 2026-08-28.** The first fix was made the same day. This field is
> no longer judged by the model at all. See **F12**. The 60% above stands as the
> record of what the model scored, not as the current behaviour.

### Topic — 33%, barely above chance

Four correct out of twelve, across six options. Random guessing scores ~17%, so
the model is doing something, but not much. Topic is used only for the
knowledge-base gap report, so a wrong label degrades a report rather than a
reply — but the gap report is one of the deliverable's better ideas, and at 33%
its groupings are not trustworthy.

Notably the errors are mostly `-> other` (5 of 8), which suggests the model is
defaulting when uncertain rather than choosing wrongly with confidence.

> **Corrected 2026-08-29 — 33% was measuring two different failures at once.**
>
> Found by Alex reading `eval/cases.json` and asking why some emails carried no
> topic label. Two problems came out of that question.
>
> First, `015-urgent` was labelled `enquiry` with no topic — the only enquiry in
> the set without one, and an oversight rather than a decision. It is a database
> access problem, so it is now labelled `research`. That takes the topic
> denominator from 12 to 13.
>
> Second, and worse: `pipeline.classify()` only asks the model for a topic once
> it has decided the email is an `enquiry`. When the category is wrong, the
> topic question is **never asked** and the field defaults to `other` — which
> the eval was then scoring as a topic error. Four of the eight topic failures
> (`001-renew`, `005-remote`, `011-room`, `020-recall`) are category mistakes
> being counted a second time in the topic column.
>
> `classify()` now returns `topic_asked`, and `evaluate.py` reports both:
>
> ```
>   topic       4/13   30.8%     every labelled case
>   topic*      4/8    50.0%     only where the model was asked
> ```
>
> **50% is the number that describes the topic classifier.** 30.8% describes the
> classifier plus the category errors upstream of it. Both are printed, with the
> difference explained in the output, so neither can be quoted without the other.
>
> The headline got worse (33% → 30.8%) because a label was added that the model
> gets wrong. That is the honest direction for a correction to move.
>
> The conclusion is unchanged: 50% across six options is still poor, and the gap
> report's groupings still cannot be trusted at that rate.

### Urgency — 100%, and meaningless

n=2. Also, urgency is classified and logged but **read by no routing decision
anywhere in the pipeline** (verified by grep). It is an unfinished feature, not
a working one, and should not be presented as a capability.

### Limitations

- n=20, and per-field denominators are smaller still (topic n=12, urgency n=2).
- Cases are synthetic, written from the public FAQ by the same person who wrote
  the classifier prompts. Real anonymised enquiries would be far more defensible.
- Single run, single model, no temperature variation — these numbers have no
  error bars. **Updated 2026-08-28:** the eval was re-run after the F12 change
  and category, topic, urgency and FAQ match all returned identical totals and
  identical per-case failures. `pick_one` runs at `temperature=0.0`, so the
  harness is reproducible on this machine; that is not the same as the numbers
  being stable across different cases or models.
- The eval scores classification only. It does not score reply quality, which
  after F10 is the thing most worth measuring and the thing we still cannot.


---

## F12 — Language detection moved from the model to Python: 12/20 -> 20/20
**2026-08-28 · Observed · Confirmed (full `--eval` re-run); NOT calibrated on mixed-language mail**

### What changed

`pipeline.classify()` no longer asks the model what language an email is
written in. `pipeline.detect_language()` counts characters instead: if
Chinese-script characters (ideographs plus the CJK punctuation and fullwidth
blocks) make up 10% or more of the letters in the subject and body, the email
is `chinese`; otherwise `english`. The sender line is excluded, because an
email address is Latin script whatever the message is written in.

The language list moved from an inline literal in `pipeline.classify()` into
`config.LANGUAGES`, for consistency with `CATEGORIES` and `TOPICS`.

> **Reversed 2026-08-29** during a cleanup pass. `config.LANGUAGES` turned out to
> be imported by nothing: `CATEGORIES` and `TOPICS` are menus handed to the model
> and belong in configuration, but language is no longer chosen from a menu, so
> the values now live in `detect_language` where they are computed. Consistency
> with the other lists was the wrong reason to move it.

### The measurement, and exactly how strong it is

| Judged by | Score on the same 20 labelled cases |
|---|---|
| model (`llm.pick_one`), F11 | 12/20 — 60.0% |
| `pipeline.detect_language`  | **20/20 — 100%** |

Confirmed by a full `python3 run.py --eval` re-run on 2026-08-28, after the
change, on `phi-4-mini` via Foundry Local:

```
  category   15/20   75.0%
  topic       4/12   33.3%
  urgency     2/2   100.0%
  language   20/20  100.0%
  faq match   9/10   90.0%
```

One qualification, and it is material:

**The eval set is trivially separable and therefore an easy test.** Every
English case contains zero Chinese characters; both Chinese cases contain zero
Latin ones. Ratios are 0.000 or 1.000 with nothing in between, and the set
contains **no mixed-language email at all**. 20/20 here shows the test is not
broken. It does not show the 10% threshold is calibrated — that number was
chosen by reasoning, not fitted to data, and real HKU enquiry mail mixes scripts
routinely.

### Two things the re-run showed that were not the point of it

**Every other number came back byte-identical to F11** — same three totals, same
14 failures, same five category confusions on the same five case ids, two days
apart. `pick_one` runs at `temperature=0.0`, so this is what determinism looks
like, and it upgrades F11 from "single run, no error bars" to reproducible on
this machine with this model. It says nothing about how the numbers would move
on different cases or a different model; it says the harness is not noisy, which
is the precondition for trusting any future comparison against Copilot Studio.

**The run got cheaper.** Classification was four model calls per email and is
now three. On the 24-email inbox the self-test went from 112 calls to 88 — 21%
fewer — while scoring better. Locally that buys seconds; against a metered
endpoint it would buy money. Deleting a model call is the only optimisation that
improves accuracy and cost at the same time.

### Behavioural consequence

The 8 English emails F11 found mislabelled `chinese` are now labelled
`english` — all 20 cases are now correct — which removes the non-English block
on auto-send for that 40% of the set. Auto-send still requires the other three conditions (match score above
threshold, `AUTO_SEND` on, and a verbatim template reply), so this restores
*eligibility*, not sending.

Measured on the full 24-email inbox, before and after, same model, same inbox:

| | before (2026-08-28) | after (2026-08-29) |
|---|---|---|
| labelled `chinese` | **13 of 24** | **1 of 24** (correct) |
| auto-sent | **1** | **4** |
| held as drafts | 15 | 12 |
| flagged for a human | 7 | 7 |
| ignored | 1 | 1 |

Only one of those 24 emails is actually in Chinese. Thirteen were being held for
a language they were not written in. "Auto-sends went from 1 in 24 to 4 in 24"
is the sentence to put in front of a supervisor — it is the deliverable's
behaviour, not a classifier score.

### The limitation, stated plainly

**This detects a writing system, not a language.** English against French is
invisible to it: a French email scores zero Chinese characters and is labelled
`english`, making it auto-send eligible. That is a genuine regression against
the model, which could in principle have caught it — at 60% accuracy, and
biased toward `chinese`, it mostly did not, but "mostly did not" is not "could
not". A third value, `other`, is **unreachable** — a character test cannot produce it.

Observed behaviour on hand-written edge cases (direct calls, not in the eval
set, so not scored above):

| Input | Result |
|---|---|
| English email containing one Chinese personal name | `english` |
| Short all-Chinese enquiry | `chinese` |
| Half English, half Chinese | `chinese` |
| French | `english` — the known hole |
| Empty string | `english` |

Rejected: `langdetect` / `langid`. Both add a dependency, both are statistical
and so can be wrong in ways a character range cannot, and both are more
machinery than one question about writing system needs. If non-CJK foreign mail
turns out to matter at HKU, that is the point to revisit — with a case in the
eval set first.

### Why this belongs next to F10 and F11

It is the third instance of the same pattern, and the first one applied rather
than observed. F10 found that a model will invent a fact the prompt forbids it
to invent. F11 measured that the one deterministic step outscored every
model-judged one. F12 moved a step across that line and the score went up.

The rule the project has arrived at: **ask the model only where there is no
right answer for code to compute.** Writing system has one. Category does not.


---

## F13 — Auto-send fires only when the model fails, and that is structural
**2026-08-29 · Observed · Confirmed (n=24, single run) + provable from the code**

Four of 24 emails were auto-sent in the post-F12 run. Every one of them was sent
because the model's draft had been **rejected**:

```
004-printing  0.571  template (model more than half the lines are duplicates)
015-return    0.700  template (model phrase repeated 3x: 'returns book returns book...')
017-limit     0.750  template (model phrase repeated 3x: 'the reference text word for word')
023-search    0.824  template (model phrase repeated 3x: 'repeat or repeat or repeat or')
```

The eleven enquiries where the model produced clean, verifiable prose were all
**held** — `draft_method` is plain `"model"` and the F10 rule refuses to send
model-written text.

### This is not a coincidence of one run

Read `draft_reply()` and `process()` together. When a FAQ entry matches, the
pipeline asks the model first. If `verify_draft()` passes, `draft_method` is
`"model"` — and `safe_to_send` requires it to start with `"template"`, so the
reply is held. The only route to a template reply on a matched enquiry is
`verify_draft()` **failing**. Therefore:

> On any enquiry with a FAQ match, auto-send is reachable **only** when the
> model's draft fails verification.

The pipeline sends when the model is at its worst and holds when it is at its
best. Nothing here is unsafe — every sent reply was verbatim FAQ text, which is
F10 working exactly as designed. But it means the **auto-send rate is really the
model's failure rate**, and that has three consequences worth stating:

1. **The automation rate is not a property we chose.** It tracks how often
   `phi-4-mini` degenerates. Nobody designed 4-in-24.
2. **A better model would automate less.** Swap in something that rarely loops
   or invents, and `verify_draft()` stops firing, templates stop being built,
   and the send count falls toward zero. Improving the model *reduces* the
   automation — the exact opposite of what anyone would predict.
3. It is invisible in the summary line. `sent=4` reads like success. Only
   `draft_method` in the CSV says why.

### The fix, and it is untested

Invert the default in `draft_reply()`: build the **template first** and treat
the model as optional polish that must earn its place, rather than trying the
model first and falling back. Then the send decision depends on retrieval
confidence — which is measured at 90% — instead of on model failure, which is
measured at nothing.

This is a proposal. It has not been implemented or run, and the interaction with
`AUTO_SEND_THRESHOLD` would need re-checking, because far more replies would
become send-eligible than the 4 seen here.

### Cookbook relevance

A safety rule and a routing rule were composed without anyone noticing they had
been coupled. Each is defensible alone: *never send model prose* (F10) and
*fall back to a template when generation fails*. Together they silently made
"the model broke" the precondition for acting automatically. **Check what your
guardrails select for, not just what they block.**

---

## F14 — Every Chinese enquiry is reported as a knowledge-base gap, and none of them are
**2026-08-29 · Observed · Confirmed (deterministic, provable from the code)**

In the same run, `009-chinese` (借書問題 — "how many books may a postgraduate
borrow, and for how long?") was logged as a knowledge-base gap and written into
`reports/kb_gaps_*.md` as a candidate for a new FAQ entry.

The FAQ already answers it. The same question in English (`017-limit`, "How many
books can I borrow") matched at 0.75 and was auto-sent in that very run.

### Cause

`knowledge._tokens()` is `re.findall(r"[a-z0-9]+", text.lower())`. Chinese text
contains no `[a-z0-9]` runs, so it tokenises to the empty set, `search()`
returns nothing, `best()` returns `None`, and `process()` records `kb_gap`.

This is not a probabilistic weakness. **Every all-Chinese enquiry produces a
false gap, always, whatever the FAQ contains.** The gap report — one of the
better ideas in the deliverable, and the part that improves the library rather
than just serving it — is systematically wrong about an entire language.

### Why it stayed hidden

The gap report was only ever eyeballed on English mail, where it behaves. And
the F12 language fix, by correctly identifying `009-chinese` as the one genuinely
Chinese email, made the false gap easy to see for the first time — before that,
13 emails were being mislabelled `chinese` and the noise buried it.

### Options

- **Bound the claim.** Log non-Latin enquiries as `retrieval unavailable` rather
  than `knowledge base gap`. Honest, no new capability. **Done 2026-08-29** —
  `knowledge.searchable()` reports whether the query tokenises to anything at
  all, `pipeline.Result` carries `retrieval_unavailable` alongside `kb_gap`, and
  the gap report lists these under "Could not be searched" with an explicit
  instruction not to read them as missing FAQ entries. This fixes the false
  claim. It does not answer the enquiry — a Chinese email still gets a template
  saying a librarian will follow up, which remains correct behaviour and remains
  the reason Chinese mail is never auto-sent.

Still not implemented:
- **Segment the FAQ by language.** Requires Chinese FAQ text, which HKU
  Libraries publishes; a real task, not a code fix.
- **Character n-gram matching for CJK.** Chinese has no spaces, so word
  tokenising cannot work regardless of language support.
- **Embeddings**, which would handle both scripts — still the obvious next step
  (F9), still unmeasured.

The first option is the honest minimum, and until one of them is done the gap
report should carry the caveat wherever it is shown.
