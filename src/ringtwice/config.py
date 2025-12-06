"""Configuration loading with TOML and environment variable interpolation."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Literal

from platformdirs import user_config_dir
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM endpoint configuration."""

    endpoint: str
    api_key: str
    model: str
    max_context: int = 8192


class MailboxConfig(BaseModel):
    """Single mailbox configuration."""

    type: Literal["gmail", "imap"]
    # Gmail-specific
    credentials_file: Path | None = None
    # IMAP-specific
    host: str | None = None
    port: int = 993
    username: str | None = None
    password: str | None = None


class Config(BaseModel):
    """Root configuration model."""

    llm: LLMConfig
    mailbox: dict[str, MailboxConfig] = Field(min_length=1)

    @classmethod
    def load(cls, config_path: Path | None = None) -> Config:
        """Load config from TOML file with env var interpolation."""
        path = config_path or get_default_config_path()
        path = Path(path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        config_dir = path.parent

        text = path.read_text()
        interpolated = interpolate_env_vars(text)
        data = tomllib.loads(interpolated)
        mailbox_section = data.get("mailbox")
        if isinstance(mailbox_section, list):
            raise ValueError(
                "Mailbox config must be keyed tables, e.g. [mailbox.work]. "
                "Array-of-tables syntax [[mailbox]] is no longer supported."
            )
        config = cls.model_validate(data)

        # Resolve relative credentials_file paths relative to config directory
        for mb in config.mailbox.values():
            if mb.credentials_file is not None:
                cred_path = Path(mb.credentials_file).expanduser()
                # If not absolute and doesn't start with ~, resolve relative to config dir
                if not cred_path.is_absolute():
                    cred_path = config_dir / cred_path
                mb.credentials_file = cred_path.resolve()

        return config


def interpolate_env_vars(text: str) -> str:
    """Replace ${VAR} with environment variable values, skipping comments."""
    pattern = r"\$\{([^}]+)\}"

    def replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            raise ValueError(f"Environment variable {var_name} not set")
        return value

    # Process line by line, skipping comments
    lines = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            lines.append(line)  # Keep comment unchanged
        else:
            lines.append(re.sub(pattern, replacer, line))
    return "\n".join(lines)


def get_default_config_path() -> Path:
    """Return platform-appropriate config path."""
    return Path(user_config_dir("ringtwice")) / "config.toml"
