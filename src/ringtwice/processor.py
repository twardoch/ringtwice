"""Email minification: remove HTML, quotes, and signatures."""

from __future__ import annotations

import html2text
from mailparser_reply import EmailReplyParser

from ringtwice.mailbox import Email


class EmailProcessor:
    """Minifies emails by removing HTML, quotes, signatures."""

    def __init__(self, languages: list[str] | None = None) -> None:
        self._languages = languages or ["en"]
        self._html2text = html2text.HTML2Text()
        self._html2text.ignore_links = False
        self._html2text.ignore_images = True
        self._html2text.body_width = 0  # Don't wrap

    def process(self, email: Email) -> str:
        """Process email to clean text."""
        # Get text content
        if email.text:
            text = email.text
        elif email.html:
            text = self._html2text.handle(email.html)
        else:
            return ""

        # Remove quotes and signatures
        try:
            parsed = EmailReplyParser(languages=self._languages).read(text=text)
            # Get the latest reply body (without quotes/signatures)
            if parsed.replies:
                return parsed.replies[0].body.strip()
        except Exception:
            # Fall back to original text if parsing fails
            pass

        return text.strip()

    def process_thread(self, emails: list[Email]) -> str:
        """Process a thread of emails into combined text."""
        parts = []
        for email in emails:
            header = f"From: {email.sender}\nDate: {email.date}\nSubject: {email.subject}\n"
            body = self.process(email)
            parts.append(f"{header}\n{body}")
        return "\n---\n".join(parts)
