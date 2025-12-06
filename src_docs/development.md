# Development

## Setup

```bash
git clone https://github.com/twardoch/ringtwice
cd ringtwice
uv sync --all-extras
```

## Run tests

```bash
uv run pytest -xvs
```

## Lint and format

```bash
uvx ruff check --fix . && uvx ruff format .
```

## Type check

```bash
uv run mypy src/
```

## Project structure

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

## Adding a new email backend

1. Create a class inheriting from `MailboxBackend` in `mailbox.py`
2. Implement `search()`, `get_thread()`, and `close()` methods
3. Add the type to `MailboxConfig` and `create_backend()` factory
4. Write tests

## Key dependencies

- `fire` - CLI framework
- `imap-tools` - IMAP email access (zero deps)
- `google-api-python-client` + `google-auth-oauthlib` - Gmail API with OAuth
- `html2text` - HTML to plain text conversion
- `mail-parser-reply` - Email quote/signature removal
- `openai` - LLM client (supports custom base_url)
- `semantic-text-splitter` + `tiktoken` - Token-aware text chunking
- `pydantic` - Config validation
- `tenacity` - Retry logic

## Philosophy

- **Minimalism**: Build only what's required now
- **Package-first**: Use existing libraries before writing custom code
- **Test-first**: Write failing test, then minimal code to pass
- **Delete first**: Can we remove code instead of adding?
