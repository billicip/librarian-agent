"""Settings: model provider, email source, thresholds, paths."""

from __future__ import annotations

import os
from pathlib import Path

# --- Model provider -------------------------------------------------------
# Foundry Local runs on your machine. The port changes per install,
# check it with `foundry server status`.

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
# "graph"  — Microsoft Graph. Never tested, Mail.Read permission was
#            refused by admins in both tenants I tried.

EMAIL_SOURCE = os.getenv("EMAIL_SOURCE", "files").strip().lower()

GRAPH_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID", "").strip()
GRAPH_TENANT_ID = os.getenv("GRAPH_TENANT_ID", "common").strip()

# --- Behaviour ------------------------------------------------------------

# Minimum FAQ match score to send without a human. This is the search
# score, not the model's confidence.
AUTO_SEND_THRESHOLD = float(os.getenv("AUTO_SEND_THRESHOLD", "0.55"))

# Below this, count it as a gap in the FAQ.
MATCH_FLOOR = float(os.getenv("MATCH_FLOOR", "0.35"))

# On by default because the file source never sends real email.
# Turn it off before using a real mailbox.
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
