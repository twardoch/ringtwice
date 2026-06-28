"""Tests for runner module."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ringtwice.config import Config, LLMConfig, MailboxConfig
from ringtwice.llm import LLMResponse
from ringtwice.mailbox import DEFAULT_FOLDERS, Email
from ringtwice.runner import (
    AskParams,
    RunCallbacks,
    build_search_criteria,
    fetch_emails,
    parse_date,
    process_emails_batch,
    process_emails_individual,
    resolve_folders,
    resolve_mailboxes,
    run_ask,
    split_csv,
)


class TestHelpers:
    """Tests for helper functions."""

    def test_split_csv_none(self) -> None:
        """Test split_csv with None input."""
        assert split_csv(None) is None

    def test_split_csv_empty(self) -> None:
        """Test split_csv with empty string."""
        assert split_csv("") is None

    def test_split_csv_single(self) -> None:
        """Test split_csv with single value."""
        assert split_csv("one") == ["one"]

    def test_split_csv_multiple(self) -> None:
        """Test split_csv with multiple values."""
        assert split_csv("one, two, three") == ["one", "two", "three"]

    def test_split_csv_trims_whitespace(self) -> None:
        """Test split_csv trims whitespace."""
        assert split_csv("  one  ,  two  ") == ["one", "two"]

    def test_parse_date_none(self) -> None:
        """Test parse_date with None input."""
        assert parse_date(None) is None

    def test_parse_date_valid(self) -> None:
        """Test parse_date with valid ISO date."""
        result = parse_date("2024-01-15")
        assert result == datetime(2024, 1, 15)

    def test_parse_date_with_time(self) -> None:
        """Test parse_date with datetime string."""
        result = parse_date("2024-01-15T10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0)


class TestResolveMailboxes:
    """Tests for resolve_mailboxes function."""

    def test_resolve_default_mailbox(self) -> None:
        """Test resolve_mailboxes returns first mailbox by default."""
        config = Config(
            llm=LLMConfig(endpoint="http://x", api_key="k", model="m"),
            mailbox={
                "first": MailboxConfig(type="imap", host="a", username="u", password="p"),
                "second": MailboxConfig(type="imap", host="b", username="u", password="p"),
            },
        )
        result = resolve_mailboxes(config, None)
        assert len(result) == 1
        assert result[0][0] == "first"

    def test_resolve_specific_mailboxes(self) -> None:
        """Test resolve_mailboxes with specific names."""
        config = Config(
            llm=LLMConfig(endpoint="http://x", api_key="k", model="m"),
            mailbox={
                "first": MailboxConfig(type="imap", host="a", username="u", password="p"),
                "second": MailboxConfig(type="imap", host="b", username="u", password="p"),
            },
        )
        result = resolve_mailboxes(config, ["second"])
        assert len(result) == 1
        assert result[0][0] == "second"

    def test_resolve_missing_mailbox_raises(self) -> None:
        """Test resolve_mailboxes raises for missing mailbox."""
        config = Config(
            llm=LLMConfig(endpoint="http://x", api_key="k", model="m"),
            mailbox={
                "first": MailboxConfig(type="imap", host="a", username="u", password="p"),
            },
        )
        with pytest.raises(ValueError, match="Unknown mailbox requested"):
            resolve_mailboxes(config, ["missing"])


class TestBuildSearchCriteria:
    """Tests for build_search_criteria function."""

    def test_empty_params(self) -> None:
        """Test build_search_criteria with minimal params."""
        params = AskParams(parse_query="test")
        criteria = build_search_criteria(params)
        assert criteria.query is None
        assert criteria.sender is None

    def test_full_params(self) -> None:
        """Test build_search_criteria with all params."""
        params = AskParams(
            parse_query="test",
            search_query="meeting",
            date_from=datetime(2024, 1, 1),
            date_to=datetime(2024, 12, 31),
            sender=["boss@example.com"],
            recipient=["me@example.com"],
            subject="Important",
        )
        criteria = build_search_criteria(params)
        assert criteria.query == "meeting"
        assert criteria.sender == ["boss@example.com"]
        assert criteria.recipient == ["me@example.com"]
        assert criteria.subject == "Important"


class TestResolveFolders:
    """Tests for resolve_folders helper."""

    def test_defaults_to_inbox(self) -> None:
        """Fallback to INBOX when not provided."""
        assert resolve_folders(None) == list(DEFAULT_FOLDERS)
        assert resolve_folders([]) == list(DEFAULT_FOLDERS)

    def test_returns_custom(self) -> None:
        """Return caller-provided folders."""
        assert resolve_folders(["Sent"]) == ["Sent"]


class TestFetchEmails:
    """Tests for fetch_emails function."""

    def test_fetch_basic(self) -> None:
        """Test basic email fetching."""
        mailbox_config = MailboxConfig(type="imap", host="a", username="u", password="p")
        email = Email(
            uid="1",
            subject="Test",
            sender="sender@example.com",
            recipients=["me@example.com"],
            date=datetime(2024, 1, 15),
            text="Hello",
            html=None,
        )

        with patch("ringtwice.runner.create_backend") as mock_backend:
            backend_instance = MagicMock()
            backend_instance.search.return_value = iter([email])
            mock_backend.return_value = backend_instance

            from ringtwice.mailbox import SearchCriteria

            result = fetch_emails(
                [("test", mailbox_config)],
                SearchCriteria(),
                folders=None,
                thread=False,
                max_emails=None,
            )

            assert len(result.emails) == 1
            assert result.counts_by_mailbox["test"] == 1
            backend_instance.close.assert_called_once()
            search_args, _ = backend_instance.search.call_args
            assert search_args[1] == list(DEFAULT_FOLDERS)

    def test_fetch_with_max_emails(self) -> None:
        """Test fetch respects max_emails."""
        mailbox_config = MailboxConfig(type="imap", host="a", username="u", password="p")
        emails = [
            Email(
                uid=str(i),
                subject=f"Test {i}",
                sender="sender@example.com",
                recipients=["me@example.com"],
                date=datetime(2024, 1, 15),
                text=f"Hello {i}",
                html=None,
            )
            for i in range(10)
        ]

        with patch("ringtwice.runner.create_backend") as mock_backend:
            backend_instance = MagicMock()
            backend_instance.search.return_value = iter(emails)
            mock_backend.return_value = backend_instance

            from ringtwice.mailbox import SearchCriteria

            result = fetch_emails(
                [("test", mailbox_config)],
                SearchCriteria(),
                folders=None,
                thread=False,
                max_emails=3,
            )

            assert len(result.emails) == 3

    def test_fetch_respects_custom_folders(self) -> None:
        """Use caller-provided folders instead of defaults."""
        mailbox_config = MailboxConfig(type="imap", host="a", username="u", password="p")
        email = Email(
            uid="1",
            subject="Test",
            sender="sender@example.com",
            recipients=["me@example.com"],
            date=datetime(2024, 1, 15),
            text="Hello",
            html=None,
        )

        with patch("ringtwice.runner.create_backend") as mock_backend:
            backend_instance = MagicMock()
            backend_instance.search.return_value = iter([email])
            mock_backend.return_value = backend_instance

            from ringtwice.mailbox import SearchCriteria

            fetch_emails(
                [("test", mailbox_config)],
                SearchCriteria(),
                folders=["SENT"],
                thread=False,
                max_emails=None,
            )

            search_args, _ = backend_instance.search.call_args
            assert search_args[1] == ["SENT"]


class TestProcessEmails:
    """Tests for process functions."""

    def test_process_individual(self, tmp_path: Path) -> None:
        """Test individual email processing."""
        email = Email(
            uid="1",
            subject="Test",
            sender="sender@example.com",
            recipients=["me@example.com"],
            date=datetime(2024, 1, 15),
            text="Hello",
            html=None,
        )
        response = LLMResponse(
            content="Result",
            model="test",
            usage_prompt_tokens=10,
            usage_completion_tokens=5,
        )

        processor = MagicMock()
        processor.process.return_value = "processed content"

        llm = MagicMock()
        llm.process_batch.return_value = iter([response])

        writer = MagicMock()
        writer.write.return_value = tmp_path / "output.jsonl"

        writes: list[Path] = []
        process_emails_individual(
            [email],
            processor,
            llm,
            writer,
            "test prompt",
            thread=False,
            on_write=lambda p: writes.append(p),
        )

        processor.process.assert_called_once_with(email)
        writer.write.assert_called_once()
        assert len(writes) == 1

    def test_process_batch(self, tmp_path: Path) -> None:
        """Test batch email processing."""
        emails = [
            Email(
                uid=str(i),
                subject=f"Test {i}",
                sender="sender@example.com",
                recipients=["me@example.com"],
                date=datetime(2024, 1, 15),
                text=f"Hello {i}",
                html=None,
            )
            for i in range(3)
        ]
        response = LLMResponse(
            content="Batch result",
            model="test",
            usage_prompt_tokens=30,
            usage_completion_tokens=10,
        )

        processor = MagicMock()
        processor.process.side_effect = [f"processed {i}" for i in range(3)]

        llm = MagicMock()
        llm.process_batch.return_value = iter([response])

        writer = MagicMock()
        writer.write_batch.return_value = tmp_path / "batch.jsonl"

        writes: list[Path] = []
        process_emails_batch(
            emails,
            processor,
            llm,
            writer,
            "test prompt",
            batch_size=None,
            on_write=lambda p: writes.append(p),
        )

        assert processor.process.call_count == 3
        writer.write_batch.assert_called_once()
        assert len(writes) == 1


class TestRunAsk:
    """Tests for run_ask function."""

    def test_run_ask_basic(self, tmp_path: Path) -> None:
        """Test basic run_ask execution."""
        config = Config(
            llm=LLMConfig(
                endpoint="http://test",
                api_key="key",
                model="model",
                max_context=4096,
            ),
            mailbox={
                "test": MailboxConfig(type="imap", host="a", username="u", password="p"),
            },
        )
        email = Email(
            uid="1",
            subject="Test",
            sender="sender@example.com",
            recipients=["me@example.com"],
            date=datetime(2024, 1, 15),
            text="Hello",
            html=None,
        )
        response = LLMResponse(
            content="Result",
            model="model",
            usage_prompt_tokens=10,
            usage_completion_tokens=5,
        )

        output_dir = tmp_path / "output"
        params = AskParams(
            parse_query="Extract info",
            output_dir=output_dir,
            config_file=tmp_path / "config.toml",
        )

        with (
            patch("ringtwice.runner.Config.load", return_value=config),
            patch("ringtwice.runner.create_backend") as mock_backend,
            patch("ringtwice.runner.LLMClient") as mock_llm,
        ):
            backend_instance = MagicMock()
            backend_instance.search.return_value = iter([email])
            mock_backend.return_value = backend_instance

            llm_instance = MagicMock()
            llm_instance.process_batch.return_value = iter([response])
            mock_llm.return_value = llm_instance

            result = run_ask(params)

            assert result == output_dir
            assert output_dir.exists()

    def test_run_ask_no_emails(self, tmp_path: Path) -> None:
        """Test run_ask with no emails found."""
        config = Config(
            llm=LLMConfig(
                endpoint="http://test",
                api_key="key",
                model="model",
            ),
            mailbox={
                "test": MailboxConfig(type="imap", host="a", username="u", password="p"),
            },
        )

        output_dir = tmp_path / "output"
        params = AskParams(
            parse_query="Extract info",
            output_dir=output_dir,
            config_file=tmp_path / "config.toml",
        )

        no_emails_called = []
        callbacks = RunCallbacks(on_no_emails=lambda: no_emails_called.append(True))

        with (
            patch("ringtwice.runner.Config.load", return_value=config),
            patch("ringtwice.runner.create_backend") as mock_backend,
            patch("ringtwice.runner.LLMClient"),
        ):
            backend_instance = MagicMock()
            backend_instance.search.return_value = iter([])
            mock_backend.return_value = backend_instance

            run_ask(params, callbacks)

        assert len(no_emails_called) == 1
