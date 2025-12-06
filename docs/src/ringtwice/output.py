"""Output handling: save LLM responses as JSONL files."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from pathvalidate import sanitize_filename
from slugify import slugify

from ringtwice.llm import LLMResponse
from ringtwice.mailbox import Email


def get_output_filename(email: Email) -> str:
    """Generate output filename from email metadata."""
    timestamp = email.date.strftime("%y%m%d-%H%M%S")
    sender = slugify(email.sender.split("@")[0], max_length=20)
    subject = slugify(email.subject, max_length=30)
    filename = f"{timestamp}-{sender}-{subject}.jsonl"
    return sanitize_filename(filename)


def get_default_output_dir() -> Path:
    """Create default output directory with timestamp inside outputs/."""
    timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
    return Path.cwd() / "output" / f"{timestamp}"


class OutputWriter:
    """Writes LLM responses to JSONL files."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, email: Email, response: LLMResponse) -> Path:
        """Write single response to JSONL file."""
        filename = get_output_filename(email)
        filepath = self._output_dir / filename

        record = {
            "email": {
                "uid": email.uid,
                "subject": email.subject,
                "sender": email.sender,
                "date": email.date.isoformat(),
            },
            "response": asdict(response),
            "timestamp": datetime.now().isoformat(),
        }

        with filepath.open("a") as f:
            f.write(json.dumps(record) + "\n")

        return filepath

    def write_batch(self, emails: list[Email], response: LLMResponse) -> Path:
        """Write batch response to JSONL file."""
        # Use first email's metadata for filename
        filename = get_output_filename(emails[0]) if emails else "batch.jsonl"
        filepath = self._output_dir / filename

        record = {
            "emails": [
                {
                    "uid": e.uid,
                    "subject": e.subject,
                    "sender": e.sender,
                    "date": e.date.isoformat(),
                }
                for e in emails
            ],
            "response": asdict(response),
            "timestamp": datetime.now().isoformat(),
        }

        with filepath.open("a") as f:
            f.write(json.dumps(record) + "\n")

        return filepath
