"""Connects to IMAP or Gmail to pull emails using a unified interface."""

from __future__ import annotations

import base64
import logging
import socket
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final, cast

import httplib2
from imap_tools.mailbox import MailBox as IMAPToolsMailBox
from imap_tools.query import AND
from googleapiclient.errors import HttpError
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

if TYPE_CHECKING:
    from ringtwice.config import MailboxConfig

DEFAULT_FOLDERS: Final[tuple[str, ...]] = ("INBOX",)
_RETRYABLE_STATUS_CODES: Final[set[int]] = {429, 500, 502, 503, 504}
logger = logging.getLogger(__name__)


@dataclass
class Email:
    """A standard email container wrapping provider-specific raw messages."""

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
    """Filters for finding specific emails."""

    query: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    sender: list[str] | str | None = None
    recipient: list[str] | str | None = None
    subject: str | None = None

    def __post_init__(self) -> None:
        """Ensure sender and recipient are lists if provided."""
        if isinstance(self.sender, str):
            self.sender = [self.sender]
        if isinstance(self.recipient, str):
            self.recipient = [self.recipient]


class MailboxBackend(ABC):
    """Base class defining how we fetch messages from mail servers."""

    @abstractmethod
    def search(self, criteria: SearchCriteria, folders: list[str]) -> Iterator[Email]:
        """Yield emails that match the requested filters across specified folders."""

    @abstractmethod
    def get_thread(self, email: Email) -> list[Email]:
        """Return all emails belonging to the same conversation as the given email."""

    @abstractmethod
    def close(self) -> None:
        """Shut down backend connection cleanly."""


class IMAPBackend(MailboxBackend):
    """IMAP client utilizing imap-tools. Logs in once and holds the connection."""

    def __init__(self, host: str, username: str, password: str, port: int = 993) -> None:
        # imap-tools does not ship typing metadata
        self._mailbox: Any = IMAPToolsMailBox(host, port).login(username, password)  # type: ignore[no-untyped-call]

    def search(self, criteria: SearchCriteria, folders: list[str]) -> Iterator[Email]:
        """Execute a mailbox-native search. Yields emails directly from the server."""
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
        """Map standard search criteria into IMAP protocol commands."""
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
        """Fake thread support for IMAP by returning the email alone.
        
        IMAP threading relies on server-side capabilities not guaranteed to exist.
        """
        return [email]

    def close(self) -> None:
        """Drop the IMAP connection safely."""
        self._mailbox.logout()


class GmailBackend(MailboxBackend):
    """Gmail API client. Requires OAuth credentials."""

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
        self._retryer = self._build_retryer()

    def _build_service(self) -> Any:
        """Authenticate with Google and construct the API service object."""
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from google_auth_httplib2 import AuthorizedHttp

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

        # Use an authorized HTTP client with a timeout to avoid hanging reads
        http = httplib2.Http(timeout=30)
        authed_http = AuthorizedHttp(creds, http=http)
        return build("gmail", "v1", http=authed_http, cache_discovery=False)

    def _build_retryer(self) -> Retrying:
        """Create retry configuration for Gmail API calls."""
        return Retrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception(self._is_retryable_exception),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

    def search(self, criteria: SearchCriteria, folders: list[str]) -> Iterator[Email]:
        """Run a standard Gmail search using Gmail's own 'q' parameter syntax."""
        query = self._build_query(criteria, folders)
        page_token: str | None = None

        while True:
            def _list_messages(token: str | None = page_token) -> dict[str, Any]:
                params: dict[str, Any] = {"userId": "me", "q": query}
                if token:
                    params["pageToken"] = token
                return self._service.users().messages().list(**params).execute()

            results = self._execute_with_retry(_list_messages)

            for msg_stub in results.get("messages", []):
                msg = self._execute_with_retry(
                    lambda message_id=msg_stub["id"]: self._service.users()
                    .messages()
                    .get(userId="me", id=message_id, format="full")
                    .execute()
                )
                yield self._parse_message(msg)

            # Check for more pages
            page_token = results.get("nextPageToken")
            if not page_token:
                break

    def _build_query(self, criteria: SearchCriteria, folders: list[str]) -> str:
        """Convert SearchCriteria to a valid Gmail API search string."""
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
        """Extract sender, dates, and bodies from the deeply nested Gmail API JSON."""
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
        """Pull the entire thread containing this email using Gmail's thread API."""
        if not email.thread_id:
            return [email]
        thread = self._execute_with_retry(
            lambda: self._service.users().threads().get(userId="me", id=email.thread_id).execute()
        )
        return [self._parse_message(msg) for msg in thread.get("messages", [])]

    def close(self) -> None:
        """Clean up. A no-op since HTTP connections are stateless."""
        pass

    def _execute_with_retry(self, func: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """Fire a request and automatically back off if Google rate limits us."""
        return self._retryer(func)

    def _is_retryable_exception(self, exc: BaseException) -> bool:
        """Determine if an exception should be retried."""
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return True
        if isinstance(exc, HttpError):
            status = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "resp", None), "status", None
            )
            return bool(status and status in _RETRYABLE_STATUS_CODES)
        return False


def create_backend(config: MailboxConfig) -> MailboxBackend:
    """Factory function to create appropriate backend."""
    if config.type == "gmail":
        if config.credentials_file is None:
            raise ValueError("Missing 'credentials_file' for Gmail mailbox. Add it to your config TOML.")
        return GmailBackend(config.credentials_file)
    elif config.type == "imap":
        if config.host is None or config.username is None or config.password is None:
            raise ValueError("Missing IMAP credentials. Ensure 'host', 'username', and 'password' are set in your config TOML.")
        return IMAPBackend(
            host=config.host,
            username=config.username,
            password=config.password,
            port=config.port,
        )
    raise ValueError(f"Unsupported mailbox type '{config.type}'. Use 'imap' or 'gmail'.")
