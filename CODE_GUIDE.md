# Code Guide

A walk through every file, written for someone new to programming. Read it in
this order — each part builds on the one before.

---

## 1. The big picture

An email arrives. Five things happen to it, always in this order:

```
1. SORT      what kind of email is this?          the AI decides
2. SEARCH    which FAQ entry answers it?          ordinary code decides
3. WRITE     compose a reply                      copied text, sometimes AI
4. CHECK     is this reply safe to send?          ordinary code decides
5. ROUTE     send it, save a draft, or flag it    ordinary code decides
```

Only steps 1 and (part of) 3 involve AI. Everything else is normal
if-this-then-that code.

That is deliberate. **The AI is used where being wrong is cheap.** If it
mislabels an email, a human sees a draft that should have been sent — annoying,
harmless. If it invents a library policy, a student acts on false information.
So we never let it state facts.

---

## 2. The folder map

```
librarian-agent/
├── inbox/            emails coming IN            (you put files here)
├── knowledge_base/   the library's FAQ answers   (librarians edit these)
├── eval/             a marked exam for the AI    (measures accuracy)
├── outbox/           replies going OUT           (created by the program)
├── reports/          spreadsheets and summaries  (created by the program)
│
├── config.py         all the settings
├── llm.py            talking to the AI
├── knowledge.py      reading and searching the FAQ
├── pipeline.py       the five steps above  ← the important one
├── sources.py        where emails come from and go to
├── evaluate.py       marking the exam
├── selftest.py       testing without an AI
├── run.py            the thing you actually run
│
└── copilot-studio/   the same agent built in Microsoft's tool  (notes + recipe)
```

The three folders at the top are **data** — you can open and edit every file in
them. The `.py` files are **code**. Splitting them this way means a librarian
can update an FAQ answer without a programmer.

---

## 3. `config.py` — the settings

Every choice that might change lives here, so nothing is buried in the code.

**The provider block** says which AI to use and where to find it:

```python
"foundry-local": {
    "base_url": "http://127.0.0.1:52999/v1",
    "model": "phi-4-mini",
}
```

`127.0.0.1` always means *this computer*. `52999` is a **port** — think of a
building with many doors; the port number says which door to knock on. Foundry
Local picks a different door each install, which is why you had to run
`foundry server status` and correct it.

**The two numbers that control behaviour:**

```python
AUTO_SEND_THRESHOLD = 0.55   # how good a FAQ match must be to send unattended
MATCH_FLOOR         = 0.35   # below this, treat the FAQ as having no answer
```

**Why settings live in a separate file at all.** Halfway through this project,
GitHub Models — the AI service we started with — was shut down permanently.
Because everything about the provider sat in one file, switching cost two lines
instead of a rewrite. That is the whole reason this file exists.

---

## 4. `knowledge_base/` — the library's answers

Four plain text files. Nothing clever:

```
Q: How many books can I borrow?
A: Loan limits vary by patron status... Academic staff may borrow up to 400
   books for 180 days, postgraduates 180 books for 180 days...
```

Copied word-for-word from `lib.hku.hk/FAQ`, with the source URL at the top of
each file. **A librarian can open these in TextEdit and change an answer.** No
database, no admin panel, no programmer. That matters more than it sounds —
it's the difference between a tool people maintain and one that rots.

---

## 5. `knowledge.py` — searching the FAQ

### How the match score is calculated

This is the number you asked about, and it is simpler than it looks.

**Step 1 — chop both texts into words, and throw away the useless ones.**

Words like "the", "is", "can", "please", "hello" appear in every email and every
FAQ entry, so they tell you nothing. We also drop "library" and "hku" for the
same reason — in a library FAQ, *everything* says library. That list is
`STOPWORDS` in the file. Words shorter than 3 letters go too.

**Step 2 — count shared words, with the FAQ's *question* counted double.**

If your email shares a word with the FAQ *question*, that's a strong signal. If
it only shares a word with the *answer*, that's weaker. So:

```
overlap = (words shared with the question) × 2  +  (words shared with the answer)
```

**Step 3 — squash the count into a 0-to-1 score.**

```
score = overlap ÷ (overlap + 3)
```

### A real worked example

Email 017 asks: *"How many books can I borrow as a postgraduate student, and
what is the loan period?"*

