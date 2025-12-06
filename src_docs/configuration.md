# Configuration

ringtwice uses a TOML configuration file with environment variable interpolation.

## Config file location

Find your config directory:

```bash
python -c "from platformdirs import user_config_dir; print(user_config_dir('ringtwice'))"
```

This returns:

- **macOS**: `~/Library/Application Support/ringtwice`
- **Linux**: `~/.config/ringtwice`
- **Windows**: `%APPDATA%\ringtwice`

## Full configuration example

```toml
[llm]
endpoint = "${LLM_API_ENDPOINT}"  # Environment variable interpolation
api_key = "${LLM_API_KEY}"
model = "llama-3.1-70b"
max_context = 8192  # Token limit for context window

[mailbox.personal]          # Name used with --boxes flag
type = "gmail"              # "gmail" or "imap"
credentials_file = "gmail_credentials.json"

[mailbox.work]
type = "imap"
host = "imap.company.com"
port = 993
username = "${WORK_EMAIL}"
password = "${WORK_PASSWORD}"
```

## LLM section

| Field | Description |
|-------|-------------|
| `endpoint` | OpenAI-compatible API endpoint URL |
| `api_key` | API key for authentication |
| `model` | Model name to use |
| `max_context` | Maximum token context window |

Environment variables can be referenced with `${VAR_NAME}` syntax.

## Mailbox section

Each mailbox has a name (e.g., `[mailbox.personal]`) used with the `--boxes` flag.

### Gmail configuration

```toml
[mailbox.gmail]
type = "gmail"
credentials_file = "gmail_credentials.json"  # Relative to config dir
```

See [Gmail Setup](gmail.md) for obtaining credentials.

### IMAP configuration

```toml
[mailbox.work]
type = "imap"
host = "imap.company.com"
port = 993
username = "user@company.com"
password = "${IMAP_PASSWORD}"
```

## Using the config command

Verify your configuration:

```bash
ringtwice config
```

This prints the resolved config path and parsed contents with environment variables applied.

Use a specific config file:

```bash
ringtwice config --config-file ./my-config.toml
```
