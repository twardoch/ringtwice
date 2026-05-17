"""Dumps LLM results to disk in JSONL format."""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from pathvalidate import sanitize_filename
from slugify import slugify

from ringtwice.llm import LLMResponse
from ringtwice.mailbox import Email

# Patterns indicating empty/irrelevant LLM responses
EMPTY_RESPONSE_PATTERNS = [
    r"^\s*$",  # Empty or whitespace only
    r"^\s*\(.*no.*found.*\)\s*$",  # "(no ... found)"
    r"^\s*\[.*no.*found.*\]\s*$",  # "[no ... found]"
    r"^.*did not find any.*$",  # "did not find any"
    r"^.*no.*orders.*found.*$",  # "no orders found"
    r"^.*no.*serial.*numbers.*$",  # "no serial numbers"
    r"^.*no.*license.*keys.*$",  # "no license keys"
    r"^.*no.*relevant.*$",  # "no relevant"
    r"^.*nothing.*found.*$",  # "nothing found"
    r"^.*none.*found.*$",  # "none found"
    r"^.*could not find.*$",  # "could not find"
    r"^.*unable to find.*$",  # "unable to find"
    r"^\s*n/?a\s*$",  # "N/A" or "n/a"
    r"^\s*-+\s*$",  # Just dashes
    r"^\s*none\s*$",  # Just "none"
]


def is_empty_response(content: str) -> bool:
    """Return True if the LLM yielded nothing useful (e.g. empty string or {})."""
    if not content:
        return True

    # Normalize for checking
    normalized = content.strip().lower()

    # Very short responses are likely meaningless
    if len(normalized) < 10:
        return True

    # Check against patterns
    for pattern in EMPTY_RESPONSE_PATTERNS:
        if re.match(pattern, normalized, re.IGNORECASE | re.DOTALL):
            return True

    return False


def extract_email_address(sender: str) -> str:
    """Strip names from 'Name <email@example.com>' and return just the address."""
    match = re.search(r"<([^>]+)>", sender)
    if match:
        return match.group(1)
    # If no angle brackets, assume the whole thing is an email or return as-is
    if "@" in sender:
        return sender.strip()
    return sender


def truncate(text: str, max_length: int = 30) -> str:
    """Chop strings that exceed max_length and append '...'."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def format_email_header(email: Email, max_subject: int = 30) -> str:
    """Build a one-line summary: YYYY-MM-DD HH:MM | sender | Subject."""
    timestamp = email.date.strftime("%Y-%m-%d %H:%M")
    sender = extract_email_address(email.sender)
    subject = truncate(email.subject, max_subject)
    return f"{timestamp} | {sender} | {subject}"


def format_batch_header(emails: list[Email], max_subject: int = 25) -> str:
    """Summarize a batch of emails. Lists the first few, notes the rest."""
    if not emails:
        return "Batch: (empty)"

    lines = []
    # Show up to 3 emails with details
    for email in emails[:3]:
        lines.append(format_email_header(email, max_subject))

    if len(emails) > 3:
        lines.append(f"  ... (+{len(emails) - 3} more emails)")

    return "\n".join(lines)


def get_output_filename(email: Email) -> str:
    """Construct a filesystem-safe string from the date, sender, and subject."""
    timestamp = email.date.strftime("%y%m%d-%H%M%S")
    sender = slugify(email.sender.split("@")[0], max_length=20)
    subject = slugify(email.subject, max_length=30)
    filename = f"{timestamp}-{sender}-{subject}.jsonl"
    return sanitize_filename(filename)


def get_default_output_dir() -> Path:
    """Build a timestamped folder inside outputs/ to hold the run's JSONL files."""
    timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
    return Path.cwd() / "output" / f"{timestamp}"


class OutputWriter:
    """Serializes LLM insights into line-delimited JSON."""

    def __init__(self, output_dir: Path, max_width: int = 70) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._max_width = max_width
        self._skipped_count = 0

    @property
    def skipped_count(self) -> int:
        """Total ignored responses due to irrelevance or emptiness."""
        return self._skipped_count

    def _wrap_content(self, content: str) -> str:
        """Hard-wrap text to 80 characters for readability."""
        lines = []
        for line in content.split("\n"):
            if len(line) > self._max_width:
                wrapped = textwrap.fill(line, width=self._max_width)
                lines.append(wrapped)
            else:
                lines.append(line)
        return "\n".join(lines)

    def write(self, email: Email, response: LLMResponse) -> Path | None:
        """Append an email and its LLM response to a JSONL file.
        
        Returns the file path, or None if the response was empty.
        """
        # Skip empty responses
        if is_empty_response(response.content):
            self._skipped_count += 1
            return None

        filename = get_output_filename(email)
        filepath = self._output_dir / filename

        record = {
            "email": {
                "uid": email.uid,
                "subject": email.subject,
                "sender": email.sender,
                "recipients": email.recipients,
                "date": email.date.isoformat(),
            },
            "response": asdict(response),
            "timestamp": datetime.now().isoformat(),
        }

        with filepath.open("a") as f:
            f.write(json.dumps(record) + "\n")

        # Print formatted response with better header
        header = format_email_header(email)
        content = self._wrap_content(response.content.strip())
        print(f"\n---\n{header}\n\n{content}\n")

        return filepath

    def write_batch(self, emails: list[Email], response: LLMResponse) -> Path | None:
        """Append a batch of emails and their combined LLM response to a JSONL file.
        
        Returns the file path, or None if the response was empty.
        """
        # Skip empty responses
        if is_empty_response(response.content):
            self._skipped_count += 1
            return None

        # Use first email's metadata for filename
        filename = get_output_filename(emails[0]) if emails else "batch.jsonl"
        filepath = self._output_dir / filename

        record = {
            "emails": [
                {
                    "uid": e.uid,
                    "subject": e.subject,
                    "sender": e.sender,
                    "recipients": e.recipients,
                    "date": e.date.isoformat(),
                }
                for e in emails
            ],
            "response": asdict(response),
            "timestamp": datetime.now().isoformat(),
        }

        with filepath.open("a") as f:
            f.write(json.dumps(record) + "\n")

        # Print formatted response with better header
        header = format_batch_header(emails)
        content = self._wrap_content(response.content.strip())
        print(f"\n---\nBatch ({len(emails)} emails):\n{header}\n\n{content}\n")

        return filepath
