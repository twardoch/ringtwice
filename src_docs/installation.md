# Installation

## Requirements

- Python 3.13+
- `uv` package manager (recommended) or `pip`

## From source (recommended for development)

```bash
git clone https://github.com/twardoch/ringtwice
cd ringtwice
uv pip install --system -e .
```

## With uv (isolated)

```bash
git clone https://github.com/twardoch/ringtwice
cd ringtwice
uv sync
uv run ringtwice --help
```

## Quick Setup

### 1. Set up email access

For Gmail, follow the [Gmail Setup Guide](gmail.md).

For IMAP, you'll need your server hostname, port, username, and password.

### 2. Create config file

Create `config.toml` in your config directory:

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

First run with Gmail opens your browser for authorization. The token is cached for future runs.
