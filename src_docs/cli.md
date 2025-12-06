# CLI Usage

## Basic syntax

```bash
ringtwice ask <PROMPT> [OPTIONS]
```

The `PROMPT` is the instruction sent to the LLM along with each email's content.

## Options

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

## Examples

### Extract action items from recent emails

```bash
ringtwice ask "List all action items, tasks, and deadlines mentioned in this email." \
    --date-from 2024-12-01 \
    --max-emails 50
```

### Summarize emails from a specific sender

```bash
ringtwice ask "Summarize this email in 2-3 sentences." \
    --sender "boss@company.com" \
    --date-from 2024-11-01
```

### Categorize emails by topic

```bash
ringtwice ask "Categorize this email. Return exactly one of: URGENT, MEETING, REPORT, FYI, SPAM" \
    --search-query "is:unread" \
    --max-emails 100 \
    --batch
```

### Process entire threads

```bash
ringtwice ask "Summarize the key decisions made in this email thread." \
    --search-query "subject:Q4 planning" \
    --thread
```

### Use a different mailbox

```bash
ringtwice ask "Is this email spam? Answer YES or NO." \
    --boxes work \
    --search-query "is:inbox"
```

## Inspect configuration

Print the resolved config path and parsed contents (with environment variables applied):

```bash
ringtwice config
# or with an explicit file:
ringtwice config --config-file ./config.example.toml
```

## Output format

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
