"""Configuration — model provider, thresholds, and paths.

Everything that could be taken away from us lives here: the model provider,
and the email source. Both were chosen after hitting access walls elsewhere
(see FINDINGS.md), so both are swappable from .env without touching logic.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Model provider -------------------------------------------------------
# Foundry Local: free, runs on this machine, a Microsoft product.
# Port is assigned per-install — check `foundry server status`.

PROVIDERS: dict[str, dict] = {
    "foundry-local": {
        "base_url": "http://127.0.0.1:52999/v1",
        "model": "phi-4-mini",
        "key_env": "",
    },
    "azure": {
        "base_url": "",                    # set MODEL_BASE_URL
        "model": "gpt-4o-mini",            # your DEPLOYMENT name
        "key_env": "AZURE_OPENAI_API_KEY",
    },
    "custom": {"base_url": "", "model": "", "key_env": "MODEL_API_KEY"},
}

PROVIDER = os.getenv("PROVIDER", "foundry-local").strip().lower()
if PROVIDER not in PROVIDERS:
    raise SystemExit(f"Unknown PROVIDER '{PROVIDER}'. One of: {', '.join(PROVIDERS)}")

_p = PROVIDERS[PROVIDER]
BASE_URL = os.getenv("MODEL_BASE_URL", "").strip() or _p["base_url"]
MODEL = os.getenv("MODEL_NAME", "").strip() or _p["model"]


def api_key() -> str:
    """Local providers need no key, but the openai SDK insists on a value."""
    if not _p["key_env"]:
        return "not-needed"
    key = os.getenv(_p["key_env"], "").strip()
    if not key:
        raise SystemExit(f"PROVIDER '{PROVIDER}' needs {_p['key_env']} in .env")
    return key


# --- Email source ---------------------------------------------------------
# "files"  — read .json files from inbox/. Works today.
# "graph"  — Microsoft Graph. WRITTEN BUT UNVERIFIED: Mail.Read consent was
#            refused by an administrator in both tenants we tried. See
#            FINDINGS.md F6. Do not claim this path works until someone runs it.

EMAIL_SOURCE = os.getenv("EMAIL_SOURCE", "files").strip().lower()

GRAPH_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID", "").strip()
GRAPH_TENANT_ID = os.getenv("GRAPH_TENANT_ID", "common").strip()

# --- Behaviour ------------------------------------------------------------

# How strong a FAQ match must be before a reply is sent without a human.
# NOTE: confidence is the SEARCH's, not the model's. A small model will happily
# claim certainty while inventing a loan period; a match score is auditable.
# "Sent because FAQ 'renew books online' matched at 0.71" can be checked.
AUTO_SEND_THRESHOLD = float(os.getenv("AUTO_SEND_THRESHOLD", "0.55"))

# Below this, we treat the FAQ as having no answer at all and log a gap.
MATCH_FLOOR = float(os.getenv("MATCH_FLOOR", "0.35"))

# Master switch. ON by default per project decision — safe here because the
# test mailbox has no real patrons. Turn OFF before pointing at a real
# shared mailbox, and get sign-off first.
AUTO_SEND = os.getenv("AUTO_SEND", "true").strip().lower() in {"1", "true", "yes"}

CATEGORIES = [
    "enquiry",                # a question we might answer from the FAQ
    "meeting_request",        # someone wants to meet / book time
    "internal_admin",         # colleagues, logistics, forms
    "automated_notification", # system mail, no action needed
    "needs_human",            # anything else — complaint, unclear, sensitive
]

TOPICS = [
    "borrowing", "accessing", "research", "study_space",
    "printing", "other",
]

URGENCIES = ["low", "normal", "high"]

# There is deliberately no LANGUAGES list here. The three lists above are menus
# handed to the model to choose from, so they belong in configuration. Language
# is not chosen from a menu any more — pipeline.detect_language computes it from
# the characters (FINDINGS.md F12), so the possible answers live with the code
# that produces them.

# --- Paths ----------------------------------------------------------------

ROOT = Path(__file__).parent
KB_DIR = ROOT / "knowledge_base"
INBOX_DIR = ROOT / "inbox"
OUTBOX_DIR = ROOT / "outbox"
REPORTS_DIR = ROOT / "reports"
EVAL_FILE = ROOT / "eval" / "cases.json"


def describe() -> str:
    return (f"provider={PROVIDER}  model={MODEL}  source={EMAIL_SOURCE}  "
            f"auto_send={'ON' if AUTO_SEND else 'OFF'}")
