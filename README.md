# ringtwice

A CLI tool that processes emails with LLMs. Fetch emails from Gmail or IMAP, clean them up, send them to any OpenAI-compatible LLM, and save the results.

## Installation

```bash
$ uv pip install --system -e .
```

Or with a virtual environment:

```bash
$ uv venv && uv sync
$ uv run ringtwice --help
```

## Quick Start: Gmail Example

### 1. Set up Gmail credentials

Follow the step-by-step guide: **[GMAIL.md](GMAIL.md)**

This creates a `gmail_credentials.json` file in your config directory.

### 2. Create config file

Create `config.toml` in your config directory (same folder as `gmail_credentials.json`):

```toml
[llm]
endpoint = "${LLM_API_ENDPOINT}"
api_key = "${LLM_API_KEY}"
model = "llama-3.1-70b"
max_context = 8192

[mailbox.gmail]
type = "gmail"
credentials_file = "gmail_credentials.json"
```

Config directory location:
- **macOS**: `~/Library/Application Support/ringtwice/`
- **Linux**: `~/.config/ringtwice/`
- **Windows**: `%APPDATA%\ringtwice\`

### 3. Set environment variables

```bash
export LLM_API_ENDPOINT="https://api.cerebras.ai/v1"  # or OpenAI, Together, Groq, etc.
export LLM_API_KEY="your-api-key-here"
```

### 4. Run ringtwice

```bash
ringtwice ask "Extract all action items and deadlines" --max-emails 5
```

First run opens your browser for Gmail authorization. The token is cached for future runs.

Results are saved to `./output/YYMMDD-HHMMSS/` as JSONL files.

---

## What is ringtwice?

ringtwice is a command-line tool that connects your email inbox to large language models. It fetches emails matching your criteria, cleans them up (removing HTML, signatures, quoted replies), sends the content to an LLM with your prompt, and saves structured results.

## What does it do?

1. **Fetches emails** from Gmail (via API) or any IMAP server
2. **Filters** by search query, date range, sender, recipient, or subject
3. **Cleans** email content: converts HTML to text, removes signatures, strips quoted replies
4. **Sends** to any OpenAI-compatible LLM endpoint (OpenAI, Anthropic, Cerebras, Together, Groq, Ollama, etc.)
5. **Saves** results as JSONL files with email metadata and LLM responses

## How does it work?

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Gmail/    │────▶│   Email     │────▶│    LLM      │────▶│   JSONL     │
│   IMAP      │     │  Processor  │     │   Client    │     │   Output    │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
      │                    │                   │                   │
   Search &          Strip HTML,         OpenAI-compat      One file per
   filter            signatures,          API call          email/batch
                     quotes
```

**Email backends:**
- **Gmail**: Uses the official Gmail API with OAuth2. Supports native threading and Gmail's powerful search syntax.
- **IMAP**: Uses `imap-tools` for any standard IMAP server. Works with Outlook, Yahoo, Fastmail, self-hosted, etc.

**Email processing:**
- `html2text` converts HTML emails to clean markdown-style text
- `mail-parser-reply` removes quoted replies ("On Mon, Jan 1, ... wrote:") and signatures

**LLM integration:**
- Uses the `openai` Python library with configurable `base_url`
- Works with any OpenAI-compatible endpoint
- Automatic retry with exponential backoff (via `tenacity`)
- Token-aware text splitting for long emails (via `semantic-text-splitter`)

**Output:**
- JSONL format: one JSON object per line
- Filenames: `YYMMDD-HHMMSS-sender-subject.jsonl`
- Each record contains email metadata, LLM response, and timestamps

## Why this design?

**Why Gmail API instead of IMAP for Gmail?**
Gmail's IMAP implementation is quirky and slow. The native API provides proper threading, faster search, and OAuth2 (no app passwords needed).

**Why OpenAI-compatible endpoints?**
Most LLM providers now support the OpenAI API format. One client works everywhere: OpenAI, Anthropic (via proxy), Cerebras, Together, Groq, Fireworks, Ollama, vLLM, etc.

