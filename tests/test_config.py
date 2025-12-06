"""Tests for configuration loading."""

from pathlib import Path

import pytest

from ringtwice.config import (
    Config,
    get_default_config_path,
    interpolate_env_vars,
)


class TestInterpolateEnvVars:
    """Tests for environment variable interpolation."""

    def test_replaces_single_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test single env var interpolation."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        result = interpolate_env_vars("${TEST_VAR}")
        assert result == "test_value"

    def test_replaces_multiple_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test multiple env vars in same string."""
        monkeypatch.setenv("VAR1", "first")
        monkeypatch.setenv("VAR2", "second")
        result = interpolate_env_vars("${VAR1} and ${VAR2}")
        assert result == "first and second"

    def test_preserves_text_without_vars(self) -> None:
        """Test text without env vars is unchanged."""
        text = "no variables here"
        assert interpolate_env_vars(text) == text

    def test_raises_on_missing_var(self) -> None:
        """Test error on missing env var."""
        with pytest.raises(ValueError, match="NONEXISTENT_VAR_12345 not set"):
            interpolate_env_vars("${NONEXISTENT_VAR_12345}")

    def test_skips_commented_lines(self) -> None:
        """Test env vars in comments are not processed."""
        text = """# This is a comment with ${MISSING_VAR}
value = "real"
  # Indented comment ${ALSO_MISSING}"""
        # Should not raise - comments are skipped
        result = interpolate_env_vars(text)
        assert "${MISSING_VAR}" in result
        assert "${ALSO_MISSING}" in result


class TestConfig:
    """Tests for Config loading."""

    def test_load_validates_mailbox_required(self, tmp_path: Path) -> None:
        """Test that at least one mailbox is required."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[llm]
endpoint = "https://api.example.com"
api_key = "test-key"
model = "test-model"
""")
        with pytest.raises(ValueError, match="mailbox"):
            Config.load(config_file)

    def test_load_parses_gmail_mailbox(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test Gmail mailbox config parsing."""
        monkeypatch.setenv("TEST_API_KEY", "secret-key")
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[llm]
endpoint = "https://api.example.com"
api_key = "${TEST_API_KEY}"
model = "test-model"
max_context = 4096

[mailbox.work]
type = "gmail"
credentials_file = "/path/to/creds.json"
""")
        config = Config.load(config_file)

        assert config.llm.endpoint == "https://api.example.com"
        assert config.llm.api_key == "secret-key"
        assert config.llm.model == "test-model"
        assert config.llm.max_context == 4096

        assert len(config.mailbox) == 1
        gmail = config.mailbox["work"]
        assert gmail.type == "gmail"
        assert gmail.credentials_file == Path("/path/to/creds.json")

    def test_load_parses_imap_mailbox(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test IMAP mailbox config parsing."""
        monkeypatch.setenv("IMAP_USER", "user@example.com")
        monkeypatch.setenv("IMAP_PASS", "secret")
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[llm]
endpoint = "https://api.example.com"
api_key = "key"
model = "model"

[mailbox.personal]
type = "imap"
host = "imap.example.com"
port = 993
username = "${IMAP_USER}"
password = "${IMAP_PASS}"
""")
        config = Config.load(config_file)

        assert len(config.mailbox) == 1
        mb = config.mailbox["personal"]
        assert mb.type == "imap"
        assert mb.host == "imap.example.com"
        assert mb.port == 993
        assert mb.username == "user@example.com"
        assert mb.password == "secret"

    def test_load_rejects_array_of_tables(self, tmp_path: Path) -> None:
        """Reject legacy [[mailbox]] syntax with a clear error."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[llm]
endpoint = "https://api.example.com"
api_key = "key"
model = "model"

[[mailbox]]
type = "gmail"
credentials_file = "/tmp/gmail.json"
""")
        with pytest.raises(ValueError, match="keyed tables"):
            Config.load(config_file)

    def test_load_raises_on_missing_file(self, tmp_path: Path) -> None:
        """Test error when config file doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            Config.load(tmp_path / "nonexistent.toml")

    def test_load_resolves_relative_credentials_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test relative credentials_file is resolved relative to config dir."""
        monkeypatch.setenv("API_KEY", "key")
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[llm]
endpoint = "https://api.example.com"
api_key = "${API_KEY}"
model = "model"

[mailbox.test]
type = "gmail"
credentials_file = "gmail_creds.json"
""")
        config = Config.load(config_file)

        # Should be resolved to absolute path in same directory as config
        expected = tmp_path / "gmail_creds.json"
        assert config.mailbox["test"].credentials_file == expected


class TestGetDefaultConfigPath:
    """Tests for default config path."""

    def test_returns_path_object(self) -> None:
        """Test return type is Path."""
        result = get_default_config_path()
        assert isinstance(result, Path)

    def test_ends_with_config_toml(self) -> None:
        """Test path ends with config.toml."""
        result = get_default_config_path()
        assert result.name == "config.toml"
        assert "ringtwice" in str(result)
