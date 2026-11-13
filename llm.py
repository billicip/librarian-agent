"""Model calls. No tool calling, Python decides the order of steps."""

from __future__ import annotations

import functools

import openai

import config


@functools.lru_cache(maxsize=1)
def _client():
    return openai.OpenAI(base_url=config.BASE_URL, api_key=config.api_key())


def ask(prompt: str, *, system: str = "", max_tokens: int = 400,
        temperature: float = 0.2, stop: list[str] | None = None) -> str:
    """Send one prompt, get text back.

    The penalties and stop sequences are there because phi-4-mini kept
    repeating the prompt back. Some endpoints don't accept them, so it
    retries without.
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
    """Check if the model got stuck repeating itself. Returns a reason or ""."""
    if not text.strip():
        return "empty response"

    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 15]
    if lines and len(set(lines)) < len(lines) / 2:
        return "more than half the lines are duplicates"

    # Same phrase 3+ times = loop.
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
    """Ask the model to pick one option from a list.

    One question at a time instead of one big JSON, because phi-4-mini
    kept breaking the JSON. If the answer isn't recognised, returns the
    last option (the catch-all).
    """
    menu = "\n".join(f"- {o}" for o in options)
    prompt = (
        f"{context}\n\n{question}\n\n"
        f"Choose exactly ONE from this list:\n{menu}\n\n"
        f"Reply with only the chosen word. No explanation."
    )
    raw = ask(prompt, max_tokens=20, temperature=0.0).lower()

    # Exact match first, then substring (e.g. "answer: enquiry").
    for option in options:
        if raw.strip() == option:
            return option
    for option in options:
        if option in raw:
            return option

    return options[-1]
