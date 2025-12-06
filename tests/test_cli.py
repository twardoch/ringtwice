"""Tests for CLI."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ringtwice.cli import RingtwiceCLI, ask, show_config
from ringtwice.config import Config, LLMConfig, MailboxConfig
from ringtwice.llm import LLMResponse
from ringtwice.mailbox import Email


@pytest.fixture
def mock_config(tmp_path: Path) -> Config:
    """Create mock config."""
    return Config(
        llm=LLMConfig(
            endpoint="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
            max_context=4096,
        ),
        mailbox={
            "test": MailboxConfig(
                type="imap",
                host="imap.example.com",
                username="user",
                password="pass",
            )
        },
    )


@pytest.fixture
def mock_email() -> Email:
    """Create mock email."""
    return Email(
        uid="1",
        subject="Test Subject",
        sender="sender@example.com",
        recipients=["me@example.com"],
        date=datetime(2024, 1, 15, 10, 30),
        text="Hello world",
        html=None,
    )


@pytest.fixture
def mock_response() -> LLMResponse:
    """Create mock LLM response."""
    return LLMResponse(
        content="Processed result",
        model="test-model",
        usage_prompt_tokens=10,
        usage_completion_tokens=5,
    )


class TestAsk:
    """Tests for ask function."""

    def test_creates_output_directory(
        self,
        tmp_path: Path,
        mock_config: Config,
        mock_email: Email,
        mock_response: LLMResponse,
    ) -> None:
        """Test CLI creates output directory."""
        output_dir = tmp_path / "output"

        with (
            patch("ringtwice.runner.Config.load", return_value=mock_config),
            patch("ringtwice.runner.create_backend") as mock_backend,
            patch("ringtwice.runner.LLMClient") as mock_llm,
        ):
            backend_instance = MagicMock()
            backend_instance.search.return_value = iter([mock_email])
            backend_instance.get_thread.return_value = [mock_email]
            mock_backend.return_value = backend_instance

            llm_instance = MagicMock()
            llm_instance.process_batch.return_value = iter([mock_response])
            mock_llm.return_value = llm_instance

            ask(
                parse_query="Extract info",
                output_dir=str(output_dir),
                config_file=str(tmp_path / "config.toml"),
                legacy=True,
            )

        assert output_dir.exists()

    def test_processes_emails_individually(
        self,
        tmp_path: Path,
        mock_config: Config,
        mock_email: Email,
        mock_response: LLMResponse,
    ) -> None:
        """Test non-batch mode processes emails individually."""
        output_dir = tmp_path / "output"

        with (
            patch("ringtwice.runner.Config.load", return_value=mock_config),
            patch("ringtwice.runner.create_backend") as mock_backend,
            patch("ringtwice.runner.LLMClient") as mock_llm,
        ):
            backend_instance = MagicMock()
            backend_instance.search.return_value = iter([mock_email])
            mock_backend.return_value = backend_instance

            llm_instance = MagicMock()
            llm_instance.process_batch.return_value = iter([mock_response])
            mock_llm.return_value = llm_instance

            ask(
                parse_query="Extract info",
                output_dir=str(output_dir),
                config_file=str(tmp_path / "config.toml"),
                batch=False,
                legacy=True,
            )

            assert llm_instance.process_batch.called

    def test_batch_mode_combines_emails(
        self,
        tmp_path: Path,
        mock_config: Config,
        mock_response: LLMResponse,
    ) -> None:
        """Test batch mode combines multiple emails."""
        output_dir = tmp_path / "output"

        emails = [
            Email(
                uid=str(i),
                subject=f"Email {i}",
                sender="sender@example.com",
                recipients=["me@example.com"],
                date=datetime(2024, 1, 15, 10, i),
                text=f"Content {i}",
                html=None,
            )
            for i in range(3)
        ]

        with (
            patch("ringtwice.runner.Config.load", return_value=mock_config),
            patch("ringtwice.runner.create_backend") as mock_backend,
            patch("ringtwice.runner.LLMClient") as mock_llm,
        ):
            backend_instance = MagicMock()
            backend_instance.search.return_value = iter(emails)
            mock_backend.return_value = backend_instance

            llm_instance = MagicMock()
            llm_instance.process_batch.return_value = iter([mock_response])
            mock_llm.return_value = llm_instance

            ask(
                parse_query="Extract info",
                output_dir=str(output_dir),
                config_file=str(tmp_path / "config.toml"),
                batch=True,
                legacy=True,
            )

            assert llm_instance.process_batch.called

    def test_respects_max_emails(
        self,
        tmp_path: Path,
        mock_config: Config,
        mock_response: LLMResponse,
    ) -> None:
        """Test max_emails limits processing."""
        output_dir = tmp_path / "output"

        emails = [
            Email(
                uid=str(i),
                subject=f"Email {i}",
                sender="sender@example.com",
                recipients=["me@example.com"],
                date=datetime(2024, 1, 15, 10, i),
                text=f"Content {i}",
                html=None,
            )
            for i in range(10)
        ]

        with (
            patch("ringtwice.runner.Config.load", return_value=mock_config),
            patch("ringtwice.runner.create_backend") as mock_backend,
            patch("ringtwice.runner.LLMClient") as mock_llm,
        ):
            backend_instance = MagicMock()
            backend_instance.search.return_value = iter(emails)
            mock_backend.return_value = backend_instance

            llm_instance = MagicMock()
            llm_instance.process_batch.return_value = iter([mock_response])
            mock_llm.return_value = llm_instance

            ask(
                parse_query="Extract info",
                output_dir=str(output_dir),
                config_file=str(tmp_path / "config.toml"),
                max_emails=3,
                legacy=True,
            )

            assert llm_instance.process_batch.call_count == 3

    def test_handles_no_emails(
        self,
        tmp_path: Path,
        mock_config: Config,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test handling when no emails found."""
        output_dir = tmp_path / "output"

        with (
            patch("ringtwice.runner.Config.load", return_value=mock_config),
            patch("ringtwice.runner.create_backend") as mock_backend,
            patch("ringtwice.runner.LLMClient"),
        ):
            backend_instance = MagicMock()
            backend_instance.search.return_value = iter([])
            mock_backend.return_value = backend_instance

            ask(
                parse_query="Extract info",
                output_dir=str(output_dir),
                config_file=str(tmp_path / "config.toml"),
                legacy=True,
            )

        captured = capsys.readouterr()
        assert "No emails to process" in captured.out

    def test_uses_search_criteria(
        self,
        tmp_path: Path,
        mock_config: Config,
        mock_email: Email,
        mock_response: LLMResponse,
    ) -> None:
        """Test search criteria are passed to backend."""
        output_dir = tmp_path / "output"

        with (
            patch("ringtwice.runner.Config.load", return_value=mock_config),
            patch("ringtwice.runner.create_backend") as mock_backend,
            patch("ringtwice.runner.LLMClient") as mock_llm,
        ):
            backend_instance = MagicMock()
            backend_instance.search.return_value = iter([mock_email])
            mock_backend.return_value = backend_instance

            llm_instance = MagicMock()
            llm_instance.process_batch.return_value = iter([mock_response])
            mock_llm.return_value = llm_instance

            ask(
                parse_query="Extract info",
                output_dir=str(output_dir),
                config_file=str(tmp_path / "config.toml"),
                search_query="meeting",
                sender="boss@example.com",
                date_from="2024-01-01",
                legacy=True,
            )

            backend_instance.search.assert_called_once()
            criteria = backend_instance.search.call_args[0][0]
            assert criteria.query == "meeting"
            assert criteria.sender == ["boss@example.com"]
            assert criteria.date_from is not None


