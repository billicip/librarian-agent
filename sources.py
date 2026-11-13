"""Where emails come from and where replies go.

FileSource reads JSON files and is what actually runs. GraphSource (Outlook)
is written but never ran, because Mail.Read was refused by admins.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import config


@dataclass
class Email:
    id: str
    sender: str
    subject: str
    body: str
    received: str = ""

    def as_text(self) -> str:
        return f"From: {self.sender}\nSubject: {self.subject}\n\n{self.body}"


# --- Source 1: files (works today) ----------------------------------------

class FileSource:
    """Reads inbox/*.json, writes replies to outbox/. "Sending" just writes a file."""

    name = "files"

    def fetch(self, limit: int = 50) -> list[Email]:
        emails = []
        for path in sorted(Path(config.INBOX_DIR).glob("*.json"))[:limit]:
            data = json.loads(path.read_text(encoding="utf-8"))
            emails.append(Email(
                id=data.get("id", path.stem),
                sender=data.get("sender", "unknown@example.com"),
                subject=data.get("subject", ""),
                body=data.get("body", ""),
                received=data.get("received", ""),
            ))
        return emails

    def _write(self, email: Email, body: str, status: str) -> str:
        Path(config.OUTBOX_DIR).mkdir(exist_ok=True)
        path = Path(config.OUTBOX_DIR) / f"{status.lower()}_{email.id}.md"
        path.write_text(
            f"# {status}\n\n"
            f"**To:** {email.sender}\n"
            f"**Subject:** Re: {email.subject}\n"
            f"**Written:** {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n\n"
            f"---\n\n{body}\n",
            encoding="utf-8",
        )
        return str(path.name)

    def save_draft(self, email: Email, body: str) -> str:
        return self._write(email, body, "DRAFT")

    def send(self, email: Email, body: str) -> str:
        return self._write(email, body, "SENT")

    def notify(self, subject: str, body: str) -> str:
        Path(config.OUTBOX_DIR).mkdir(exist_ok=True)
        path = Path(config.OUTBOX_DIR) / "NOTIFICATION.md"
        path.write_text(f"# {subject}\n\n{body}\n", encoding="utf-8")
        return str(path.name)


# --- Source 2: Microsoft Graph (written, NEVER RUN) ------------------------

class GraphSource:
    """Outlook via Microsoft Graph. NOT TESTED.

    Needs an app registration, Mail.Read/Send/ReadWrite with admin consent,
    msal, and GRAPH_CLIENT_ID / GRAPH_TENANT_ID in .env.
    """

    name = "graph"
    SCOPES = ["Mail.Read", "Mail.Send", "Mail.ReadWrite"]

    def __init__(self):
        if not config.GRAPH_CLIENT_ID:
            raise SystemExit(
                "EMAIL_SOURCE=graph needs GRAPH_CLIENT_ID in .env.\n"
                "This path is untested. Use EMAIL_SOURCE=files instead."
            )
        try:
            import msal  # noqa: F401
        except ImportError:
            raise SystemExit("EMAIL_SOURCE=graph needs: pip3 install msal requests")
        self._token = None

    def _headers(self) -> dict:
        import msal

        if self._token is None:
            app = msal.PublicClientApplication(
                config.GRAPH_CLIENT_ID,
                authority=f"https://login.microsoftonline.com/{config.GRAPH_TENANT_ID}",
            )
            # Device code flow, so no redirect URI is needed.
            flow = app.initiate_device_flow(scopes=self.SCOPES)
            if "user_code" not in flow:
                raise SystemExit(f"Could not start device flow: {flow}")
            print(flow["message"], flush=True)
            result = app.acquire_token_by_device_flow(flow)
            if "access_token" not in result:
                raise SystemExit(
                    f"Auth failed: {result.get('error_description', result)}"
                )
            self._token = result["access_token"]
        return {"Authorization": f"Bearer {self._token}"}

    def fetch(self, limit: int = 50) -> list[Email]:
        import requests

        response = requests.get(
            "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages",
            headers=self._headers(),
            params={"$top": limit, "$select": "id,subject,from,bodyPreview,receivedDateTime"},
            timeout=30,
        )
        response.raise_for_status()
        emails = []
        for item in response.json().get("value", []):
            address = (item.get("from", {}).get("emailAddress", {}) or {})
            emails.append(Email(
                id=item["id"],
                sender=address.get("address", "unknown"),
                subject=item.get("subject", ""),
                body=item.get("bodyPreview", ""),
                received=item.get("receivedDateTime", ""),
            ))
        return emails

    def save_draft(self, email: Email, body: str) -> str:
        import requests

        response = requests.post(
            f"https://graph.microsoft.com/v1.0/me/messages/{email.id}/createReply",
            headers=self._headers(), timeout=30,
        )
        response.raise_for_status()
        draft_id = response.json()["id"]
        requests.patch(
            f"https://graph.microsoft.com/v1.0/me/messages/{draft_id}",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"body": {"contentType": "Text", "content": body}},
            timeout=30,
        ).raise_for_status()
        return f"draft:{draft_id}"

    def send(self, email: Email, body: str) -> str:
        import requests

        draft_ref = self.save_draft(email, body)
        draft_id = draft_ref.split(":", 1)[1]
        requests.post(
            f"https://graph.microsoft.com/v1.0/me/messages/{draft_id}/send",
            headers=self._headers(), timeout=30,
        ).raise_for_status()
        return f"sent:{draft_id}"

    def notify(self, subject: str, body: str) -> str:
        import requests

        me = requests.get("https://graph.microsoft.com/v1.0/me",
                          headers=self._headers(), timeout=30).json()
        requests.post(
            "https://graph.microsoft.com/v1.0/me/sendMail",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": me["mail"]}}],
            }},
            timeout=30,
        ).raise_for_status()
        return "notification emailed"


def get_source():
    return GraphSource() if config.EMAIL_SOURCE == "graph" else FileSource()