**Why JSONL output?**
JSONL is append-friendly (no array closing brackets), streamable, and easy to process with `jq`, Python, or any JSON parser. One file per email means you can incrementally process results.

**Why clean emails before sending to LLM?**
Email threads accumulate cruft: HTML formatting, signatures repeated 10 times, entire conversation histories quoted. Cleaning reduces token usage by 50-80% and improves LLM response quality.

---

## Installation

### From source (recommended for development)

```bash
$ git clone https://github.com/yourname/ringtwice
$ cd ringtwice
$ uv pip install --system -e .
```

### With uv (isolated)

```bash
$ git clone https://github.com/yourname/ringtwice
$ cd ringtwice
$ uv sync
$ uv run ringtwice --help
```

### Requirements

- Python 3.13+
- `uv` package manager (recommended) or `pip`

---

## CLI Usage

### Basic syntax

```bash
$ ringtwice ask <PROMPT> [OPTIONS]
```

The `PROMPT` is the instruction sent to the LLM along with each email's content.

### Options

| Flag | Description |
|------|-------------|
| `--search-query` | Email search text (Gmail syntax or IMAP TEXT search) |
| `--date-from` | Filter emails after this date (YYYY-MM-DD) |
| `--date-to` | Filter emails before this date (YYYY-MM-DD) |
| `--sender` | Filter by sender address/name (comma-separated allowed) |
| `--recipient` | Filter by recipient address/name (comma-separated allowed) |
| `--subject` | Filter by subject line |
| `--max-emails` | Maximum number of emails to process |
| `--thread` | Retrieve full email threads instead of individual emails |
| `--batch` | Combine multiple emails into single LLM requests |
| `--batch-size` | Number of emails per batch (default: fit to context) |
| `--boxes` | Mailbox names to search (from config) |
| `--output-dir` | Output directory (default: `./output/YYMMDD-HHMMSS`) |
| `--config-file` | Path to config file (default: `~/.config/ringtwice/config.toml`) |

### Examples

**Extract action items from recent emails:**

```bash
$ ringtwice ask "List all action items, tasks, and deadlines mentioned in this email." \
    --date-from 2024-12-01 \
    --max-emails 50
```

**Summarize emails from a specific sender:**

```bash
$ ringtwice ask "Summarize this email in 2-3 sentences." \
    --sender "boss@company.com" \
    --date-from 2024-11-01
```

**Categorize emails by topic:**

```bash
$ ringtwice ask "Categorize this email. Return exactly one of: URGENT, MEETING, REPORT, FYI, SPAM" \
    --search-query "is:unread" \
    --max-emails 100 \
    --batch
```

**Process entire threads:**

```bash
$ ringtwice ask "Summarize the key decisions made in this email thread." \
    --search-query "subject:Q4 planning" \
    --thread
```

**Use a different mailbox:**

```bash
$ ringtwice ask "Is this email spam? Answer YES or NO." \
    --boxes work \
    --search-query "is:inbox"
```

### Inspect configuration

Print the resolved config path and parsed contents (with environment variables applied):

```bash
$ ringtwice config
# or with an explicit file:
$ ringtwice config --config-file ./config.example.toml
```

### Output format

Each JSONL file contains records like:

```json
{
  "email": {
    "uid": "abc123",
    "subject": "Q4 Planning Meeting Notes",
    "sender": "alice@company.com",
    "date": "2024-12-01T14:30:00"
  },
  "response": {
    "content": "Action items:\n- Review budget by Friday\n- Schedule follow-up with finance team",
    "model": "llama-3.1-70b",
    "usage_prompt_tokens": 1250,
    "usage_completion_tokens": 45
  },
  "timestamp": "2024-12-06T10:15:30"
}
```

---

## Python API

Use ringtwice as a library in your own Python code:

