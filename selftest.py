"""Run the real pipeline with a fake model. No model, server or network needed."""

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
    """Fake model that answers based on keywords."""

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
        return options[-1]

    def ask(self, prompt, **kwargs):
        self.calls += 1
        # phi-4-mini once made up "9 am to 5 pm" opening hours. This must be caught.
        if "opening hour" in prompt.lower():
            return ("The Main Library operates from 9 am to 5 pm on Mondays "
                    "and Tuesdays.\n\nHKU Libraries")
        # The other real failure: repeating the prompt.
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

        # Made-up opening hours must be replaced by the template.
        hours = by_id.get("002-hours")
        if hours:
            if not hours.draft_method.startswith("template"):
                problems.append(
                    f"invented opening hours were NOT caught — draft_method="
                    f"{hours.draft_method!r}")
            if "9 am to 5 pm" in hours.draft:
                problems.append("the invented time survived into the reply")

        # A looping reply must also be replaced.
        renew = by_id.get("001-renew")
        if renew:
            if not renew.draft_method.startswith("template"):
                problems.append(
                    f"degenerate reply was NOT caught — draft_method="
                    f"{renew.draft_method!r}")
            if "Reference information" in renew.draft:
                problems.append("the echoed prompt survived into the reply")
            # The template version is safe to send.
            if config.AUTO_SEND and renew.action != "sent":
                problems.append(f"verified template was {renew.action}, "
                                f"expected 'sent'")

        # Chinese is never auto-sent.
        chinese = by_id.get("009-chinese")
        if chinese and chinese.action == "sent":
            problems.append("Chinese enquiry was auto-sent; it must be held")

        # Search can't read Chinese, so it shouldn't count as an FAQ gap.
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

        print("\nSELF-TEST PASSED")

    finally:
        llm.pick_one, llm.ask = real_pick, real_ask
        config.OUTBOX_DIR = original_outbox
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    run_selftest()
