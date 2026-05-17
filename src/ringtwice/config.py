"""Loads settings from TOML files and interpolates environment variables."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Literal

from platformdirs import user_config_dir
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """Configuration mapping for the LLM API endpoint."""

    endpoint: str
    api_key: str
    model: str
    max_context: int = 8192


class MailboxConfig(BaseModel):
    """Credentials and connection details for a single IMAP or Gmail account."""

    type: Literal["gmail", "imap"]
    # Gmail-specific
    credentials_file: Path | None = None
    # IMAP-specific
    host: str | None = None
    port: int = 993
    username: str | None = None
    password: str | None = None


class Config(BaseModel):
    """Top-level configuration tying mailboxes and LLMs together."""

    llm: LLMConfig
    mailbox: dict[str, MailboxConfig] = Field(min_length=1)

    @classmethod
    def load(cls, config_path: Path | None = None) -> Config:
        """Read TOML, replace ${ENV_VARS}, and return the validated config object."""
        path = config_path or get_default_config_path()
        path = Path(path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Missing config file: {path}. Create it at ~/.config/ringtwice/config.toml, or pass --config-file <path>.")

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
    """Swap out ${VAR} for actual environment variables. Ignores # comments."""
    pattern = r"\$\{([^}]+)\}"

    def replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            raise ValueError(f"Missing environment variable: {var_name}. Export it or add it to your .env file.")
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
    """Find the default config file location depending on the OS."""
    return Path(user_config_dir("ringtwice")) / "config.toml"
