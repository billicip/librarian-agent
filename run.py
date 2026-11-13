"""Entry point.

    python3 run.py --selftest  run with a fake model
    python3 run.py --check     check the model is running
    python3 run.py             process the inbox
    python3 run.py --eval      score the classifier
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import config      # noqa: E402
import knowledge   # noqa: E402
import llm         # noqa: E402
import pipeline    # noqa: E402
import sources     # noqa: E402


def check() -> None:
    """Check the model responds and can pick from a list."""
    print(f"Checking: {config.describe()}\n")

    try:
        reply = llm.ask("Reply with the single word: ready", max_tokens=10)
    except Exception as exc:                                  # noqa: BLE001
        print(f"  [1/3] model reachable ..... FAILED ({type(exc).__name__})")
        if "Connection" in type(exc).__name__:
            print(f"\nNothing is listening at {config.BASE_URL}")
            print("  foundry server status      <- check the port")
            print("  foundry model load phi-4-mini")
        else:
            print(f"\n{exc}")
        raise SystemExit(1)
    print(f"  [1/3] model reachable ..... OK  ({reply[:40]!r})")

    picked = llm.pick_one(
        "What kind of email is this?", config.CATEGORIES,
        context="From: student@hku.hk\nSubject: How do I renew a book?")
    ok = picked == "enquiry"
    print(f"  [2/3] classification ...... {'OK' if ok else 'WEAK'}  (got {picked!r}, "
          f"expected 'enquiry')")

    entries = knowledge.load()
    match = knowledge.best("How do I renew my books online?", entries)
    print(f"  [3/3] knowledge base ...... {len(entries)} entries, "
          f"best match {match.score if match else 0} on "
          f"{match.entry.question[:45] if match else 'nothing'!r}")

    print("\nReady. Run: python3 run.py")
    if not ok:
        print("Classification looked weak — run --eval to measure it properly.")


def _write_log(results: list[pipeline.Result], stamp: str) -> Path:
    """One CSV row per email."""
    path = Path(config.REPORTS_DIR) / f"log_{stamp}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "sender", "subject", "category", "topic",
                         "urgency", "language", "action", "match_score",
                         "matched_faq", "draft_method", "kb_gap",
                         "retrieval_unavailable", "notes"])
        for r in results:
            writer.writerow([
                r.email.id, r.email.sender, r.email.subject, r.category,
                r.topic, r.urgency, r.language, r.action, r.match_score,
                r.matched_question, r.draft_method, "yes" if r.kb_gap else "",
                "yes" if r.retrieval_unavailable else "", "; ".join(r.notes),
            ])
    return path


def _write_gaps(gaps: list[pipeline.Result], unreadable: list[pipeline.Result],
                stamp: str) -> Path:
    """List enquiries the FAQ couldn't answer. Unsearchable ones are listed separately."""
    path = Path(config.REPORTS_DIR) / f"kb_gaps_{stamp}.md"
    lines = ["# Knowledge base gaps", "",
             "Enquiries that no FAQ entry covered.", ""]
    if gaps:
        lines += [f"- **{r.email.subject}** — {r.email.sender} (topic: {r.topic})"
                  for r in gaps]
    else:
        lines.append("None.")

    if unreadable:
        lines += ["", "## Could not be searched", "",
                  "The search only reads English words, so these weren't "
                  "searched. Not necessarily missing from the FAQ.", ""]
        lines += [f"- **{r.email.subject}** — {r.email.sender} "
                  f"(language: {r.language})" for r in unreadable]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_queue(pending: list[pipeline.Result], stamp: str) -> Path:
    """Everything waiting on a person, sorted by urgency.

    Urgency is only used for sorting here, it was only tested on 2 emails.
    """
    path = Path(config.REPORTS_DIR) / f"review_queue_{stamp}.md"
    lines = ["# Review queue", "",
             "Everything waiting on a person, most urgent first. "
             "Urgency is the model's guess.", ""]
    if not pending:
        lines.append("Nothing waiting.")

    current = None
    for r in pending:
        if r.urgency != current:
            current = r.urgency
            lines.append(f"\n## {current}\n")
        lines.append(f"- **{r.email.subject}** — {r.email.sender}  ")
        lines.append(f"  {r.action} · {r.category}"
                     + (f" · match {r.match_score}" if r.match_score else ""))
        lines += [f"  · {note}" for note in r.notes]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def report(results: list[pipeline.Result]) -> None:
    """Write the CSV log, gap list and review queue, then print a summary."""
    Path(config.REPORTS_DIR).mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")

    gaps = [r for r in results if r.kb_gap]
    unreadable = [r for r in results if r.retrieval_unavailable]

    # Most urgent first, then by id.
    rank = {u: i for i, u in enumerate(reversed(config.URGENCIES))}
    pending = sorted([r for r in results if r.action in {"drafted", "flagged"}],
                     key=lambda r: (rank.get(r.urgency, 99), r.email.id))

    csv_path = _write_log(results, stamp)
    gap_path = _write_gaps(gaps, unreadable, stamp)
    queue_path = _write_queue(pending, stamp)

    actions = Counter(r.action for r in results)
    categories = Counter(r.category for r in results)

    print(f"\n{'─' * 58}")
    print(f"  {len(results)} emails processed")
    print("  actions:    " + ", ".join(f"{k}={v}" for k, v in actions.items()))
    print("  categories: " + ", ".join(f"{k}={v}" for k, v in categories.items()))
    if gaps:
        print(f"  KB gaps:    {len(gaps)} enquiry(ies) with no FAQ answer")
    if unreadable:
        print(f"  unsearchable: {len(unreadable)} enquiry(ies) the word-based "
              f"search could not read (not gaps)")
    print(f"\n  drafts/sent -> {config.OUTBOX_DIR.name}/")
    print(f"  log         -> {csv_path.relative_to(config.ROOT)}")
    print(f"  gaps        -> {gap_path.relative_to(config.ROOT)}")
    print(f"  review queue-> {queue_path.relative_to(config.ROOT)}"
          f"  ({len(pending)} waiting on a person)")


