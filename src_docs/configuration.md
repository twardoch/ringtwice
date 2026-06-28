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

Place your `config.toml` in that directory, or pass `--config-file <path>` to
override the location for any run.

---

## Full configuration example

```toml
[llm]
endpoint    = "${LLM_API_ENDPOINT}"   # environment variable interpolation
api_key     = "${LLM_API_KEY}"
model       = "llama-3.1-70b"
max_context = 8192                    # token limit for context window

[mailbox.personal]          # name used with --boxes flag
type             = "gmail"
credentials_file = "gmail_credentials.json"   # relative to config dir

[mailbox.work]
type     = "imap"
host     = "imap.company.com"
port     = 993
username = "${WORK_EMAIL}"
password = "${WORK_PASSWORD}"
```

---

## `[llm]` section reference

All fields are required unless a default is noted.

| Key | Type | Default | Description |
|---|---|---|---|
| `endpoint` | string | — | Base URL of the OpenAI-compatible API (e.g. `https://api.openai.com/v1` or `https://api.cerebras.ai/v1`) |
| `api_key` | string | — | API key for authentication. Use `${MY_KEY}` to read from an env var |
| `model` | string | — | Model identifier as the provider expects it (e.g. `gpt-4o`, `llama-3.1-70b`) |
| `max_context` | integer | `8192` | Maximum token budget for a single LLM call. ringtwice reserves ~1 000 tokens for the prompt and splits the email body into chunks that fit the remainder |

### Choosing `max_context`

Set this to the model's actual context window minus a comfortable safety
margin.  If emails are silently truncated or you see `context_length_exceeded`
errors, lower `max_context`.  Common values:

| Model family | Recommended `max_context` |
|---|---|
| GPT-4o / GPT-4 Turbo | 100000 |
| GPT-3.5 Turbo | 14000 |
| Llama 3 70B (Cerebras) | 8192 |
| Mistral 7B | 4096 |
| Ollama local models | 4096 |

---

## `[mailbox.<name>]` section reference

Each mailbox block has a name (e.g. `[mailbox.personal]`) that is used with
the `--boxes` flag.  You may define as many mailboxes as you like.

### Common fields

| Key | Type | Required | Description |
|---|---|---|---|
| `type` | `"gmail"` or `"imap"` | Yes | Backend to use |

### Gmail-specific fields (`type = "gmail"`)

| Key | Type | Default | Description |
|---|---|---|---|
| `credentials_file` | path string | — | Path to the OAuth client secrets JSON downloaded from Google Cloud Console.  Relative paths are resolved from the config directory |

See [Gmail Setup](gmail.md) for how to obtain this file.

```toml
[mailbox.personal]
type             = "gmail"
credentials_file = "gmail_credentials.json"
```

### IMAP-specific fields (`type = "imap"`)

| Key | Type | Default | Description |
|---|---|---|---|
| `host` | string | — | IMAP server hostname |
| `port` | integer | `993` | IMAP port (993 = IMAPS/TLS; 143 = plain/STARTTLS) |
| `username` | string | — | Login username (usually the full email address) |
| `password` | string | — | Login password or app-specific password |

See [IMAP Quickstart](imap.md) for provider-specific notes.

```toml
[mailbox.work]
type     = "imap"
host     = "imap.company.com"
port     = 993
username = "${WORK_EMAIL}"
password = "${WORK_PASSWORD}"
```

---

## Environment variable interpolation

Any `${VAR_NAME}` token in `config.toml` is replaced with the matching
environment variable at load time.  Lines beginning with `#` are skipped so
you can comment freely without accidental substitution.

Load a `.env` file automatically by placing it in the same directory as
your config, or export variables in your shell before running ringtwice.

```bash
# .env (next to config.toml)
LLM_API_ENDPOINT=https://api.cerebras.ai/v1
LLM_API_KEY=cb-xxxxxxxxxxxxxxxxxxxxxxxx
WORK_EMAIL=me@company.com
WORK_PASSWORD=s3cr3t
```

If a referenced variable is not set, ringtwice raises a `ValueError` with
the variable name so you know exactly what is missing.

---

## Using the config command

Verify your configuration and test mailbox connections:

```bash
ringtwice config
```

This prints:

1. The resolved config file path
2. The fully-interpolated config as JSON (secrets visible — don't share the output)
3. A connectivity check for each mailbox showing OK or the error

Use a specific config file:

```bash
ringtwice config --config-file ./my-config.toml
```

---

## JSONL output schema

ringtwice writes one JSONL file per email (or per batch) under
`output/<timestamp>/`.  Each line is a self-contained JSON object.

### Single-email record

```json
{
  "email": {
    "uid": "18b3f2a9c1d4",
    "subject": "Q3 budget review",
    "sender": "Alice <alice@example.com>",
    "recipients": ["bob@example.com", "carol@example.com"],
    "date": "2024-07-15T09:42:00+02:00"
  },
  "response": {
    "content": "Action items:\n1. Review spreadsheet by July 20\n2. ...",
    "model": "llama-3.1-70b",
    "usage_prompt_tokens": 812,
    "usage_completion_tokens": 134
  },
  "timestamp": "2024-07-15T11:03:22.418291"
}
```

### Batch record

When `--batch` is used, multiple emails are grouped into a single LLM call.
The record contains an `emails` array instead of a single `email` object:

```json
{
  "emails": [
    {
      "uid": "18b3f2a9c1d4",
      "subject": "Q3 budget review",
      "sender": "alice@example.com",
      "recipients": ["bob@example.com"],
      "date": "2024-07-15T09:42:00+02:00"
    },
    {
      "uid": "18b3f2a9c2e5",
      "subject": "Re: Q3 budget review",
      "sender": "bob@example.com",
      "recipients": ["alice@example.com"],
      "date": "2024-07-15T10:11:00+02:00"
    }
  ],
  "response": {
    "content": "Thread summary: ...",
    "model": "llama-3.1-70b",
    "usage_prompt_tokens": 1540,
    "usage_completion_tokens": 210
  },
  "timestamp": "2024-07-15T11:03:25.002114"
}
```

### Field reference

| Path | Type | Description |
|---|---|---|
| `email.uid` | string | Provider-specific message ID |
| `email.subject` | string | Subject header (may be empty for some automated messages) |
| `email.sender` | string | `From:` header value, may include display name |
| `email.recipients` | string[] | `To:` header split on commas |
| `email.date` | ISO 8601 string | Message date with timezone offset when available |
| `emails` | object[] | Present instead of `email` in batch mode; same fields per item |
| `response.content` | string | Raw text returned by the LLM |
| `response.model` | string | Model name echoed back by the API |
| `response.usage_prompt_tokens` | integer | Tokens consumed by the prompt + email content |
| `response.usage_completion_tokens` | integer | Tokens in the LLM reply |
| `timestamp` | ISO 8601 string | Wall-clock time when the record was written |

!!! tip "Parsing JSONL"
    Read output files with standard tools:
    ```bash
    # Pretty-print each record
    jq '.' output/240715-110322/*.jsonl

    # Extract just the LLM responses
    jq -r '.response.content' output/240715-110322/*.jsonl
    ```
