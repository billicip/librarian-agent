"""Talking to the model.

Two functions only. Note what is NOT here: no tool calling, no agent loop.
The model is asked to do text tasks; Python decides the sequence.

That is a deliberate design choice, and the central one in this project.
See FINDINGS.md F5 — phi-4-mini is marked tool-capable but does not use tools
in practice. Rather than fight that, we removed the need for it: every step in
our pipeline has a known position, so nothing has to be decided at runtime.
"""

from __future__ import annotations

import functools

import openai

import config


@functools.lru_cache(maxsize=1)
def _client():
    return openai.OpenAI(base_url=config.BASE_URL, api_key=config.api_key())


def ask(prompt: str, *, system: str = "", max_tokens: int = 400,
        temperature: float = 0.2, stop: list[str] | None = None) -> str:
    """One prompt in, text out. Low temperature: we want consistency, not flair.

    `frequency_penalty` and `stop` are here because of an observed failure:
    phi-4-mini echoed the prompt's "Reference information: --- ..." block and
    then repeated it until it ran out of tokens. Penalising repeated tokens and
    stopping at the delimiter both cut that off. Some OpenAI-compatible
    endpoints reject these parameters, so we retry without them rather than
    crash — a slightly worse reply beats no reply.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = dict(model=config.MODEL, messages=messages,
                  max_tokens=max_tokens, temperature=temperature)
    extras = {"frequency_penalty": 0.6, "presence_penalty": 0.3}
    if stop:
        extras["stop"] = stop

    try:
        response = _client().chat.completions.create(**kwargs, **extras)
    except Exception:                                       # noqa: BLE001
        response = _client().chat.completions.create(**kwargs)

    return (response.choices[0].message.content or "").strip()


def looks_degenerate(text: str) -> str:
    """Detect the model repeating itself. Returns a reason, or "" if fine.

    Small models fall into loops: they emit a phrase, then emit it again, and
    again, until the token budget runs out. It is obvious to a human and easy
    to detect mechanically — and much better caught here than mailed to a
    student.
    """
    if not text.strip():
        return "empty response"

    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 15]
    if lines and len(set(lines)) < len(lines) / 2:
        return "more than half the lines are duplicates"

    # A phrase repeated three or more times is a loop, not emphasis.
    words = text.split()
    if len(words) > 40:
        for size in (6, 10):
            chunks = [" ".join(words[i:i + size])
                      for i in range(0, len(words) - size, size)]
            counts = {}
            for chunk in chunks:
                counts[chunk] = counts.get(chunk, 0) + 1
                if counts[chunk] >= 3:
                    return f"phrase repeated {counts[chunk]}x: {chunk[:45]!r}"

    if "Reference information" in text or text.count("---") > 2:
        return "the prompt was echoed back instead of answered"

    return ""


def pick_one(question: str, options: list[str], *, context: str = "") -> str:
    """Ask the model to choose exactly one option from a fixed list.

    WHY THIS EXISTS, and it is the most important thing in this file:

    The obvious approach is to ask for all fields at once as JSON --
    {"category": ..., "topic": ..., "urgency": ...}. Small models are
    unreliable at that. They add prose around the JSON, forget a field, or
    invent a value outside the allowed set, and one malformed brace loses
    everything.

    Asking one narrow question at a time, with a fixed menu and a demand for a
    single word, is far more robust. It costs more calls and more seconds. On a
    local model that is free, so the trade is worth taking.

    We also parse leniently — if the model answers "The category is: enquiry",
    we still find "enquiry" — and fall back to the last option (which is always
    the safe catch-all) rather than crashing or guessing.
    """
    menu = "\n".join(f"- {o}" for o in options)
    prompt = (
        f"{context}\n\n{question}\n\n"
        f"Choose exactly ONE from this list:\n{menu}\n\n"
        f"Reply with only the chosen word. No explanation."
    )
    raw = ask(prompt, max_tokens=20, temperature=0.0).lower()

    # Exact match first, then substring — handles "answer: enquiry" politely.
    for option in options:
        if raw.strip() == option:
            return option
    for option in options:
        if option in raw:
            return option

    # Nothing recognisable. Fall back to the catch-all rather than guessing.
    return options[-1]