After removing useless words, the email keeps:

```
books, borrow, loan, many, period, postgraduate, student
```

The FAQ entry *"How many books can I borrow?"* keeps:

```
books, borrow, many
```

- Shared with the **question**: `books, borrow, many` → **3**
- Shared with the **answer**: `books, borrow, loan` → **3**

```
overlap = 3 × 2 + 3 = 9
score   = 9 ÷ (9 + 3) = 0.75
```

0.75 is above the 0.55 threshold, so this one sends automatically.

### Why divide by `overlap + 3`?

It turns a count into a fraction that never quite reaches 1. More shared words
push the score up, but with diminishing returns:

| overlap | score |
|---|---|
| 1 | 0.25 |
| 3 | 0.50 |
| 6 | 0.67 |
| 9 | 0.75 |
| 20 | 0.87 |

Two other formulas were tried first and both failed instructively:

- **Dividing by the email's word count.** A chatty email has more words, so it
  got punished for being chatty. Every score came out tiny and nothing ever
  passed the threshold.
- **Dividing by the FAQ question's word count.** This fixed the numbers but
  broke the *ranking* — short FAQ questions like "Where can I checkout books?"
  are easy to fully cover, so they started winning every search. Correct
  retrieval fell from 9-out-of-10 to 4-out-of-10.

### The honest weakness

**It matches words, not meaning.** Ask *"how long can I keep a book"* and it
will not find the entry that says *"loan period"* — no shared words. Fixing this
means embeddings (comparing meaning mathematically), which is the clearest next
improvement to make.

---

## 6. `llm.py` — talking to the AI

Two functions.

### `ask()` — send text, get text back

Three settings on it are worth understanding, and each exists because something
went wrong:

- **`temperature=0.2`** — how much randomness. 0 is the same answer every time;
  1 is creative and unpredictable. We want boring and consistent.
- **`frequency_penalty` / `presence_penalty`** — makes repeating a word
  progressively less likely. Added after the AI got stuck echoing the same
  paragraph over and over.
- **`stop`** — a list of phrases that cut generation off immediately.

Note it retries without those settings if the AI server rejects them. Not every
server supports every option, and a slightly worse reply beats a crash.

### `pick_one()` — choose one word from a fixed list

**This is the most important idea in the file.**

The obvious way to classify an email is to ask for everything at once:

```json
{"category": "enquiry", "topic": "borrowing", "urgency": "normal"}
```

Small AI models are bad at this. They wrap the JSON in chatter, forget a field,
or invent a value you never offered — and one misplaced bracket loses
everything.

So instead we ask **one narrow question at a time**, each with a menu:

> Which library topic is this about?
> - borrowing
> - accessing
> - research
> ...
> Reply with only the chosen word.

Three small questions instead of one big one. Slower, far more reliable. On a
free local AI, "slower" costs nothing.

(It was four until language moved into ordinary code — see `detect_language`
in section 9.)

It also reads the answer forgivingly — if the AI says "The category is:
enquiry", it still finds `enquiry` — and falls back to the last option (always
the safe catch-all) rather than crashing.

### `looks_degenerate()` — catching the AI getting stuck

Small models sometimes loop, repeating a phrase until they run out of room.
This spots it: more than half the lines identical, a phrase appearing 3+ times,
or the prompt echoed back. Obvious to a human, easy to catch in code, and much
better caught here than emailed to a student.

---

## 7. `sources.py` — where emails come from

### `Email` — one email, four facts

`id`, `sender`, `subject`, `body`. It also carries `received`, the timestamp,
which is stored but not yet used by anything — the four above are what every
step actually reads.

### `FileSource` — reading from `inbox/`

Reads the `.json` files. "Sending" writes a file to `outbox/` marked `SENT`,
which is why auto-send is safe right now: **nothing actually leaves your
computer.** You can see every decision the program made by reading the folder.

### `GraphSource` — real Outlook (written, never run)

This is your question 1, so it gets its own section below.

---

## 8. What changes with real Outlook

**Short answer: the thinking is identical, the plumbing is not.**

Steps 1 to 4 — sort, search, write, check — never touch email at all. They take
a subject and a body as plain text and produce a reply as plain text. Those
steps genuinely will behave the same.

What changes is only step 5, and the getting-in step before step 1. Concretely:

