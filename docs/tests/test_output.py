"""Tests for output handling."""

import json
from datetime import datetime
from pathlib import Path

from ringtwice.llm import LLMResponse
from ringtwice.mailbox import Email
from ringtwice.output import OutputWriter, get_default_output_dir, get_output_filename


def make_email(
    subject: str = "Test Subject",
    sender: str = "john.doe@example.com",
    date: datetime | None = None,
) -> Email:
    """Helper to create test emails."""
    return Email(
        uid="1",
        subject=subject,
        sender=sender,
        recipients=["me@example.com"],
        date=date or datetime(2024, 1, 15, 10, 30, 0),
        text="content",
        html=None,
    )


def make_response(content: str = "Response text") -> LLMResponse:
    """Helper to create test responses."""
    return LLMResponse(
        content=content,
        model="test-model",
        usage_prompt_tokens=10,
        usage_completion_tokens=5,
    )


class TestGetOutputFilename:
    """Tests for output filename generation."""

    def test_format(self) -> None:
        """Test filename follows YYMMDD-HHMMSS-sender-subject.jsonl format."""
        email = make_email(
            subject="Important Meeting Notes",
            sender="john.doe@example.com",
            date=datetime(2024, 1, 15, 10, 30, 0),
        )
        filename = get_output_filename(email)
        assert filename.startswith("240115-103000-")
        assert "john" in filename.lower()
        assert filename.endswith(".jsonl")

    def test_sanitizes_special_chars(self) -> None:
        """Test special characters are removed from filename."""
        email = make_email(
            subject="Re: [URGENT!] Meeting?? (updated)",
            sender="test+user@example.com",
        )
        filename = get_output_filename(email)
        # Should not contain special chars that are invalid in filenames
        assert "?" not in filename
        assert "[" not in filename
        assert "!" not in filename

    def test_truncates_long_subject(self) -> None:
        """Test long subjects are truncated."""
        email = make_email(
            subject="A" * 100,  # Very long subject
        )
        filename = get_output_filename(email)
        # Filename should be reasonable length
        assert len(filename) < 100

    def test_handles_empty_subject(self) -> None:
        """Test empty subject produces valid filename."""
        email = make_email(subject="")
        filename = get_output_filename(email)
        assert filename.endswith(".jsonl")
        assert len(filename) > len(".jsonl")


class TestGetDefaultOutputDir:
    """Tests for default output directory."""

    def test_returns_path_object(self) -> None:
        """Test return type is Path."""
        result = get_default_output_dir()
        assert isinstance(result, Path)

    def test_parent_is_output(self) -> None:
        """Test parent directory is 'output'."""
        result = get_default_output_dir()
        assert result.parent.name == "output"

    def test_name_is_timestamp(self) -> None:
        """Test directory name is timestamp format YYMMDD-HHMMSS."""
        result = get_default_output_dir()
        name = result.name
        # Should be 13 chars: YYMMDD-HHMMSS
        assert len(name) == 13
        # Should have dash in middle
        assert name[6] == "-"
        # Should be mostly numeric
        assert name[:6].isdigit()
        assert name[7:].isdigit()


class TestOutputWriter:
    """Tests for OutputWriter."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        """Test output directory is created if missing."""
        output_dir = tmp_path / "new_dir" / "nested"
        OutputWriter(output_dir)  # Creates directory on init
        assert output_dir.exists()
        assert output_dir.is_dir()

    def test_write_creates_file(self, tmp_path: Path) -> None:
        """Test write creates JSONL file."""
        writer = OutputWriter(tmp_path)
        email = make_email()
        response = make_response()

        filepath = writer.write(email, response)

        assert filepath.exists()
        assert filepath.suffix == ".jsonl"

    def test_write_content_is_valid_jsonl(self, tmp_path: Path) -> None:
        """Test written content is valid JSONL."""
        writer = OutputWriter(tmp_path)
        email = make_email()
        response = make_response("Test response")

        filepath = writer.write(email, response)

        with filepath.open() as f:
            line = f.readline()
            data = json.loads(line)

        assert data["email"]["uid"] == "1"
        assert data["email"]["subject"] == "Test Subject"
        assert data["response"]["content"] == "Test response"
        assert "timestamp" in data

    def test_write_appends_to_file(self, tmp_path: Path) -> None:
        """Test multiple writes append to same file."""
        writer = OutputWriter(tmp_path)
        email = make_email()
        response1 = make_response("First")
        response2 = make_response("Second")

        filepath1 = writer.write(email, response1)
        filepath2 = writer.write(email, response2)

        # Same file
        assert filepath1 == filepath2

        # Two lines
        lines = filepath1.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_write_batch_creates_file(self, tmp_path: Path) -> None:
        """Test write_batch creates JSONL file."""
        writer = OutputWriter(tmp_path)
        emails = [make_email(subject="Email 1"), make_email(subject="Email 2")]
        response = make_response()

        filepath = writer.write_batch(emails, response)

        assert filepath.exists()

    def test_write_batch_includes_all_emails(self, tmp_path: Path) -> None:
        """Test write_batch includes metadata for all emails."""
        writer = OutputWriter(tmp_path)
        emails = [
            make_email(subject="First"),
            make_email(subject="Second"),
        ]
        response = make_response()

        filepath = writer.write_batch(emails, response)

        with filepath.open() as f:
            data = json.loads(f.readline())

        assert len(data["emails"]) == 2
        assert data["emails"][0]["subject"] == "First"
        assert data["emails"][1]["subject"] == "Second"

    def test_write_batch_empty_list(self, tmp_path: Path) -> None:
        """Test write_batch handles empty email list."""
        writer = OutputWriter(tmp_path)
        response = make_response()

        filepath = writer.write_batch([], response)

        assert filepath.name == "batch.jsonl"
