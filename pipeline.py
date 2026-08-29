"""The pipeline — the heart of this project.

Read this file to understand what the agent actually does. It is a fixed
sequence of steps, not an agent loop. Python decides the order; the model
only performs text tasks at three points.

    classify  ->  match FAQ  ->  draft  ->  route
      [AI]         [Python]      [AI]     [Python]

WHY NOT AN AGENT LOOP. A tool-calling agent lets the model decide what to do
next. That is necessary when the sequence cannot be known in advance. Here it
can: we always classify before matching, always match before drafting. Fixing
the order buys three things — it works on a small local model that cannot
reliably call tools (FINDINGS.md F5), it cannot wander off, and a librarian
can read the sequence above and know exactly what will happen.

Most tasks people call "agentic" are this shape.
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

# Chinese ideographs, plus the CJK punctuation and fullwidth blocks, which
# carry the writing system just as clearly as the characters do.
_CJK = re.compile("[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
                  "\u3000-\u303f\uff00-\uffef]")
_LATIN = re.compile("[A-Za-z]")

# A stray Chinese name or a quoted title in an otherwise English email should
# not hold that email back. A tenth of the letters is well above that and well
# below any genuinely Chinese message. Tuned on 2 Chinese cases out of 20 —
# enough to fix an obvious bug, nowhere near calibrated on mixed-language mail.
_CJK_RATIO = 0.10


def detect_language(text: str) -> str:
    """Which writing system is this, decided by Python rather than the model.

    This replaced an llm.pick_one call that scored 12/20 and was biased toward
    answering "chinese" — mislabelling 8 plainly English emails and, because
    process() blocks auto-send on non-English mail, silently holding back
    roughly 40% of the inbox for a reason unrelated to reply quality.

    The third instance of this project's central finding: where a step has a
    right answer that code can compute, code beats the model. F10 found it,
    F11 measured it, this applies it.

    Returns "english" or "chinese". Unlike CATEGORIES and TOPICS these are not
    in config.py on purpose: those are menus offered to the model and belong in
    configuration, whereas these two are simply what this function can compute.
    A third value, "other", was listed briefly and is not reachable — see the
    limit below.

    LIMIT, stated plainly: this detects a SCRIPT, not a language. It separates
    Chinese from Latin script reliably. It cannot tell English from French, so
    a French email is labelled "english" and becomes eligible for auto-send.
    That is a real regression against the model, which could in principle have
    caught it — at 60% accuracy it mostly did not. See FINDINGS.md F12.

    Rejected: langdetect / langid. Both are extra dependencies, both are
    statistical (so they can be wrong in ways a character range cannot), and
    both are far more machinery than one question about writing system needs.
    """
    cjk = len(_CJK.findall(text))
    if cjk == 0:
        return "english"
    latin = len(_LATIN.findall(text))
    return "chinese" if cjk / (cjk + latin) >= _CJK_RATIO else "english"


# --- Step 1: classify -----------------------------------------------------

def classify(email: Email) -> dict:
    """Three narrow questions to the model, plus one answered in Python.

    See llm.pick_one for why the questions are asked one at a time. Language
    used to be a fourth question; it is now detect_language() above.
    """
    context = f"An email received by a university library:\n\n{email.as_text()[:1200]}"

    category = llm.pick_one(
        "What kind of email is this?", config.CATEGORIES, context=context)

    # Only enquiries need a topic — skip the call otherwise. Saves time and
    # avoids asking the model a question with no sensible answer.
    topic = "other"
    if category == "enquiry":
        topic = llm.pick_one(
            "Which library topic is this enquiry about?",
            config.TOPICS, context=context)

    urgency = llm.pick_one(
        "How urgent is this email? 'high' only if a deadline or problem is "
        "stated explicitly.",
        config.URGENCIES, context=context)

    # Not a model call. The sender line is excluded on purpose: an email
    # address is Latin script whatever language the message is written in.
    language = detect_language(f"{email.subject}\n{email.body}")

    return {"category": category, "topic": topic,
            "urgency": urgency, "language": language,
            # Whether the topic question was put to the model at all. The eval
            # needs this: when the category is wrong, topic is never asked and
            # defaults to "other", and scoring that as a topic error counts one
            # category mistake twice. Kept here rather than re-derived in
            # evaluate.py so the two can never disagree.
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

# Numbers, times and prices are where invention does real damage — a wrong
# opening time sends someone across campus for nothing. Anything matching this
# in a generated draft must also appear in the source text.
_FACT = re.compile(r"\$?\d+(?:[:.]\d+)?\s*(?:am|pm|a\.m\.|p\.m\.|hours?|days?|%)?",
                   re.IGNORECASE)


def template_reply(email: Email, match: knowledge.Match | None) -> str:
    """Build a reply WITHOUT the model. The FAQ answer is quoted verbatim.

    This is the safe path, and after the failure described in FINDINGS.md F10
    it is also the default. A small model asked to paraphrase a policy will
    invent one; a template cannot. It reads slightly stiffly. Stiff and correct
    beats fluent and wrong when the sender is a student who will act on it.
    """
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
    """Return a reason the draft is unsafe to send, or "" if it passes.

    Two checks, both cheap and both earned by observed failures:
      - degeneration (the model looping on the prompt)
      - invented facts: any number, time or price in the draft that does not
        appear in the reference text

    The second is deliberately strict. A false alarm costs a human glance at a
    draft; a miss costs a student a wasted trip to a closed library.
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
    """Return (reply, how_it_was_made).

    Tries the model first, verifies the result, and falls back to the template
    when verification fails. The fallback is not an error path — on a small
    local model it is expected to fire regularly.
    """
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
    # Same degeneration guard. A looping summary in a notification is noise,
    # so fall back to the raw subject line, which is always truthful.
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

    # A weak match usually means the FAQ has no answer for this. Worth
    # recording: the accumulated list is a to-do list for whoever maintains the
    # FAQ.
    #
    # But "nothing matched" has two causes that mean opposite things, and until
    # 2026-08-29 this treated them as one (FINDINGS.md F14). A Chinese enquiry
    # scores nothing because the word-based search cannot read it — not because
    # the FAQ is missing an entry. Reporting that as a gap sends a librarian off
    # to write an FAQ answer that already exists in English.
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

    # 4. route.
    # Confidence is the SEARCH's, not the model's — see config.AUTO_SEND_THRESHOLD.
    confident = match is not None and match.score >= config.AUTO_SEND_THRESHOLD
    non_english = result.language != "english"

    # Only TEMPLATE replies may be auto-sent. A model-written reply is prose we
    # have not read, produced by a model observed to invent opening hours
    # (FINDINGS.md F10). Templates quote the FAQ verbatim and cannot invent.
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
            # Deliberate: we have not measured drafting quality in Chinese,
            # so we do not auto-send it. Caution beats an untested claim.
            result.notes.append(
                f"language '{result.language}' — never auto-sent, quality unverified")
        if not safe_to_send:
            result.notes.append(
                "model-written reply — held for review; only verbatim "
                "template replies are auto-sent")
        if not config.AUTO_SEND:
            result.notes.append("AUTO_SEND is off")

    return result
