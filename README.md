# ringtwice

A CLI tool that processes emails with LLMs. Fetch emails from Gmail or IMAP, clean them up, send them to any OpenAI-compatible LLM, and save the results.

## Quick Start

```bash
# Install
uv pip install --system -e .

# Or with virtual environment
uv venv && uv sync
uv run ringtwice --help
```

```bash
# Run
ringtwice ask "Extract all action items and deadlines" --max-emails 5
```

## What it does

1. **Fetches emails** from Gmail (via API) or any IMAP server
2. **Cleans** email content: converts HTML to text, removes signatures and quoted replies
3. **Sends** to any OpenAI-compatible LLM with your prompt
4. **Saves** results as JSONL files

## Documentation

| Document | Description |
|----------|-------------|
| [Installation](src_docs/installation.md) | Setup, requirements, and quick start |
| [Gmail Setup](src_docs/gmail.md) | Step-by-step Gmail API configuration |
| [CLI Usage](src_docs/cli.md) | Command-line options and examples |
| [Configuration](src_docs/configuration.md) | Config file format and options |
| [Python API](src_docs/python-api.md) | Using ringtwice as a library |
| [Development](src_docs/development.md) | Contributing and extending |

## License

MIT
