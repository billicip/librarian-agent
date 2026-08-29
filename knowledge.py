"""The knowledge base — real HKU Libraries FAQ content, and how we search it.

Content in knowledge_base/*.md is copied verbatim from lib.hku.hk/FAQ, with
the source URL recorded in each file. Librarians can edit these files directly
in any text editor: no database, no admin console, no code.

SEARCH IS DELIBERATELY DUMB and that is the point. Scoring is word overlap
(a Jaccard-style ratio), not embeddings. Three reasons:

  1. It is auditable. "Matched at 0.71 on these words" can be checked by a
     human. An embedding score cannot be explained to a librarian.
  2. It needs no extra model, no vector store, no extra download.
  3. It is the honest baseline. If a naive method already answers most
     enquiries, that is worth knowing before adding machinery.

Its weakness is real and should be reported: it matches WORDS, not MEANING.
"How long can I keep a book" will not match a FAQ that says "loan period".
Upgrading this to embeddings is the single clearest next improvement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import config

# Words too common to carry meaning. Without this, every enquiry matches every
# FAQ on "the" and "library".
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "am", "i",
    "you", "my", "me", "we", "us", "it", "this", "that", "these", "those",
    "to", "of", "in", "on", "at", "for", "from", "with", "by", "as", "and",
    "or", "but", "if", "can", "could", "would", "should", "will", "shall",
    "do", "does", "did", "have", "has", "had", "how", "what", "when", "where",
    "who", "which", "why", "please", "hello", "hi", "dear", "thanks", "thank",
    "regards", "library", "libraries", "hku",
}


@dataclass
class Entry:
    question: str
    answer: str
    section: str
    source: str

    def __str__(self) -> str:
        return f"[{self.section}] Q: {self.question}\nA: {self.answer}"


@dataclass
class Match:
    entry: Entry
    score: float


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def load() -> list[Entry]:
    """Parse every knowledge_base/*.md into Q/A entries."""
    entries: list[Entry] = []
    for path in sorted(Path(config.KB_DIR).glob("*.md")):
        text = path.read_text(encoding="utf-8")

        section = path.stem
        source = ""
        for line in text.splitlines():
            if line.startswith("# "):
                section = line[2:].strip()
            elif line.startswith("source:"):
                source = line.split(":", 1)[1].strip()

        # Q: ... A: ... pairs, answer running until the next Q: or end of file.
        pattern = re.compile(r"^Q:\s*(.+?)\nA:\s*(.+?)(?=\n\nQ:|\Z)",
                             re.MULTILINE | re.DOTALL)
        for question, answer in pattern.findall(text):
            entries.append(Entry(
                question=question.strip(),
                answer=" ".join(answer.split()),
                section=section,
                source=source,
            ))
    return entries


# Controls how quickly the score approaches 1. Lower = more generous.
# Chosen empirically — see the note on tuning below.
_SATURATION = 3.0


def search(query: str, entries: list[Entry], *, top: int = 3) -> list[Match]:
    """Score every entry against the query; return the best few.

    Overlap is counted as shared meaningful words, with the FAQ *question*
    weighted double — a question matching a question is a stronger signal than
    a question matching prose buried in an answer.

    The raw count is then squashed into 0..1 by `n / (n + k)`. Two earlier
    attempts are worth recording, because both failed in instructive ways:

      - Dividing by the QUERY's word count made every score tiny, because a
        chatty email has many words and is punished for being chatty. Ranking
        was fine (the divisor is constant per query, so it cancels out) but
        no score ever cleared a sensible send threshold.
      - Dividing by the FAQ QUESTION's word count fixed the magnitudes and
        broke the ranking, because it rewards short FAQ questions — "Where can
        I checkout books?" is easy to cover and started winning everything.
        Retrieval fell from 9/10 to 4/10.

    A saturating function on the raw count keeps the ranking that worked and
    produces usable magnitudes.

    HONEST CAVEAT: `_SATURATION` and the thresholds in config.py were tuned on
    ten labelled cases. That is enough to avoid something obviously broken and
    nowhere near enough to call calibrated. Naive singularisation ("books" ->
    "book") was also tried and made retrieval worse (9/10 -> 8/10), so it is
    not used — but on ten cases that difference is one example, not evidence.
    Re-tune against real enquiry data when any exists.
    """
    query_words = _tokens(query)
    if not query_words:
        return []

    results: list[Match] = []
    for entry in entries:
        overlap = (len(query_words & _tokens(entry.question)) * 2
                   + len(query_words & _tokens(entry.answer)))
        if overlap:
            score = overlap / (overlap + _SATURATION)
            results.append(Match(entry=entry, score=round(score, 3)))

    results.sort(key=lambda m: m.score, reverse=True)
    return results[:top]


def searchable(query: str) -> bool:
    """Can this text be searched at all, before asking whether anything matched?

    `_tokens` finds runs of [a-z0-9]. Chinese has none, so a Chinese enquiry
    tokenises to the empty set and `search` returns nothing — not because the
    FAQ lacks an answer, but because the search cannot read the question.

    Those two outcomes look identical downstream and mean opposite things. One
    says "write a new FAQ entry"; the other says "this tool does not work on
    this input". Distinguishing them is the whole point of this function.
    See FINDINGS.md F14.
    """
    return bool(_tokens(query))


def best(query: str, entries: list[Entry]) -> Match | None:
    hits = search(query, entries, top=1)
    return hits[0] if hits else None
