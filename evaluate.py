"""Score the classifier against the hand-labelled emails in eval/cases.json."""

from __future__ import annotations

import json
from collections import Counter, defaultdict

import config
import knowledge
import pipeline
from sources import Email


def run() -> None:
    cases = json.loads(config.EVAL_FILE.read_text(encoding="utf-8"))
    entries = knowledge.load()

    print(f"Evaluating {config.MODEL} on {len(cases)} labelled cases\n")

    correct = Counter()
    total = Counter()
    confusion: dict[str, Counter] = defaultdict(Counter)
    failures = []
    kb_hits = 0
    kb_total = 0

    for i, case in enumerate(cases, 1):
        email = Email(
            id=case["id"], sender=case["sender"],
            subject=case["subject"], body=case["body"],
        )
        got = pipeline.classify(email)

        row = []
        for field in ("category", "topic", "urgency", "language"):
            if field not in case["expect"]:
                continue
            expected = case["expect"][field]
            actual = got[field]
            total[field] += 1
            hit = actual == expected
            if hit:
                correct[field] += 1
            else:
                failures.append((case["id"], field, expected, actual))

            # Also score topic only where the model was actually asked.
            if field == "topic" and got.get("topic_asked"):
                total["topic_asked"] += 1
                correct["topic_asked"] += hit
            if field == "category":
                confusion[expected][actual] += 1
            row.append(f"{field[:4]}={'ok' if hit else actual}")

        # Check FAQ retrieval separately from classification.
        if "expect_faq" in case:
            kb_total += 1
            match = knowledge.best(f"{case['subject']} {case['body']}", entries)
            if match and case["expect_faq"].lower() in match.entry.question.lower():
                kb_hits += 1
                row.append("faq=ok")
            else:
                got_q = match.entry.question[:30] if match else "none"
                row.append(f"faq={got_q!r}")
                failures.append((case["id"], "faq", case["expect_faq"], got_q))

        print(f"[{i:2}/{len(cases)}] {case['id']:<22} " + "  ".join(row))

    print(f"\n{'─' * 58}\nRESULTS\n")
    for field in ("category", "topic", "topic_asked", "urgency", "language"):
        if total[field]:
            pct = 100 * correct[field] / total[field]
            label = "topic*" if field == "topic_asked" else field
            print(f"  {label:<10} {correct[field]:>2}/{total[field]:<2}  {pct:5.1f}%")
    if kb_total:
        pct = 100 * kb_hits / kb_total
        print(f"  {'faq match':<10} {kb_hits:>2}/{kb_total:<2}  {pct:5.1f}%")

    if total["topic_asked"] and total["topic_asked"] != total["topic"]:
        skipped = total["topic"] - total["topic_asked"]
        print(f"\n  * topic* only counts the {total['topic_asked']} cases where the "
              f"model was asked.\n    In the other {skipped} the category was wrong, "
              f"so topic was never asked.")

    if failures:
        print(f"\n  {len(failures)} failure(s):")
        for case_id, field, expected, actual in failures:
            print(f"    {case_id:<22} {field}: expected {expected!r}, got {actual!r}")

    pairs = [(exp, act, n) for exp, row in confusion.items()
             for act, n in row.items() if exp != act]
    if pairs:
        print("\n  category confusions (expected -> got):")
        for expected, actual, count in sorted(pairs, key=lambda t: -t[2]):
            print(f"    {expected} -> {actual}  ({count}x)")

    print(f"\n  Model: {config.MODEL}  Provider: {config.PROVIDER}")


if __name__ == "__main__":
    run()
