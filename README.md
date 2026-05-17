# ringtwice

> The postman always rings twice.

Pipe your inbox through an LLM. **ringtwice** connects to Gmail or any IMAP server, strips the HTML and reply-chain clutter from emails, sends the clean text to any OpenAI-compatible API, and saves the results as JSONL files.

Use it to extract action items, summarize threads, triage support queues, or run any other structured parsing job over your email.

## Quick start

```bash
# Install
uv pip install --system -e .
# or inside a venv:
uv venv && uv sync

# Run
ringtwice ask "Extract all action items and deadlines" --max-emails 5
```

## How it works

1. **Fetch** — Connects to Gmail (via OAuth2) or any IMAP server. Supports folder selection, date ranges, sender/recipient/subject filters, and full thread retrieval.
2. **Scrub** — Drops HTML markup, quoted replies, and signatures. This matters: LLM context windows are expensive. Clean text means fewer tokens and better results.
3. **Parse** — Sends the clean text plus your prompt to the LLM (OpenAI, Ollama, vLLM, Cerebras, any OpenAI-compatible endpoint).
4. **Dump** — Saves each response as a JSONL file named `YYMMDD-HHMMSS-SENDEREMAIL-THREADSUBJECT.jsonl`.

## Configuration

ringtwice reads a TOML config file. Copy the example and edit:

```bash
cp config.example.toml config.toml
```

Key sections:

```toml
[llm]
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
model = "gpt-4o-mini"
max_context_tokens = 8192

[[mailboxes]]
name = "work"
type = "gmail"                      # or "imap"
credentials_file = "~/.config/ringtwice/gmail_credentials.json"
```

For Gmail, see [src_docs/gmail.md](src_docs/gmail.md) for the OAuth2 setup steps.

## CLI reference

```bash
ringtwice ask PROMPT [OPTIONS]

Options:
  --search-query TEXT       Gmail/IMAP search string (e.g. "from:boss@example.com")
  --thread                  Retrieve full threads (default: individual messages)
  --max-emails INT          Stop after this many emails
  --boxes TEXT              Comma-separated mailbox names to search
  --date-from TEXT          Start date (YYYY-MM-DD)
  --date-to TEXT            End date (YYYY-MM-DD)
  --sender TEXT             Filter by sender address
  --recipient TEXT          Filter by recipient address
  --subject TEXT            Filter by subject substring
  --batch / --no-batch      Combine emails before sending to LLM
  --batch-size INT          Emails per LLM call when batching
  --output-dir PATH         Where to save JSONL files (default: ./output)
  --verbose                 Debug logging
```

**Examples:**

```bash
# Summarize unread emails from your manager
ringtwice ask "Summarize this email in 2 sentences" \
  --search-query "from:manager@company.com is:unread" \
  --max-emails 20

# Extract all deadlines from the last week
ringtwice ask "List every deadline mentioned, with date and description" \
  --date-from 2024-01-01 \
  --output-dir ./deadlines

# Batch-process a support mailbox
ringtwice ask "Classify this as: question/bug/feature-request. Output JSON." \
  --boxes support \
  --batch \
  --batch-size 10
```

## Python API

```python
from ringtwice.config import load_config
from ringtwice.mailbox import create_backend, SearchCriteria
from ringtwice.processor import EmailProcessor
from ringtwice.llm import LLMClient
from ringtwice.output import OutputWriter

config = load_config("config.toml")
backend = create_backend(config.mailboxes["work"])
processor = EmailProcessor()
llm = LLMClient(config.llm)
writer = OutputWriter(output_dir="./output")

criteria = SearchCriteria(query="project alpha", max_results=50)
for email in backend.search(criteria, folders=["INBOX"]):
    clean = processor.process(email)
    response = llm.parse(clean, prompt="Extract action items as JSON list")
    writer.write(email, response)
```

## Project layout

```
src/ringtwice/
├── cli.py          # Fire CLI entry point
├── config.py       # TOML config loading with env-var interpolation
├── mailbox.py      # Gmail (OAuth2) and IMAP backends
├── processor.py    # Email scrubbing: HTML→text, quote/signature removal
├── llm.py          # OpenAI-compatible client with token-aware chunking
└── output.py       # JSONL writer with slugified filenames
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `imap-tools` | IMAP access |
| `google-api-python-client` | Gmail API |
| `google-auth-oauthlib` | Gmail OAuth2 |
| `html2text` | HTML → plain text |
| `mail-parser-reply` | Quote and signature removal |
| `openai` | LLM client (supports custom `base_url`) |
| `semantic-text-splitter` + `tiktoken` | Token-aware chunking |
| `pydantic` | Config validation |
| `tenacity` | Retry logic |
| `fire` | CLI |

## Docs

| Guide | Contents |
|-------|----------|
| [Installation](src_docs/installation.md) | Setup and requirements |
| [Gmail Setup](src_docs/gmail.md) | OAuth2 credential creation |
| [CLI Usage](src_docs/cli.md) | All flags with examples |
| [Configuration](src_docs/configuration.md) | Config file reference |
| [Python API](src_docs/python-api.md) | Library usage |
| [Development](src_docs/development.md) | Tests and contributing |

## License

MIT
