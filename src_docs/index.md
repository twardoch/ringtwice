# ringtwice

> The postman always rings twice.

Pipe your inbox through an LLM. **ringtwice** grabs emails from Gmail or IMAP, strips away the HTML and signature clutter, feeds the clean text to any OpenAI-compatible LLM, and dumps the parsed insights to disk.

## Quick Start

```bash
# Install system-wide
uv pip install --system -e .

# Or inside a virtual environment
uv venv && uv sync
uv run ringtwice --help
```

```bash
# Example: Summarize recent emails
ringtwice ask "Extract all action items and deadlines" --max-emails 5
```

## How It Works

1. **Fetch**: Connects to Gmail (via API) or any IMAP server.
2. **Scrub**: Drops HTML formatting, quoted replies, and signatures to save context tokens.
3. **Parse**: Streams the clean text plus your prompt to the LLM (OpenAI, Ollama, vLLM, etc.).
4. **Dump**: Saves the extracted data as JSONL files.

## Documentation

| Guide | What's Inside |
|----------|-------------|
| [Installation](src_docs/installation.md) | Setup, requirements, and basic testing. |
| [Gmail Setup](src_docs/gmail.md) | How to wrangle Google's OAuth requirements. |
| [CLI Usage](src_docs/cli.md) | Flags, arguments, and practical examples. |
| [Configuration](src_docs/configuration.md) | How to map mailboxes and define LLM endpoints. |
| [Python API](src_docs/python-api.md) | Using ringtwice within your own Python scripts. |
| [Development](src_docs/development.md) | Running tests, extending the code, and contributing. |

## License

MIT
