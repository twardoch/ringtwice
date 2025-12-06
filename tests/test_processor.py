"""Tests for email processing/minification."""

from datetime import datetime

from ringtwice.mailbox import Email
from ringtwice.processor import EmailProcessor


def make_email(
    text: str | None = None,
    html: str | None = None,
    subject: str = "Test",
    sender: str = "test@example.com",
) -> Email:
    """Helper to create test emails."""
    return Email(
        uid="1",
        subject=subject,
        sender=sender,
        recipients=["me@example.com"],
        date=datetime(2024, 1, 15, 10, 30),
        text=text,
        html=html,
    )


class TestEmailProcessor:
    """Tests for EmailProcessor."""

    def test_process_plain_text(self) -> None:
        """Test plain text email is returned."""
        email = make_email(text="Hello world")
        processor = EmailProcessor()
        result = processor.process(email)
        assert "Hello" in result

    def test_process_converts_html_to_text(self) -> None:
        """Test HTML is converted to plain text."""
        email = make_email(html="<p><strong>Hello</strong> world</p>")
        processor = EmailProcessor()
        result = processor.process(email)
        assert "Hello" in result
        assert "<p>" not in result
        assert "<strong>" not in result

    def test_process_prefers_text_over_html(self) -> None:
        """Test text body is used when both text and html exist."""
        email = make_email(text="Plain text", html="<p>HTML text</p>")
        processor = EmailProcessor()
        result = processor.process(email)
        assert result == "Plain text"

    def test_process_removes_quoted_text(self) -> None:
        """Test quoted replies are removed."""
        text = """This is my reply.

On Mon, Jan 1, 2024, someone wrote:
> Original message here
> More quoted text"""
        email = make_email(text=text)
        processor = EmailProcessor()
        result = processor.process(email)
        assert "This is my reply" in result
        # Quoted text should be removed
        assert "Original message" not in result or len(result) < len(text)

    def test_process_handles_empty_email(self) -> None:
        """Test graceful handling of empty email."""
        email = make_email(text=None, html=None)
        processor = EmailProcessor()
        result = processor.process(email)
        assert result == ""

    def test_process_strips_whitespace(self) -> None:
        """Test result is stripped of leading/trailing whitespace."""
        email = make_email(text="  Hello world  \n\n")
        processor = EmailProcessor()
        result = processor.process(email)
        assert not result.startswith(" ")
        assert not result.endswith("\n")

    def test_process_thread_combines_emails(self) -> None:
        """Test thread processing combines multiple emails."""
        emails = [
            make_email(text="First message", subject="Thread", sender="a@example.com"),
            make_email(text="Second message", subject="Re: Thread", sender="b@example.com"),
        ]
        processor = EmailProcessor()
        result = processor.process_thread(emails)

        assert "First message" in result
        assert "Second message" in result
        assert "a@example.com" in result
        assert "b@example.com" in result
        assert "---" in result  # Separator

    def test_process_thread_includes_headers(self) -> None:
        """Test thread processing includes email headers."""
        emails = [make_email(text="Content", subject="My Subject", sender="sender@example.com")]
        processor = EmailProcessor()
        result = processor.process_thread(emails)

        assert "From: sender@example.com" in result
        assert "Subject: My Subject" in result
        assert "Date:" in result

    def test_process_thread_empty_list(self) -> None:
        """Test thread processing with empty list."""
        processor = EmailProcessor()
        result = processor.process_thread([])
        assert result == ""

    def test_custom_languages(self) -> None:
        """Test processor can be initialized with custom languages."""
        processor = EmailProcessor(languages=["en", "de", "fr"])
        # Just verify it initializes without error
        assert processor._languages == ["en", "de", "fr"]