class TestConfig:
    """Tests for config command."""

    def test_config_command_displays_path_and_content(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Ensure config command shows the path and parsed content."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[llm]
endpoint = "https://api.example.com"
api_key = "key"
model = "model"

[mailbox.default]
type = "gmail"
credentials_file = "gmail.json"
"""
        )

        fake_backend = MagicMock()
        fake_backend.search.return_value = iter([])

        cli = RingtwiceCLI()
        with patch("ringtwice.cli.create_backend", return_value=fake_backend):
            cli.config(config_file=str(config_file))

        captured = capsys.readouterr().out
        assert str(config_file) in captured
        assert '"mailbox"' in captured
        assert '"default"' in captured
        assert "Mailbox connectivity" in captured
        assert "default" in captured
        assert "OK" in captured

    def test_config_command_shows_path_on_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Even on parse errors, config path should be shown."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[llm]
endpoint = "https://api.example.com"
api_key = "key"
model = "model"

[[mailbox]]  # legacy, should fail
type = "gmail"
credentials_file = "/tmp/gmail.json"
"""
        )

        cli = RingtwiceCLI()
        with pytest.raises(ValueError):
            cli.config(config_file=str(config_file))

        captured = capsys.readouterr().out
        assert str(config_file) in captured
        assert "Failed to parse config" in captured

    def test_show_config_standalone(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test standalone show_config function."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[llm]
endpoint = "https://api.example.com"
api_key = "key"
model = "model"

[mailbox.default]
type = "gmail"
credentials_file = "gmail.json"
"""
        )

        fake_backend = MagicMock()
        fake_backend.search.return_value = iter([])

        with patch("ringtwice.cli.create_backend", return_value=fake_backend):
            show_config(config_file=str(config_file))

        captured = capsys.readouterr().out
        assert str(config_file) in captured
