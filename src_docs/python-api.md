# Python API

Use ringtwice as a library in your own Python code.

## Basic example

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

## Key classes

### Config

Load and validate configuration:

```python
from ringtwice.config import Config
config = Config.load(Path("/path/to/config.toml"))
# Access: config.llm.endpoint, config.llm.model, config.mailbox["gmail"].type
```

### Email

Unified email representation:

```python
from ringtwice.mailbox import Email
# Fields: uid, subject, sender, recipients, date, text, html, thread_id
```

### SearchCriteria

Email search parameters:

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

### EmailProcessor

Clean email content:

```python
from ringtwice.processor import EmailProcessor
processor = EmailProcessor(languages=["en", "de"])
clean_text = processor.process(email)
thread_text = processor.process_thread([email1, email2, email3])
```

### LLMClient

Send to LLM:

```python
from ringtwice.llm import LLMClient
client = LLMClient(config.llm)
response = client.complete(prompt="System prompt", content="User content")
# response.content, response.model, response.usage_prompt_tokens
```

### OutputWriter

Save results:

```python
from ringtwice.output import OutputWriter
writer = OutputWriter(Path("./output"))
filepath = writer.write(email, response)
filepath = writer.write_batch(emails, response)
```