def process_inbox() -> None:
    print(f"{config.describe()}\n")
    if config.AUTO_SEND and config.EMAIL_SOURCE == "graph":
        print("!! AUTO_SEND is ON against a REAL mailbox. Replies will be sent.\n")

    entries = knowledge.load()
    source = sources.get_source()
    emails = source.fetch()
    if not emails:
        print(f"No emails found. Put .json files in {config.INBOX_DIR.name}/")
        return

    results = []
    for i, email in enumerate(emails, 1):
        print(f"[{i}/{len(emails)}] {email.subject[:52]}")
        result = pipeline.process(email, entries, source)
        results.append(result)
        detail = f"{result.category}"
        if result.category == "enquiry":
            detail += f"/{result.topic} match={result.match_score}"
        print(f"         -> {result.action.upper():8} {detail}")
        for note in result.notes:
            print(f"            · {note}")

    report(results)


def _cannot_reach_model(exc: Exception) -> None:
    """Short error message instead of a long traceback."""
    print(f"\nCould not reach the model at {config.BASE_URL}\n")
    print("The Foundry Local server is not running, or is on a different port.")
    print("  1. foundry server status        <- the port is assigned per install")
    print("  2. foundry model load phi-4-mini")
    print(f"  3. put the real URL in .env as MODEL_BASE_URL (currently "
          f"{config.BASE_URL})")
    print(f"\nUnderlying error: {type(exc).__name__}: {exc}")


def main() -> None:
    args = sys.argv[1:]
    try:
        if args and args[0] == "--selftest":
            import selftest
            selftest.run_selftest()
        elif args and args[0] == "--check":
            check()
        elif args and args[0] == "--eval":
            import evaluate
            evaluate.run()
        else:
            process_inbox()
    except Exception as exc:                                  # noqa: BLE001
        if "Connection" in type(exc).__name__:
            _cannot_reach_model(exc)
            raise SystemExit(1)
        raise
    except KeyboardInterrupt:
        print("\nStopped.")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
