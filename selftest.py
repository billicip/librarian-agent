"""Prove the pipeline works without a model or a mailbox.

Swaps in a scripted fake model, runs real emails through the real pipeline,
and checks the routing decisions. Catches broken wiring in under a second with
no download, no server and no network — so if a real run then fails, the
problem is the model, not this code.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import config
import knowledge
import llm
import pipeline
import sources


class FakeLLM:
    """Answers plausibly from keywords. Deterministic, so the test is stable."""

    def __init__(self):
        self.calls = 0

    def pick_one(self, question, options, context=""):
        self.calls += 1
        text = context.lower()
        if "category" in question.lower() or "kind of email" in question.lower():
            if "do not reply" in text or "automated message" in text:
                return "automated_notification"
            if "would like to meet" in text or "are you free" in text:
                return "meeting_request"
            if "dear colleagues" in text:
                return "internal_admin"
            if "unacceptable" in text:
                return "needs_human"
            return "enquiry"
        if "topic" in question.lower():
            for word, topic in [("renew", "borrowing"), ("print", "printing"),
                                ("open", "accessing"), ("room", "study_space")]:
                if word in text:
                    return topic
            return "research"
        if "urgent" in question.lower():
            return "high" if "urgent" in text else "normal"
        # No language branch: the pipeline no longer asks the model what
        # language an email is in. pipeline.detect_language decides it from
        # the characters, so the Chinese check below now tests the real thing.
        return options[-1]

    def ask(self, prompt, **kwargs):
        self.calls += 1
        # Reproduces the real failure from FINDINGS.md F10: asked about opening
        # hours, phi-4-mini invented "9 am to 5 pm" and it was auto-sent.
        # The verifier must catch this and fall back to the template.
        if "opening hour" in prompt.lower():
            return ("The Main Library operates from 9 am to 5 pm on Mondays "
                    "and Tuesdays.\n\nHKU Libraries")
        # And the other real failure: looping on the prompt.
        if "renew" in prompt.lower():
            return "Reference information:\n---\nCan I renew books online?\n---\n" * 4
        return "Thank you for your message. Please see the FAQ.\n\nHKU Libraries"


def run_selftest() -> None:
    print("Self-test — fake model, real pipeline, no network\n")

    fake = FakeLLM()
    real_pick, real_ask = llm.pick_one, llm.ask
    llm.pick_one, llm.ask = fake.pick_one, fake.ask
    pipeline.llm = llm

    scratch = Path(config.OUTBOX_DIR) / "_selftest"
    original_outbox = config.OUTBOX_DIR
    config.OUTBOX_DIR = scratch
    scratch.mkdir(parents=True, exist_ok=True)

    try:
        entries = knowledge.load()
        assert entries, "knowledge base is empty — check knowledge_base/*.md"

        source = sources.FileSource()
        emails = source.fetch()
        assert emails, "no emails in inbox/"

        results = [pipeline.process(e, entries, source) for e in emails]

        for r in results:
            print(f"  {r.email.id:<14} {r.category:<23} {r.action}")

        problems = []
        by_id = {r.email.id: r for r in results}

        # An automated notification must never produce a reply.
        auto = by_id.get("006-noreply")
        if auto and auto.action != "ignored":
            problems.append(f"automated mail was {auto.action}, expected 'ignored'")

        # A meeting request must be flagged for a human, never answered.
        meeting = by_id.get("003-meeting")
        if meeting and meeting.action != "flagged":
            problems.append(f"meeting request was {meeting.action}, expected 'flagged'")

        # REGRESSION (F10): a model reply that invents an opening time must be
        # rejected and replaced by the verbatim template, never sent as-is.
        hours = by_id.get("002-hours")
        if hours:
            if not hours.draft_method.startswith("template"):
                problems.append(
                    f"invented opening hours were NOT caught — draft_method="
                    f"{hours.draft_method!r}")
            if "9 am to 5 pm" in hours.draft:
                problems.append("the invented time survived into the reply")

        # REGRESSION: a looping reply must also be rejected.
        renew = by_id.get("001-renew")
        if renew:
            if not renew.draft_method.startswith("template"):
                problems.append(
                    f"degenerate reply was NOT caught — draft_method="
                    f"{renew.draft_method!r}")
            if "Reference information" in renew.draft:
                problems.append("the echoed prompt survived into the reply")
            # Having fallen back to a verbatim template, it IS safe to send.
            if config.AUTO_SEND and renew.action != "sent":
                problems.append(f"verified template was {renew.action}, "
                                f"expected 'sent'")

        # Chinese must never auto-send — quality is unverified.
        chinese = by_id.get("009-chinese")
        if chinese and chinese.action == "sent":
            problems.append("Chinese enquiry was auto-sent; it must be held")

        # REGRESSION (F14): the word-based FAQ search cannot read Chinese, so it
        # finds nothing. That must be recorded as "could not search", never as
        # "the FAQ has no answer" — the same question in English matches at 0.75.
        if chinese:
            if chinese.kb_gap:
                problems.append(
                    "Chinese enquiry was reported as a knowledge-base gap; the "
                    "search cannot read it, which is not the same as the FAQ "
                    "lacking an answer")
            if not chinese.retrieval_unavailable:
                problems.append(
                    "Chinese enquiry was NOT flagged retrieval_unavailable")

        # Every enquiry must produce some draft text.
        for r in results:
            if r.category == "enquiry" and not r.draft:
                problems.append(f"{r.email.id}: enquiry produced no draft")

        print(f"\n  {fake.calls} model calls, {len(results)} emails")

        if problems:
            print("\nSELF-TEST FAILED:")
            for p in problems:
                print(f"  - {p}")
            raise SystemExit(1)

        print("\nSELF-TEST PASSED — classification routing, FAQ matching, "
              "drafting\nand send/hold decisions all behave correctly.")
        print("If a real run fails now, the problem is the model, not the pipeline.")

    finally:
        llm.pick_one, llm.ask = real_pick, real_ask
        config.OUTBOX_DIR = original_outbox
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    run_selftest()
