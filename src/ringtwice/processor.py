"""Mail cleaner. Strips HTML, signatures, and reply trails to save tokens."""

from __future__ import annotations

import html2text
from mailparser_reply import EmailReplyParser

from ringtwice.mailbox import Email


class EmailProcessor:
    """Strips email clutter before feeding text to the LLM.

    Two passes reduce token cost significantly:

    Pass 1 — HTML → plain text (html2text):
        HTML email bodies contain tags, inline styles, and base64 images that
        consume tokens without carrying semantic content.  html2text converts
        them to Markdown-like plain text, keeping links (useful for context)
        but discarding images (rarely useful for LLM parsing).

    Pass 2 — quote / signature removal (mail-parser-reply):
        Forwarded messages and reply threads repeat earlier content for each
        message.  mail-parser-reply isolates the *latest* reply fragment so the
        LLM sees only new information.  Keeping quoted history would waste
        30-80 % of the context window on content the LLM already processed in
        earlier emails.
    """

    def __init__(self, languages: list[str] | None = None) -> None:
        self._languages = languages or ["en"]
        # Configure html2text for token-efficient output:
        # - Keep links: anchor text alone strips too much context.
        # - Drop images: alt text adds little; data URIs are enormous.
        # - body_width=0: disable line-wrapping so we count tokens, not columns.
        self._html2text = html2text.HTML2Text()
        self._html2text.ignore_links = False
        self._html2text.ignore_images = True
        self._html2text.body_width = 0  # Don't wrap

    def process(self, email: Email) -> str:
        """Strip HTML, signatures, and quotes from a single email.

        Returns the cleaned body string, or an empty string for empty emails.
        """
        # Pass 1: obtain a plain-text representation.
        # Prefer the text/plain MIME part when available; fall back to
        # converting text/html.  Plain text skips html2text overhead and tends
        # to be cleaner for quoted-reply detection.
        if email.text:
            text = email.text
        elif email.html:
            # Pass 1b: HTML → plain text.  This alone can reduce token count
            # by 40-70 % for typical marketing or client-mail HTML bodies.
            text = self._html2text.handle(email.html)
        else:
            return ""

        # Pass 2: quote / signature stripping.
        # mail-parser-reply segments the message into Reply objects ordered
        # from newest to oldest.  replies[0].body is the freshest content the
        # sender actually typed — everything after is quoted context.
        try:
            parsed = EmailReplyParser(languages=self._languages).read(text=text)
            # Get the latest reply body (without quotes/signatures)
            if parsed.replies:
                body = parsed.replies[0].body
                if isinstance(body, str):
                    return body.strip()
                return str(body).strip()
        except Exception:
            # Fall back to original text if parsing fails
            pass

        return text.strip()

    def process_thread(self, emails: list[Email]) -> str:
        """Combine multiple emails into a single chronological transcript."""
        parts = []
        for email in emails:
            header = f"From: {email.sender}\nDate: {email.date}\nSubject: {email.subject}\n"
            body = self.process(email)
            parts.append(f"{header}\n{body}")
        return "\n---\n".join(parts)
