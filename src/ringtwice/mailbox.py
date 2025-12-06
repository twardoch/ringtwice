"""Email access abstraction for Gmail and IMAP backends."""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from imap_tools.mailbox import MailBox as IMAPToolsMailBox
from imap_tools.query import AND

if TYPE_CHECKING:
    from ringtwice.config import MailboxConfig


@dataclass
class Email:
    """Unified email representation."""

    uid: str
    subject: str
    sender: str
    recipients: list[str]
    date: datetime
    text: str | None
    html: str | None
    thread_id: str | None = None


@dataclass
class SearchCriteria:
    """Email search parameters."""

    query: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    sender: list[str] | str | None = None
    recipient: list[str] | str | None = None
    subject: str | None = None

    def __post_init__(self) -> None:
        """Normalize sender/recipient to lists when provided."""
        if isinstance(self.sender, str):
            self.sender = [self.sender]
        if isinstance(self.recipient, str):
            self.recipient = [self.recipient]


class MailboxBackend(ABC):
    """Abstract base for email backends."""

    @abstractmethod
    def search(self, criteria: SearchCriteria, folders: list[str]) -> Iterator[Email]:
        """Search for emails matching criteria."""

    @abstractmethod
    def get_thread(self, email: Email) -> list[Email]:
        """Get all emails in a thread."""

    @abstractmethod
    def close(self) -> None:
        """Close connection."""


class IMAPBackend(MailboxBackend):
    """IMAP email backend using imap-tools."""

    def __init__(self, host: str, username: str, password: str, port: int = 993) -> None:
        # imap-tools does not ship typing metadata
        self._mailbox: Any = IMAPToolsMailBox(host, port).login(username, password)  # type: ignore[no-untyped-call]

    def search(self, criteria: SearchCriteria, folders: list[str]) -> Iterator[Email]:
        """Search IMAP mailbox."""
        for folder in folders:
            self._mailbox.folder.set(folder)
            imap_criteria = self._build_criteria(criteria)
            for msg in self._mailbox.fetch(imap_criteria):
                if msg.uid is None:
                    continue
                yield Email(
                    uid=msg.uid,
                    subject=msg.subject,
                    sender=msg.from_,
                    recipients=list(msg.to),
                    date=msg.date,
                    text=msg.text,
                    html=msg.html,
                )

    def _build_criteria(self, criteria: SearchCriteria) -> AND:
        """Convert SearchCriteria to imap-tools query."""
        text_parts: list[str] = []
        from_part: str | None = None
        to_part: str | None = None
        subject_part = criteria.subject
        date_gte_part: date | None = None
        date_lt_part: date | None = None

        if criteria.query:
            text_parts.append(criteria.query)
        if criteria.sender:
            if len(criteria.sender) == 1:
                from_part = criteria.sender[0]
            else:
                text_parts.extend(criteria.sender)
        if criteria.recipient:
            if len(criteria.recipient) == 1:
                to_part = criteria.recipient[0]
            else:
                text_parts.extend(criteria.recipient)
        if criteria.date_from:
            date_gte_part = criteria.date_from.date()
        if criteria.date_to:
            date_lt_part = criteria.date_to.date()
        text_part: str | None = " OR ".join(text_parts) if text_parts else None

        if not any([text_part, from_part, to_part, subject_part, date_gte_part, date_lt_part]):
            return AND(all=True)

        return AND(
            text=text_part,
            from_=from_part,
            subject=subject_part,
            to=to_part,
            date_gte=date_gte_part,
            date_lt=date_lt_part,
        )

    def get_thread(self, email: Email) -> list[Email]:
        """IMAP doesn't have native threading - return single email."""
        return [email]

    def close(self) -> None:
        """Logout from IMAP server."""
        self._mailbox.logout()


