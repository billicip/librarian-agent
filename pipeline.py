"""Main pipeline. Fixed sequence, no agent loop.

    classify  ->  match FAQ  ->  draft  ->  route
      [AI]         [Python]      [AI]     [Python]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import config
import knowledge
import llm
from sources import Email


@dataclass
class Result:
    email: Email
    category: str = ""
    topic: str = ""
    urgency: str = ""
    language: str = ""
    match_score: float = 0.0
    matched_question: str = ""
    action: str = ""          # sent | drafted | flagged | ignored
    draft: str = ""
    artifact: str = ""        # filename or id the action produced
    draft_method: str = ""   # "model" or "template (reason)"
    kb_gap: bool = False
    retrieval_unavailable: bool = False   # search could not read the query at all
    notes: list[str] = field(default_factory=list)


# --- Step 1a: language (Python, not the model) ----------------------------

# Chinese characters + CJK punctuation and fullwidth blocks.
_CJK = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
                  "\u3000-\u303f\uff00-\uffef]")
_LATIN = re.compile("[A-Za-z]")

# 10% so a single Chinese name in an English email doesn't count.
# Only tested on 2 Chinese emails, not on mixed-language mail.
_CJK_RATIO = 0.10


def detect_language(text: str) -> str:
    """Return "english" or "chinese" based on character counts.

    Used to be a model call that scored 12/20. This scores 20/20.
    Only detects script, so French or Indonesian will come back as "english".
    """
    cjk = len(_CJK.findall(text))
    if cjk == 0:
        return "english"
    latin = len(_LATIN.findall(text))
    return "chinese" if cjk / (cjk + latin) >= _CJK_RATIO else "english"


# --- Step 1: classify -----------------------------------------------------

def classify(email: Email) -> dict:
    """Ask the model for category, topic and urgency. Language is done in Python."""
    context = f"An email received by a university library:\n\n{email.as_text()[:1200]}"

    category = llm.pick_one(
        "What kind of email is this?", config.CATEGORIES, context=context)

    # Only enquiries need a topic.
    topic = "other"
    if category == "enquiry":
        topic = llm.pick_one(
            "Which library topic is this enquiry about?",
            config.TOPICS, context=context)

    urgency = llm.pick_one(
        "How urgent is this email? 'high' only if a deadline or problem is "
        "stated explicitly.",
        config.URGENCIES, context=context)

    # Skip the sender line, email addresses are always Latin script.
    language = detect_language(f"{email.subject}\n{email.body}")

    return {"category": category, "topic": topic,
            "urgency": urgency, "language": language,
            # evaluate.py uses this so a wrong category isn't also counted
            # as a wrong topic.
            "topic_asked": category == "enquiry"}


# --- Step 3: draft --------------------------------------------------------

REPLY_SYSTEM = (
    "You write short, polite email replies for HKU Libraries.\n"
    "RULES:\n"
    "- Use ONLY the reference text supplied. Never state a number, time, price "
    "or policy that does not appear in it word for word.\n"
    "- If the reference does not answer the question, say a librarian will "
    "follow up. Do not guess.\n"
    "- Under 100 words. Sign off as 'HKU Libraries'.\n"
    "- Output ONLY the reply body. Do not repeat these instructions."
)

# Any number, time or price in a model draft must also be in the FAQ text.
_FACT = re.compile(r"\$?\d+(?:[:.]\d+)?\s*(?:am|pm|a\.m\.|p\.m\.|hours?|days?|%)?",
                   re.IGNORECASE)


def template_reply(email: Email, match: knowledge.Match | None) -> str:
    """Build a reply without the model by quoting the FAQ answer word for word."""
    if match is None:
        return ("Thank you for contacting HKU Libraries.\n\n"
                "We have received your message. A librarian will review it and "
                "reply to you directly.\n\n"
                "HKU Libraries")

    body = ["Thank you for contacting HKU Libraries.\n",
            f"{match.entry.answer}\n"]
    if match.entry.source:
        body.append(f"More detail: {match.entry.source}\n")
    body.append("If this does not answer your question, please reply and a "
                "librarian will follow up.\n")
    body.append("HKU Libraries")
    return "\n".join(body)


def verify_draft(draft: str, reference: str) -> str:
    """Return why the draft is unsafe, or "" if it's fine.

    Checks for repetition loops and for numbers/times/prices not in the FAQ.
    """
    problem = llm.looks_degenerate(draft)
    if problem:
        return problem

    reference_facts = {f.strip().lower() for f in _FACT.findall(reference)}
    for fact in _FACT.findall(draft):
        fact = fact.strip().lower()
        if len(fact) < 2:
            continue
        if fact not in reference_facts and not any(
                fact in known for known in reference_facts):
            return f"states {fact!r}, which is not in the FAQ text"
    return ""


def draft_reply(email: Email, match: knowledge.Match | None) -> tuple[str, str]:
    """Return (reply, method). Tries the model, falls back to the template."""
    if match is None:
        return template_reply(email, None), "template (no FAQ match)"

    reference = f"{match.entry.question}\n{match.entry.answer}"

    generated = llm.ask(
        f"FAQ entry:\n{reference}\n\n"
        f"User's email:\n{email.as_text()[:900]}\n\n"
        f"Reply:",
        system=REPLY_SYSTEM, max_tokens=220,
        stop=["FAQ entry:", "User's email:", "\n---"],
    )

    problem = verify_draft(generated, reference + " " + email.as_text())
    if problem:
        return template_reply(email, match), f"template (model {problem})"
    return generated, "model"


def summarise_meeting(email: Email) -> str:
    summary = llm.ask(
        f"In ONE sentence, say who wants to meet and what about:\n\n"
        f"{email.as_text()[:900]}",
        max_tokens=80, stop=["\n\n"],
    )
    # If the summary is broken, just use the subject line.
    if llm.looks_degenerate(summary):
        return f"Meeting request from {email.sender}: {email.subject}"
    return summary


# --- The whole thing ------------------------------------------------------

def process(email: Email, entries: list[knowledge.Entry], source) -> Result:
    result = Result(email=email)

    # 1. classify
    labels = classify(email)
    result.category = labels["category"]
    result.topic = labels["topic"]
    result.urgency = labels["urgency"]
    result.language = labels["language"]

    # Everything that is not an enquiry or a meeting request stops here.
    if result.category == "automated_notification":
        result.action = "ignored"
        return result

    if result.category == "meeting_request":
        result.draft = summarise_meeting(email)
        result.draft_method = "model summary"
        result.action = "flagged"
        result.notes.append("meeting request — needs a human to accept or decline")
        return result

    if result.category in {"internal_admin", "needs_human"}:
        result.action = "flagged"
        result.notes.append(f"{result.category} — no automatic reply attempted")
        return result

    # --- enquiry path ---

    # 2. match the FAQ (Python, not AI)
    query = f"{email.subject} {email.body}"
    match = knowledge.best(query, entries)
    if match:
        result.match_score = match.score
        result.matched_question = match.entry.question

    # Weak match = probably a gap in the FAQ. Except when the search can't
    # read the text at all (e.g. Chinese), which is a different problem.
    if match is None or match.score < config.MATCH_FLOOR:
        if not knowledge.searchable(query):
            result.retrieval_unavailable = True
            result.notes.append(
                "retrieval unavailable — the FAQ search is word-based and found "
                "no searchable words here; this is NOT evidence the FAQ lacks "
                "an answer")
        else:
            result.kb_gap = True
            result.notes.append("no FAQ entry covers this — knowledge base gap")
        match = None

    # 3. draft
    result.draft, result.draft_method = draft_reply(email, match)

    # 4. route
    confident = match is not None and match.score >= config.AUTO_SEND_THRESHOLD
    non_english = result.language != "english"

    # Only template replies get auto-sent. The model once made up opening hours.
    safe_to_send = result.draft_method.startswith("template")

    if confident and config.AUTO_SEND and not non_english and safe_to_send:
        result.action = "sent"
        result.artifact = source.send(email, result.draft)
    else:
        result.action = "drafted"
        result.artifact = source.save_draft(email, result.draft)
        if not confident:
            result.notes.append(
                f"match {result.match_score} below send threshold "
                f"{config.AUTO_SEND_THRESHOLD} — held for review")
        if non_english:
            # Chinese replies haven't been checked yet.
            result.notes.append(
                f"language '{result.language}' — never auto-sent, quality unverified")
        if not safe_to_send:
            result.notes.append(
                "model-written reply — held for review; only verbatim "
                "template replies are auto-sent")
        if not config.AUTO_SEND:
            result.notes.append("AUTO_SEND is off")

    return result
