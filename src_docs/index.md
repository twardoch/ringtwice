# ringtwice

A CLI tool that processes emails with LLMs. Fetch emails from Gmail or IMAP, clean them up, send them to any OpenAI-compatible LLM, and save the results.

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

## Quick Start

```bash
# Install
uv pip install --system -e .
# Or with virtual environment
uv venv && uv sync

# Run
ringtwice ask "Extract all action items and deadlines" --max-emails 5
```

Results are saved to `./output/YYMMDD-HHMMSS/` as JSONL files.

## Documentation

- [Installation](installation.md) - Setup and requirements
- [Gmail Setup](gmail.md) - Step-by-step Gmail API configuration
- [CLI Usage](cli.md) - Command-line options and examples
- [Configuration](configuration.md) - Config file format and options
- [Python API](python-api.md) - Using ringtwice as a library
- [Development](development.md) - Contributing and extending

## Why this design?

**Why Gmail API instead of IMAP for Gmail?**
Gmail's IMAP implementation is quirky and slow. The native API provides proper threading, faster search, and OAuth2 (no app passwords needed).

**Why OpenAI-compatible endpoints?**
Most LLM providers now support the OpenAI API format. One client works everywhere: OpenAI, Anthropic (via proxy), Cerebras, Together, Groq, Fireworks, Ollama, vLLM, etc.

**Why JSONL output?**
JSONL is append-friendly (no array closing brackets), streamable, and easy to process with `jq`, Python, or any JSON parser. One file per email means you can incrementally process results.

**Why clean emails before sending to LLM?**
Email threads accumulate cruft: HTML formatting, signatures repeated 10 times, entire conversation histories quoted. Cleaning reduces token usage by 50-80% and improves LLM response quality.

## License

MIT
