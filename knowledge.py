"""Load and search the FAQ in knowledge_base/.

Search is plain word overlap, no embeddings. Easy to check by hand, but it
matches words, not meaning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import config

# Common words to ignore, otherwise everything matches on "the" and "library".
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


# How fast the score goes to 1. Lower = more generous.
_SATURATION = 3.0


def search(query: str, entries: list[Entry], *, top: int = 3) -> list[Match]:
    """Score every FAQ entry against the query and return the top few.

    Words matching the FAQ question count double. Score is n / (n + 3).
    I tried dividing by query length (scores too small) and by FAQ question
    length (short questions won everything, 4/10). This one got 9/10.
    Tuned on only 10 emails.
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
    """False if the text has no searchable words (e.g. it's all Chinese)."""
    return bool(_tokens(query))


def best(query: str, entries: list[Entry]) -> Match | None:
    hits = search(query, entries, top=1)
    return hits[0] if hits else None