| | Files (now) | Real Outlook |
|---|---|---|
| Get emails | read a folder | ask Microsoft's servers, over the internet |
| Permission | none | sign in, and an administrator must approve |
| Save a draft | write a `.md` file | create a real draft in the mailbox |
| Send | write a file marked SENT | **an email actually reaches a person** |
| Mistakes | delete the file | you cannot unsend it |

**So can we assume it will work? No — and you were right to ask.** Three things
change that have nothing to do with whether the logic is correct:

**Permission.** We already hit this wall. Reading a real mailbox needs
`Mail.Read` permission, and an administrator refused it in *both* accounts you
tried. That is not a coding problem and no amount of good code solves it.

**Real emails are messier than our samples.** Ours are clean text. Real ones
have signature blocks, legal disclaimers, forwarded chains, quoted replies,
HTML formatting, and attachments. The FAQ search counts shared words — so a
long corporate signature adds dozens of irrelevant words and drags scores down.
**This alone could change the accuracy meaningfully**, and it is untested.

**The stakes change completely.** Right now a wrong reply is a file you delete.
In real Outlook it is an email in a student's inbox, from the library, that
cannot be recalled. That's why only the copy-word-for-word replies are allowed
to send unattended.

### And yes — connectors and tools matter

You're asking the right question. Here's the honest picture:

**Reading mail** needs Microsoft Graph — Microsoft's doorway to Outlook,
Calendar, Teams and SharePoint. Getting in needs: an app registration (many
universities block this for students), the right permissions, and **an
administrator's approval**. That last one already stopped us.

**The FAQ** currently sits in text files. In production it would more likely
live in SharePoint, which is another connector and another permission.

**Copilot Studio** exists precisely to make all of this someone else's problem.
Its "connectors" are pre-built, permission-managed doorways to Outlook,
SharePoint and the rest. You do not write any of this plumbing — you pick
Outlook from a menu.

Which is exactly the trade-off in your research: build it yourself and own every
piece of plumbing, or use Copilot Studio and get the plumbing free but need a
licence you have not been given.

**What we can and cannot claim.** Verified: the sorting, searching, writing and
checking logic works on a free local AI. Not verified: that it survives real
mailbox permissions, real messy email, or real consequences. Keep those apart
in the report — the first is a result, the second would be a guess.

---

## 9. `pipeline.py` — the five steps

The file to read if you only read one.

### `classify()`

**Three** calls to `pick_one()` — category, topic, urgency — plus one answer
worked out in Python. It skips the topic question when the email isn't an
enquiry: asking "which library topic is this spam about?" has no sensible
answer, so don't ask.

### `detect_language()` — the fourth answer, without the model

Language used to be a fourth `pick_one()` call, and it was the worst-scoring
field in the whole eval: 12/20, and wrong in one direction — it kept saying
`chinese` about plainly English mail. Because `process()` refuses to auto-send
anything non-English, that one bad label was quietly switching off auto-send on
about 40% of the inbox.

So we stopped asking. The function now counts characters: if a tenth or more of
the letters are Chinese-script, it's `chinese`; otherwise `english`. It scores
20/20 on the same cases (FINDINGS.md F12).

The thing to take from this, and it is the project's whole argument in one
function: **"what writing system is this?" has a right answer that code can
compute, so code should compute it.** Save the model for questions where there
is no such rule — "is this email a complaint or a booking request?" has no
character test.

The honest catch: it detects a *writing system*, not a language. A French
email has no Chinese characters in it, so it comes back `english`. That hole is
written down in F12 rather than papered over.

### `template_reply()` — the safe path

Builds a reply **with no AI at all**:

```
Thank you for contacting HKU Libraries.

[the FAQ answer, copied exactly]

More detail: [source link]

If this does not answer your question, please reply and a librarian
will follow up.

HKU Libraries
```

Copied text cannot be invented text. It reads a bit stiff. Stiff and true beats
smooth and false when a student is going to act on it.

### `verify_draft()` — the guard

When the AI *does* write a reply, this checks it before anyone sees it:

1. Is it looping? (`looks_degenerate`)
2. **Does every number, time and price in the reply also appear in the FAQ?**

Check 2 is the important one. It exists because the AI wrote *"The Main Library
operates from 9 am to 5 pm"* — completely invented — and the program emailed
it. Now "9" and "5" would be checked against the FAQ text, not found, and the
reply thrown away.

