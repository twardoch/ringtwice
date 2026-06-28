# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`ringtwice` is a Python 3.13 Fire CLI tool that:
- Connects to GMail (preferred) or IMAP mailboxes
- Searches/filters emails by query, date range, sender, recipient, subject
- Minifies emails (strips HTML, signatures, old quotations)
- Sends email content to an LLM (OpenAI-compatible API) with a user-defined prompt
- Saves LLM responses as JSONL files

## Build & Test Commands

```bash
# Setup
uv venv --python 3.13
uv sync

# Run tests
pytest -xvs

# Lint and format
uvx ruff check --fix . && uvx ruff format .

# Full test with coverage
pytest --cov=src --cov-report=term-missing --cov-fail-under=80

# Run the CLI
uv run ringtwice --help
```

You can also run `./build.sh` 

## Project Layout

```
ringtwice/
├── src/ringtwice/
│   ├── cli.py          # Fire CLI entry point
│   ├── config.py       # TOML config with env var interpolation
│   ├── mailbox.py      # Gmail/IMAP email backends
│   ├── pipeline.py     # Async producer-consumer pipeline
│   ├── processor.py    # Email minification (HTML, quotes, signatures)
│   ├── llm.py          # OpenAI-compatible LLM client
│   ├── output.py       # JSONL output writer
│   └── runner.py       # Orchestration: fetch → process → write
├── src_docs/           # MkDocs Material source pages
│   ├── gmail.md        # OAuth2 setup walkthrough
│   ├── imap.md         # IMAP quickstart (new)
│   ├── configuration.md # Config reference + JSONL schema
│   └── ...
├── tests/              # pytest tests (108 tests, 81%+ coverage)
├── pyproject.toml      # uv/pip config
└── config.example.toml # Example configuration
```

## Key Dependencies

- `fire` - CLI framework
- `imap-tools` - IMAP email access (zero deps)
- `google-api-python-client` + `google-auth-oauthlib` - Gmail API with OAuth
- `html2text` - HTML to plain text conversion
- `mail-parser-reply` - Email quote/signature removal
- `openai` - LLM client (supports custom base_url)
- `semantic-text-splitter` + `tiktoken` - Token-aware text chunking
- `pydantic` - Config validation
- `tenacity` - Retry logic

## Configuration

Config file uses TOML format with environment variables for secrets:
- API endpoint (e.g., `https://api.cerebras.ai/v1`)
- API key (from env var)
- Model name and max context length
- Mailbox configurations (IMAP credentials or GMail auth)

## CLI Interface

Key flags:
- `--parse-query` - LLM prompt to apply to emails
- `--search-query` - Email search text
- `--thread` - Retrieve full threads vs individual emails
- `--max-emails` - Limit number of emails
- `--boxes` - Which mailboxes to search
- `--batch` / `--batch-size` - Combine emails before sending to LLM
- `--output-dir` - Where to save JSONL results
- `--dry-run` - Fetch + LLM process but skip writing JSONL files to disk

Output naming: `YYMMDD-HHMMSS-SENDEREMAIL-THREADSUBJECT.jsonl` (slugified)

---

## Development Guidelines

### Toolchain

- **Package Manager**: `uv` exclusively
- **Python**: 3.13 via `uv`
- **Formatting/Linting**: `ruff`
- **Type Checking**: `mypy` or `pyright`
- **Testing**: `pytest`

### Code Standards

- Type hints on every function
- `pathlib` for paths
- Pydantic for config/data structures
- `openai` library for LLM access (uses httpx internally)

### Philosophy

- **Minimalism**: Build only what's required now
- **Package-first**: Use existing libraries before writing custom code
- **Test-first**: Write failing test, then minimal code to pass
- **Delete first**: Can we remove code instead of adding?

### Documentation Files

- `README.md` - Purpose and usage
- `PLAN.md` - Architecture and future goals
- `TODO.md` - Task list with status markers
- `WORK.md` - Current work log
- `CHANGELOG.md` - Release notes