```python
from pathlib import Path
from ringtwice.config import Config
from ringtwice.mailbox import SearchCriteria, create_backend
from ringtwice.processor import EmailProcessor
from ringtwice.llm import LLMClient
from datetime import datetime

# Load configuration
config = Config.load(Path("~/.config/ringtwice/config.toml").expanduser())

# Create email backend
backend = create_backend(config.mailbox["gmail"])

# Define search criteria
criteria = SearchCriteria(
    query="meeting notes",
    date_from=datetime(2024, 12, 1),
    sender="team@company.com",
)

# Fetch and process emails
processor = EmailProcessor()
llm = LLMClient(config.llm)

try:
    for email in backend.search(criteria, folders=["INBOX"]):
        # Clean the email
        clean_text = processor.process(email)

        # Send to LLM
        for response in llm.process_batch(
            prompt="Summarize this email in one sentence.",
            contents=[clean_text],
        ):
            print(f"Subject: {email.subject}")
            print(f"Summary: {response.content}")
            print()
finally:
    backend.close()
```

### Key classes

**`Config`** - Load and validate configuration:
```python
from ringtwice.config import Config
config = Config.load(Path("/path/to/config.toml"))
# Access: config.llm.endpoint, config.llm.model, config.mailbox["gmail"].type
```

**`Email`** - Unified email representation:
```python
from ringtwice.mailbox import Email
# Fields: uid, subject, sender, recipients, date, text, html, thread_id
```

**`SearchCriteria`** - Email search parameters:
```python
from ringtwice.mailbox import SearchCriteria
criteria = SearchCriteria(
    query="search text",
    date_from=datetime(2024, 1, 1),
    date_to=datetime(2024, 12, 31),
    sender="user@example.com",
    subject="keyword",
)
```

**`EmailProcessor`** - Clean email content:
```python
from ringtwice.processor import EmailProcessor
processor = EmailProcessor(languages=["en", "de"])
clean_text = processor.process(email)
thread_text = processor.process_thread([email1, email2, email3])
```

**`LLMClient`** - Send to LLM:
```python
from ringtwice.llm import LLMClient
client = LLMClient(config.llm)
response = client.complete(prompt="System prompt", content="User content")
# response.content, response.model, response.usage_prompt_tokens
```

**`OutputWriter`** - Save results:
```python
from ringtwice.output import OutputWriter
writer = OutputWriter(Path("./output"))
filepath = writer.write(email, response)
filepath = writer.write_batch(emails, response)
```

---

## Development

### Setup

```bash
$ git clone https://github.com/yourname/ringtwice
$ cd ringtwice
$ uv sync --all-extras
```

### Run tests

```bash
$ uv run pytest -xvs
```

### Lint and format

```bash
$ uvx ruff check --fix . && uvx ruff format .
```

### Type check

```bash
$ uv run mypy src/
```

### Project structure

```
src/ringtwice/
├── cli.py          # Fire CLI entry point
├── config.py       # TOML config loading with ${VAR} interpolation
├── mailbox.py      # Gmail and IMAP backends
├── processor.py    # Email cleaning (HTML, quotes, signatures)
├── llm.py          # OpenAI-compatible client with retry
└── output.py       # JSONL file writer

tests/
├── test_cli.py
├── test_config.py
├── test_mailbox.py
├── test_processor.py
├── test_llm.py
└── test_output.py
```

### Adding a new email backend

1. Create a class inheriting from `MailboxBackend` in `mailbox.py`
2. Implement `search()`, `get_thread()`, and `close()` methods
3. Add the type to `MailboxConfig` and `create_backend()` factory
4. Write tests

### Configuration file format

```toml
[llm]
endpoint = "${LLM_API_ENDPOINT}"  # Environment variable interpolation
api_key = "${LLM_API_KEY}"
model = "llama-3.1-70b"
max_context = 8192  # Token limit for context window

[mailbox.personal]          # Name used with --boxes flag
type = "gmail"              # "gmail" or "imap"
credentials_file = "~/.config/ringtwice/gmail_credentials.json"

[mailbox.work]
type = "imap"
host = "imap.company.com"
port = 993
username = "${WORK_EMAIL}"
password = "${WORK_PASSWORD}"
```

---

## License

MIT