It is deliberately strict. A false alarm costs a human a glance at a draft. A
miss sends a student to a closed library.

### `draft_reply()` — try the AI, fall back if it fails

Ask the AI → verify → if it fails, use the template instead. The fallback is
**not an error**. On a small local model it fires often, and that's the system
working.

It returns *how* the reply was made, which ends up in the spreadsheet so you can
count it.

### `process()` — putting it together

```
classify
├─ automated notification → ignore, stop here
├─ meeting request        → one-line summary, flag for a human
├─ internal / needs human → flag for a human
└─ enquiry                → search FAQ → draft → decide
```

Four conditions must **all** hold before anything sends by itself:

1. FAQ match at 0.55 or above
2. `AUTO_SEND` switched on
3. Email is in English (Chinese quality is unmeasured, so never unattended)
4. **The reply is a template, not AI-written**

Fail any one and it becomes a draft with a note explaining which.

---

## 10. `evaluate.py` — marking the exam

`eval/cases.json` holds 20 emails with the **correct answers written by hand**.
The program classifies each and compares.

That produces a real number — *"17 of 20 correct"* — instead of an impression.
It also prints **confusion pairs**: not just "85%" but "it reads internal_admin
as enquiry four times", which tells you what to fix.

The hand-written labels matter more than the code. A wrong label silently
punishes a correct AI.

### Why some emails have no topic label, and why topic is scored twice

You only mark what the answer key answers. All 20 cases carry a `category` and a
`language`, so those are scored out of 20. Only 13 carry a `topic` — the spam,
the meeting requests, the automated notice and the internal mail aren't
enquiries, and "which library topic is this spam about?" has no answer. Only 2
carry an `urgency`, which is why 2/2 tells you nothing.

Topic gets two rows in the results:

```
  topic       4/13   30.8%     every labelled case
  topic*      4/8    50.0%     only where the model was actually asked
```

The reason is worth understanding, because it is a trap that catches a lot of
evaluations. `pipeline.classify()` only asks for a topic once it has decided the
email is an enquiry. So when the *category* comes out wrong, the topic question
is never asked at all and the field defaults to `other`. Scoring that as a topic
mistake counts one category mistake twice, and drags down a number that is
supposed to describe something else. `classify()` returns `topic_asked` so the
eval can tell the two cases apart.

**50% describes the topic classifier. 30.8% describes the topic classifier plus
everything that went wrong before it.** Both are printed on purpose, so neither
can be quoted alone.

(Alex found this by reading `cases.json` and asking why some emails had no
topic. Reading your own test data is worth an hour of it.)

---

## 11. `selftest.py` — testing without an AI

Replaces the real AI with a fake one that returns fixed answers, then runs
everything. One second, no AI needed, no network.

The fake deliberately reproduces **both real failures** — the invented opening
hours and the looping reply — and the test asserts they get caught. So those
bugs cannot come back silently.

This is why, when your run failed earlier, you knew instantly the problem was
outside the code: the self-test still passed.

---

## 12. `run.py` — the thing you run

```
python3 run.py --selftest    test the logic, no AI needed
python3 run.py --check       is the AI reachable and sensible?
python3 run.py               process the inbox
python3 run.py --eval        mark the exam
```

Run them in that order when something breaks. Each isolates a different layer,
so the first one that fails tells you where the problem is.

It also writes three files per run: a CSV of every decision, a **gap report** of
enquiries no FAQ answered — which over time becomes a to-do list of FAQ entries
worth writing — and a **review queue** listing everything still waiting on a
person, most urgent first.

The review queue is the only place `urgency` is used, and that is a decision
worth understanding rather than a leftover. Urgency is a model judgement, and
the eval measured it on two cases, which is to say it is not really measured at
all. So it orders a list a librarian reads top to bottom: if it is wrong, an
item gets read in the wrong order. It gates no send decision and it must not.
An unmeasured signal has no business deciding what leaves the building — same
rule as everywhere else here.

---

## 13. If you change one thing, change this

Replace the word-matching search with **embeddings** — comparing meaning rather
than spelling. It is the single clearest improvement, and everything else is
already built to accommodate it: only `knowledge.py`'s `search()` would change.
