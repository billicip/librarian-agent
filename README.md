# Librarian Email Agent

Email assistant for the HKU Libraries mailbox. It sorts incoming emails,
answers common questions using the library FAQ, and leaves the rest for a
librarian.

Runs locally with `phi-4-mini` on Foundry Local. No API key, no cloud.

Built at HKU LITE Lab as a student research assistant.

## How it works

```
email -> classify -> automated      -> ignored
                  -> meeting        -> flagged + summary
                  -> enquiry        -> search FAQ -> draft reply -> sent / held
```

The order is fixed in Python, there's no agent loop. The model only does
classification, summaries and drafts. I tried tool calling with phi-4-mini
first but it didn't really use the tools.

A reply is only sent automatically if:

1. the FAQ match score is at least 0.55
2. the reply quotes the FAQ directly (not written by the model)
3. the email is in English
4. `AUTO_SEND` is on

Rule 2 is there because in an early run the model made up library opening
hours and the reply got sent. With the default file source nothing is
actually emailed, "sent" replies are just written to `outbox/`.

Each run also writes a CSV log, a list of questions the FAQ didn't answer,
and a review queue for whatever still needs a person.

## Results

On 20 hand-labelled test emails:

| | Score |
|---|---|
| Category (model) | 15/20 |
| FAQ match (keyword search) | 9/10 |
| Language, model | 12/20 |
| Language, Python character check | 20/20 |

All 5 category mistakes sent mail to a human instead of auto-replying.

## Setup

```bash
pip3 install -r requirements.txt
cp .env.example .env

brew tap microsoft/foundrylocal
brew trust --formula microsoft/foundrylocal/foundrylocal
brew install foundrylocal
foundry model download phi-4-mini
foundry model load phi-4-mini
foundry server status
```

Put the port from `foundry server status` into `.env` as `MODEL_BASE_URL`
(e.g. `http://127.0.0.1:PORT/v1`).

## Usage

```bash
python3 run.py --selftest   # fake model, no setup needed
python3 run.py --check      # check the model is running
python3 run.py              # process inbox/
python3 run.py --eval       # score against eval/cases.json
```

## Files

| | |
|---|---|
| `pipeline.py` | the main steps |
| `llm.py` | model calls |
| `knowledge.py` | FAQ loading and search |
| `sources.py` | reads emails from files (Outlook version written but untested) |
| `config.py` | settings |
| `evaluate.py` | scoring |
| `selftest.py` | test with a fake model |
| `run.py` | entry point |
| `knowledge_base/` | 23 FAQ entries from lib.hku.hk |
| `inbox/` | 24 test emails |
| `eval/cases.json` | 20 labelled emails |

## Limitations

- Search matches words, not meaning. "How long can I keep a book" won't find
  "loan period". Embeddings would be the next step.
- Thresholds were tuned on 10 emails.
- I wrote the test emails myself based on the public FAQ.
- Chinese was only tested on 2 emails, so it never auto-sends.
- The Outlook (Graph) code never ran because Mail.Read permission was blocked
  by admins. I also couldn't build the Copilot Studio version because of
  licensing.

FAQ content is from <https://lib.hku.hk/FAQ/> and <https://libguides.lib.hku.hk>.
