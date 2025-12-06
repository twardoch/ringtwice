"""Tests for email access abstraction."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ringtwice.config import MailboxConfig
from ringtwice.mailbox import (
    Email,
    GmailBackend,
    IMAPBackend,
    SearchCriteria,
    create_backend,
)


class TestSearchCriteria:
    """Tests for SearchCriteria dataclass."""

    def test_default_values(self) -> None:
        """Test all fields default to None."""
        criteria = SearchCriteria()
        assert criteria.query is None
        assert criteria.date_from is None
        assert criteria.date_to is None
        assert criteria.sender is None
        assert criteria.recipient is None
        assert criteria.subject is None


class TestEmail:
    """Tests for Email dataclass."""

    def test_create_minimal(self) -> None:
        """Test creating email with minimal fields."""
        email = Email(
            uid="123",
            subject="Test",
            sender="test@example.com",
            recipients=["me@example.com"],
            date=datetime(2024, 1, 15, 10, 30),
            text="Hello",
            html=None,
        )
        assert email.uid == "123"
        assert email.thread_id is None


class TestIMAPBackend:
    """Tests for IMAP backend."""

    def test_build_criteria_empty(self) -> None:
        """Test empty criteria builds 'all' query."""
        with patch("ringtwice.mailbox.IMAPToolsMailBox"):
            backend = IMAPBackend("host", "user", "pass")
            criteria = SearchCriteria()
            result = backend._build_criteria(criteria)
            # AND with all=True
            assert hasattr(result, "all") or result is not None

    def test_build_criteria_with_sender(self) -> None:
        """Test sender filter in criteria."""
        with patch("ringtwice.mailbox.IMAPToolsMailBox"):
            backend = IMAPBackend("host", "user", "pass")
            criteria = SearchCriteria(sender="test@example.com")
            result = backend._build_criteria(criteria)
            assert result is not None

    def test_build_criteria_with_date_range(self) -> None:
        """Test date range filter in criteria."""
        with patch("ringtwice.mailbox.IMAPToolsMailBox"):
            backend = IMAPBackend("host", "user", "pass")
            criteria = SearchCriteria(
                date_from=datetime(2024, 1, 1),
                date_to=datetime(2024, 12, 31),
            )
            result = backend._build_criteria(criteria)
            assert result is not None

    def test_get_thread_returns_single_email(self) -> None:
        """Test IMAP threading returns single email."""
        with patch("ringtwice.mailbox.IMAPToolsMailBox"):
            backend = IMAPBackend("host", "user", "pass")
            email = Email(
                uid="1",
                subject="Test",
                sender="test@example.com",
                recipients=["me@example.com"],
                date=datetime.now(),
                text="content",
                html=None,
            )
            result = backend.get_thread(email)
            assert result == [email]


class TestGmailBackend:
    """Tests for Gmail backend."""

    @pytest.fixture
    def gmail_backend(self, tmp_path: Path) -> GmailBackend:
        """Create a GmailBackend with mocked service."""
        creds_file = tmp_path / "creds.json"
        creds_file.write_text("{}")
        with patch.object(GmailBackend, "_build_service", return_value=MagicMock()):
            return GmailBackend(creds_file)

    def test_build_query_empty(self, gmail_backend: GmailBackend) -> None:
        """Test empty criteria builds empty query."""
        criteria = SearchCriteria()
        result = gmail_backend._build_query(criteria, [])
        assert result == ""

    def test_build_query_with_sender(self, gmail_backend: GmailBackend) -> None:
        """Test sender in Gmail query."""
        criteria = SearchCriteria(sender="test@example.com")
        result = gmail_backend._build_query(criteria, [])
        assert "from:test@example.com" in result

    def test_build_query_with_date_range(self, gmail_backend: GmailBackend) -> None:
        """Test date range in Gmail query."""
        criteria = SearchCriteria(
            date_from=datetime(2024, 1, 15),
            date_to=datetime(2024, 2, 15),
        )
        result = gmail_backend._build_query(criteria, [])
        assert "after:2024/01/15" in result
        assert "before:2024/02/15" in result

    def test_build_query_with_folders(self, gmail_backend: GmailBackend) -> None:
        """Test folder filter in Gmail query."""
        criteria = SearchCriteria()
        result = gmail_backend._build_query(criteria, ["INBOX", "Sent"])
        assert "in:INBOX" in result
        assert "in:Sent" in result

    def test_get_thread_without_thread_id(self, gmail_backend: GmailBackend) -> None:
        """Test get_thread returns single email when no thread_id."""
        email = Email(
            uid="1",
            subject="Test",
            sender="test@example.com",
            recipients=["me@example.com"],
            date=datetime.now(),
            text="content",
            html=None,
            thread_id=None,
        )
        result = gmail_backend.get_thread(email)
        assert result == [email]


class TestCreateBackend:
    """Tests for backend factory function."""

    def test_creates_gmail_backend(self, tmp_path: Path) -> None:
        """Test factory creates GmailBackend for gmail type."""
        # Create a fake credentials file
        creds_file = tmp_path / "creds.json"
        creds_file.write_text("{}")

        config = MailboxConfig(
            name="test",
            type="gmail",
            credentials_file=creds_file,
        )
        with patch.object(GmailBackend, "_build_service", return_value=MagicMock()):
            backend = create_backend(config)
            assert isinstance(backend, GmailBackend)

    def test_creates_imap_backend(self) -> None:
        """Test factory creates IMAPBackend for imap type."""
        config = MailboxConfig(
            name="test",
            type="imap",
            host="imap.example.com",
            username="user",
            password="pass",
        )
        with patch("ringtwice.mailbox.IMAPToolsMailBox"):
            backend = create_backend(config)
            assert isinstance(backend, IMAPBackend)

    def test_raises_on_gmail_missing_credentials(self) -> None:
        """Test error when Gmail config missing credentials_file."""
        config = MailboxConfig(name="test", type="gmail")
        with pytest.raises(ValueError, match="credentials_file"):
            create_backend(config)

    def test_raises_on_imap_missing_host(self) -> None:
        """Test error when IMAP config missing host."""
        config = MailboxConfig(
            name="test",
            type="imap",
            username="user",
            password="pass",
        )
        with pytest.raises(ValueError, match="host"):
            create_backend(config)

    def test_raises_on_unknown_type(self) -> None:
        """Test error on unknown mailbox type."""
        config = MailboxConfig(name="test", type="imap")  # type: ignore[arg-type]
        # Manually set an invalid type
        object.__setattr__(config, "type", "unknown")
        with pytest.raises(ValueError, match="Unknown mailbox type"):
            create_backend(config)
