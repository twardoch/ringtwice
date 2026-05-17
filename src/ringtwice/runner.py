"""Core orchestration for email processing with LLMs. Connects mailboxes, formats prompts, and runs inference."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from ringtwice.config import Config, get_default_config_path
from ringtwice.llm import LLMClient
from ringtwice.mailbox import DEFAULT_FOLDERS, Email, SearchCriteria, create_backend
from ringtwice.output import OutputWriter, get_default_output_dir
from ringtwice.pipeline import PipelineCallbacks, PipelineStats, run_pipeline
from ringtwice.processor import EmailProcessor

if TYPE_CHECKING:
    from collections.abc import Callable

    from ringtwice.config import MailboxConfig


@dataclass
class AskParams:
    """CLI parameters converted into pipeline inputs."""

    parse_query: str
    search_query: str | None = None
    folders: list[str] | None = None
    thread: bool = False
    max_emails: int | None = None
    boxes: list[str] | None = None
    batch: bool = False
    batch_size: int | None = None
    output_dir: Path | None = None
    config_file: Path | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    sender: list[str] | None = None
    recipient: list[str] | None = None
    subject: str | None = None


@dataclass
class FetchResult:
    """Raw emails fetched from a mailbox and their totals."""

    emails: list[Email]
    counts_by_mailbox: dict[str, int]


def split_csv(value: str | None) -> list[str] | None:
    """Split comma-separated strings into trimmed lists. Drop empties."""
    if value is None:
        return None
    parts = [v.strip() for v in value.split(",")]
    return [p for p in parts if p] or None


def parse_date(value: str | None) -> datetime | None:
    """Parse ISO date strings into datetime objects. Return None if empty."""
    if value is None:
        return None
    return datetime.fromisoformat(value)


def resolve_mailboxes(
    config: Config, requested: list[str] | None
) -> list[tuple[str, MailboxConfig]]:
    """Match requested mailboxes against config. Fails hard if missing."""
    names = requested or [next(iter(config.mailbox))]
    missing = [name for name in names if name not in config.mailbox]
    if missing:
        raise ValueError(f"Unknown mailbox requested: {', '.join(missing)}. Check your config TOML for valid mailbox names.")
    return [(name, config.mailbox[name]) for name in names]


def resolve_folders(requested: list[str] | None) -> list[str]:
    """Return requested folders or default to INBOX."""
    return requested or list(DEFAULT_FOLDERS)


def build_search_criteria(params: AskParams) -> SearchCriteria:
    """Map CLI parameters to a SearchCriteria object."""
    return SearchCriteria(
        query=params.search_query,
        date_from=params.date_from,
        date_to=params.date_to,
        sender=params.sender,
        recipient=params.recipient,
        subject=params.subject,
    )


def fetch_emails(
    mailbox_configs: list[tuple[str, MailboxConfig]],
    criteria: SearchCriteria,
    folders: list[str] | None = None,
    thread: bool = False,
    max_emails: int | None = None,
    on_progress: Callable[[], None] | None = None,
) -> FetchResult:
    """Pull emails sequentially from configured mailboxes matching search criteria."""
    all_emails: list[Email] = []
    counts: dict[str, int] = defaultdict(int)

    resolved_folders = resolve_folders(folders)

    for mailbox_name, mailbox_config in mailbox_configs:
        backend = create_backend(mailbox_config)
        try:
            for email in backend.search(criteria, resolved_folders):
                if thread:
                    thread_emails = backend.get_thread(email)
                    all_emails.extend(thread_emails)
                    counts[mailbox_name] += len(thread_emails)
                else:
                    all_emails.append(email)
                    counts[mailbox_name] += 1

                if on_progress:
                    on_progress()

                if max_emails and len(all_emails) >= max_emails:
                    break
        finally:
            backend.close()

        if max_emails and len(all_emails) >= max_emails:
            all_emails = all_emails[:max_emails]
            break

    return FetchResult(emails=all_emails, counts_by_mailbox=dict(counts))


def process_emails_individual(
    emails: list[Email],
    processor: EmailProcessor,
    llm: LLMClient,
    writer: OutputWriter,
    parse_query: str,
    thread: bool,
    on_progress: Callable[[], None] | None = None,
    on_write: Callable[[Path], None] | None = None,
) -> None:
    """Send emails to the LLM one by one. Slower but more precise."""
    for email in emails:
        content = processor.process_thread([email]) if thread else processor.process(email)
        for response in llm.process_batch(parse_query, [content]):
            path = writer.write(email, response)
            if path and on_write:
                on_write(path)
        if on_progress:
            on_progress()


def process_emails_batch(
    emails: list[Email],
    processor: EmailProcessor,
    llm: LLMClient,
    writer: OutputWriter,
    parse_query: str,
    batch_size: int | None,
    on_progress: Callable[[], None] | None = None,
    on_write: Callable[[Path], None] | None = None,
) -> None:
    """Group emails to minimize LLM round-trips. Flushes when batch_size is met."""
    batch_contents: list[str] = []
    batch_emails: list[Email] = []

    def flush_batch() -> None:
        if not batch_contents:
            return
        combined = "\n---\n".join(batch_contents)
        for response in llm.process_batch(parse_query, [combined]):
            path = writer.write_batch(batch_emails, response)
            if path and on_write:
                on_write(path)

    for email in emails:
        content = processor.process(email)
        batch_contents.append(content)
        batch_emails.append(email)
        if on_progress:
            on_progress()

        if batch_size and len(batch_contents) >= batch_size:
            flush_batch()
            batch_contents = []
            batch_emails = []

    flush_batch()


def run_ask(params: AskParams, callbacks: RunCallbacks | None = None) -> Path:
    """Execute the core extraction loop synchronously.
    
    Pulls emails, builds prompts, fires LLM queries, and writes JSONL outputs.
    Returns the path where results are saved.
    """
    cb = callbacks or RunCallbacks()
    load_dotenv()

    config_path = params.config_file or get_default_config_path()
    config = Config.load(config_path)

    out_dir = params.output_dir or get_default_output_dir()
    writer = OutputWriter(out_dir)
    llm = LLMClient(config.llm)
    processor = EmailProcessor()

    criteria = build_search_criteria(params)
    mailbox_configs = resolve_mailboxes(config, params.boxes)
    folders = resolve_folders(params.folders)

    # Fetch emails
    cb.on_fetch_start()
    result = fetch_emails(
        mailbox_configs,
        criteria,
        folders,
        params.thread,
        params.max_emails,
        on_progress=cb.on_fetch_progress,
    )
    cb.on_fetch_end(result.counts_by_mailbox, [name for name, _ in mailbox_configs])

    if not result.emails:
        cb.on_no_emails()
        return out_dir

    # Process emails
    cb.on_process_start(len(result.emails))
    if params.batch:
        process_emails_batch(
            result.emails,
            processor,
            llm,
            writer,
            params.parse_query,
            params.batch_size,
            on_progress=cb.on_process_progress,
            on_write=cb.on_write,
        )
    else:
        process_emails_individual(
            result.emails,
            processor,
            llm,
            writer,
            params.parse_query,
            params.thread,
            on_progress=cb.on_process_progress,
            on_write=cb.on_write,
        )
    cb.on_process_end(out_dir)

    return out_dir


@dataclass
class RunCallbacks:
    """Hooks to update UI and terminal progress bars during synchronous runs."""

    on_fetch_start: Callable[[], None] = lambda: None
    on_fetch_progress: Callable[[], None] = lambda: None
    on_fetch_end: Callable[[dict[str, int], list[str]], None] = lambda counts, names: None
    on_no_emails: Callable[[], None] = lambda: None
    on_process_start: Callable[[int], None] = lambda total: None
    on_process_progress: Callable[[], None] = lambda: None
    on_write: Callable[[Path], None] = lambda path: None
    on_process_end: Callable[[Path], None] = lambda out_dir: None


@dataclass
class AsyncRunCallbacks:
    """Hooks to update UI and terminal progress bars during async concurrent runs."""

    on_fetch_start: Callable[[], None] = lambda: None
    on_fetch_progress: Callable[[int, str], None] = lambda count, mailbox: None
    on_fetch_complete: Callable[[int], None] = lambda total: None
    on_fetch_error: Callable[[Exception, str], None] = lambda e, mailbox: None

    on_process_start: Callable[[], None] = lambda: None
    on_process_progress: Callable[[int, int], None] = lambda processed, queued: None
    on_process_complete: Callable[[int], None] = lambda total: None
    on_process_error: Callable[[Exception, list[Email]], None] = lambda e, emails: None

    on_write: Callable[[Path, int], None] = lambda path, email_count: None
    on_stats_update: Callable[[PipelineStats], None] = lambda stats: None
    on_no_emails: Callable[[], None] = lambda: None
    on_complete: Callable[[Path, PipelineStats], None] = lambda out_dir, stats: None


async def run_ask_async(
    params: AskParams, callbacks: AsyncRunCallbacks | None = None
) -> tuple[Path, PipelineStats]:
    """Execute the extraction loop asynchronously.
    
    Streams emails into a producer-consumer pipeline so LLM processing 
    starts before fetching finishes. Maximizes throughput.

    Returns:
        Tuple containing the output directory path and performance statistics.
    """
    cb = callbacks or AsyncRunCallbacks()
    load_dotenv()

    config_path = params.config_file or get_default_config_path()
    config = Config.load(config_path)

    out_dir = params.output_dir or get_default_output_dir()
    writer = OutputWriter(out_dir)
    llm = LLMClient(config.llm)
    processor = EmailProcessor()

    criteria = build_search_criteria(params)
    mailbox_configs = resolve_mailboxes(config, params.boxes)
    folders = resolve_folders(params.folders)

    # Convert callbacks to pipeline format
    pipeline_callbacks = PipelineCallbacks(
        on_fetch_start=cb.on_fetch_start,
        on_fetch_progress=cb.on_fetch_progress,
        on_fetch_complete=cb.on_fetch_complete,
        on_fetch_error=cb.on_fetch_error,
        on_process_start=cb.on_process_start,
        on_process_progress=cb.on_process_progress,
        on_process_complete=cb.on_process_complete,
        on_process_error=cb.on_process_error,
        on_write=cb.on_write,
        on_stats_update=cb.on_stats_update,
    )

    # Run the pipeline
    stats = await run_pipeline(
        mailbox_configs=mailbox_configs,
        criteria=criteria,
        llm=llm,
        writer=writer,
        processor=processor,
        parse_query=params.parse_query,
        folders=folders,
        thread=params.thread,
        max_emails=params.max_emails,
        batch=params.batch,
        batch_size=params.batch_size,
        buffer_multiplier=20,  # Buffer 20x LLM context worth of emails
        num_workers=1,  # Single worker for LLM (rate limiting)
        callbacks=pipeline_callbacks,
    )

    if stats.emails_fetched == 0:
        cb.on_no_emails()

    cb.on_complete(out_dir, stats)

    return out_dir, stats


def run_ask_with_pipeline(
    params: AskParams, callbacks: AsyncRunCallbacks | None = None
) -> tuple[Path, PipelineStats]:
    """Wrap run_ask_async for synchronous callers.
    
    Use this to get concurrent throughput benefits without adopting asyncio.
    """
    return asyncio.run(run_ask_async(params, callbacks))
