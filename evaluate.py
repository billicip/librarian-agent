"""Measure the classifier against hand-labelled cases.

This is the part that makes the project research rather than a demo.

"We built an agent" is not a finding. "phi-4-mini correctly classified 17 of
20 library enquiries; every failure confused internal_admin with enquiry" is —
it is a number, it is reproducible by anyone who clones this repo, and it can
be compared directly against Copilot Studio once that becomes available.

The eval set lives in eval/cases.json with the correct answers written by
hand. Getting the labels right matters more than the code here: a wrong label
silently punishes a correct model.
"""

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

            # Topic is scored twice: once over every labelled case, and once
            # over only those where the model was actually asked. See the note
            # printed with the results.
            if field == "topic" and got.get("topic_asked"):
                total["topic_asked"] += 1
                correct["topic_asked"] += hit
            if field == "category":
                confusion[expected][actual] += 1
            row.append(f"{field[:4]}={'ok' if hit else actual}")

        # Where a case names the FAQ entry that SHOULD match, check retrieval
        # too — classification and retrieval fail in different ways and a
        # combined number would hide which one is weak.
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
        print(f"\n  * topic is scored twice on purpose. The plain row counts every "
              f"labelled\n    case; the starred row counts only the "
              f"{total['topic_asked']} where the model was actually\n    asked. "
              f"In the other {skipped}, it called the category something other than\n"
              f"    'enquiry', so pipeline.classify() never put the topic question and\n"
              f"    the answer defaulted to 'other'. Scoring those as topic errors\n"
              f"    counts one category mistake twice.")

    if failures:
        print(f"\n  {len(failures)} failure(s):")
        for case_id, field, expected, actual in failures:
            print(f"    {case_id:<22} {field}: expected {expected!r}, got {actual!r}")

    # Confusion pairs are the useful output. "It got 85%" tells you little;
    # "it systematically reads internal_admin as enquiry" tells you what to fix.
    pairs = [(exp, act, n) for exp, row in confusion.items()
             for act, n in row.items() if exp != act]
    if pairs:
        print("\n  category confusions (expected -> got):")
        for expected, actual, count in sorted(pairs, key=lambda t: -t[2]):
            print(f"    {expected} -> {actual}  ({count}x)")

    print(f"\n  Record this in FINDINGS.md with the model name and date.")
    print(f"  Model: {config.MODEL}  Provider: {config.PROVIDER}")


if __name__ == "__main__":
    run()