class GmailBackend(MailboxBackend):
    """Gmail API backend."""

    SCOPES: ClassVar[list[str]] = ["https://www.googleapis.com/auth/gmail.readonly"]
    _service: Any

    def __init__(self, credentials_file: Path) -> None:
        # Expand ~ and resolve path
        self._credentials_file = Path(credentials_file).expanduser().resolve()
        if not self._credentials_file.exists():
            raise FileNotFoundError(
                f"Gmail credentials not found: {self._credentials_file}\n\n"
                "To set up Gmail access, see: https://twardoch.github.io/ringtwice/gmail/\n"
            )
        self._service = self._build_service()

    def _build_service(self) -> Any:
        """Build Gmail API service with OAuth."""
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        # Store token next to credentials file
        token_path = self._credentials_file.parent / "gmail_token.json"

        creds: Any = None
        if token_path.exists():
            creds = cast(Any, Credentials).from_authorized_user_file(str(token_path), self.SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                # Try to refresh expired token
                from google.auth.transport.requests import Request

                creds.refresh(cast(Any, Request)())
            else:
                # Run OAuth flow - opens browser
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._credentials_file), self.SCOPES
                )
                creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json())

        return build("gmail", "v1", credentials=creds)

    def search(self, criteria: SearchCriteria, folders: list[str]) -> Iterator[Email]:
        """Search Gmail using API query syntax."""
        query = self._build_query(criteria, folders)
        page_token: str | None = None

        while True:
            # Build request with optional page token
            request = self._service.users().messages().list(userId="me", q=query)
            if page_token:
                request = (
                    self._service.users()
                    .messages()
                    .list(userId="me", q=query, pageToken=page_token)
                )
            results = request.execute()

            for msg_stub in results.get("messages", []):
                msg = (
                    self._service.users()
                    .messages()
                    .get(userId="me", id=msg_stub["id"], format="full")
                    .execute()
                )
                yield self._parse_message(msg)

            # Check for more pages
            page_token = results.get("nextPageToken")
            if not page_token:
                break

    def _build_query(self, criteria: SearchCriteria, folders: list[str]) -> str:
        """Build Gmail search query string."""
        parts = []
        if criteria.query:
            parts.append(criteria.query)
        if criteria.sender:
            if len(criteria.sender) == 1:
                parts.append(f"from:{criteria.sender[0]}")
            else:
                ors = " OR ".join(f"from:{s}" for s in criteria.sender)
                parts.append(f"({ors})")
        if criteria.subject:
            parts.append(f"subject:{criteria.subject}")
        if criteria.recipient:
            if len(criteria.recipient) == 1:
                parts.append(f"to:{criteria.recipient[0]}")
            else:
                ors = " OR ".join(f"to:{r}" for r in criteria.recipient)
                parts.append(f"({ors})")
        if criteria.date_from:
            parts.append(f"after:{criteria.date_from.strftime('%Y/%m/%d')}")
        if criteria.date_to:
            parts.append(f"before:{criteria.date_to.strftime('%Y/%m/%d')}")
        if folders:
            folder_query = " OR ".join(f"in:{f}" for f in folders)
            parts.append(f"({folder_query})")
        return " ".join(parts)

    def _parse_message(self, msg: dict[str, Any]) -> Email:
        """Parse Gmail API message to Email dataclass."""
        headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}

        # Extract body
        text = None
        html = None
        payload = msg["payload"]

        if "parts" in payload:
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                if "data" in part.get("body", {}):
                    data = base64.urlsafe_b64decode(part["body"]["data"]).decode()
                    if mime_type == "text/plain":
                        text = data
                    elif mime_type == "text/html":
                        html = data
        elif "body" in payload and "data" in payload["body"]:
            data = base64.urlsafe_b64decode(payload["body"]["data"]).decode()
            if payload.get("mimeType") == "text/html":
                html = data
            else:
                text = data

        # Parse date
        date_str = headers.get("date", "")
        try:
            from email.utils import parsedate_to_datetime

            date = parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            date = datetime.now()

        return Email(
            uid=msg["id"],
            subject=headers.get("subject", ""),
            sender=headers.get("from", ""),
            recipients=headers.get("to", "").split(","),
            date=date,
            text=text,
            html=html,
            thread_id=msg.get("threadId"),
        )

    def get_thread(self, email: Email) -> list[Email]:
        """Get full Gmail thread."""
        if not email.thread_id:
            return [email]
        thread = self._service.users().threads().get(userId="me", id=email.thread_id).execute()
        return [self._parse_message(msg) for msg in thread.get("messages", [])]

    def close(self) -> None:
        """No persistent connection to close."""
        pass


def create_backend(config: MailboxConfig) -> MailboxBackend:
    """Factory function to create appropriate backend."""
    if config.type == "gmail":
        if config.credentials_file is None:
            raise ValueError("Gmail mailbox requires credentials_file")
        return GmailBackend(config.credentials_file)
    elif config.type == "imap":
        if config.host is None or config.username is None or config.password is None:
            raise ValueError("IMAP mailbox requires host, username, and password")
        return IMAPBackend(
            host=config.host,
            username=config.username,
            password=config.password,
            port=config.port,
        )
    raise ValueError(f"Unknown mailbox type: {config.type}")
