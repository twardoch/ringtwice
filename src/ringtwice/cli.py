"""CLI entry point using Fire."""

from __future__ import annotations

import contextlib
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

import fire
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from ringtwice.config import Config, get_default_config_path
from ringtwice.mailbox import Email, SearchCriteria, create_backend
from ringtwice.pipeline import PipelineStats
from ringtwice.runner import (
    AskParams,
    AsyncRunCallbacks,
    RunCallbacks,
    parse_date,
    run_ask,
    run_ask_with_pipeline,
    split_csv,
)

console = Console(width=200, soft_wrap=True)


@dataclass
class ProgressState:
    """Holds progress bars and task IDs for callbacks."""

    fetch_progress: Progress | None = None
    fetch_task: TaskID | None = None
    process_progress: Progress | None = None
    process_task: TaskID | None = None


def _make_callbacks() -> tuple[RunCallbacks, ProgressState]:
    """Create callbacks with Rich progress bars (legacy synchronous mode)."""
    progress_state = ProgressState()

    def on_fetch_start() -> None:
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        )
        progress.start()
        task = progress.add_task("Fetching emails", start=True)
        progress_state.fetch_progress = progress
        progress_state.fetch_task = task

    def on_fetch_progress() -> None:
        progress = progress_state.fetch_progress
        task = progress_state.fetch_task
        if progress is not None and task is not None:
            progress.advance(task)

    def on_fetch_end(counts: dict[str, int], names: list[str]) -> None:
        progress = progress_state.fetch_progress
        if progress:
            progress.stop()

        table = Table(title="Mailbox Summary", show_lines=False)
        table.add_column("Mailbox", style="cyan")
        table.add_column("Processed", justify="right")
        total = 0
        for name in names:
            count = counts.get(name, 0)
            table.add_row(name, str(count))
            total += count
        table.add_row("[bold]Total[/]", str(total))
        console.print(table)

    def on_no_emails() -> None:
        console.print("[yellow]No emails to process[/]")

    def on_process_start(total: int) -> None:
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold green]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        )
        progress.start()
        task = progress.add_task("Processing emails", total=total)
        progress_state.process_progress = progress
        progress_state.process_task = task

    def on_process_progress() -> None:
        progress = progress_state.process_progress
        task = progress_state.process_task
        if progress is not None and task is not None:
            progress.advance(task)

    def on_write(path: Path) -> None:
        console.print(f"[blue]Wrote[/]: {path}")

    def on_process_end(out_dir: Path) -> None:
        progress = progress_state.process_progress
        if progress:
            progress.stop()
        console.print(f"[bold green]Output saved to:[/] {out_dir}")

    callbacks = RunCallbacks(
        on_fetch_start=on_fetch_start,
        on_fetch_progress=on_fetch_progress,
        on_fetch_end=on_fetch_end,
        on_no_emails=on_no_emails,
        on_process_start=on_process_start,
        on_process_progress=on_process_progress,
        on_write=on_write,
        on_process_end=on_process_end,
    )
    return callbacks, progress_state


@dataclass
class AsyncProgressState:
    """Holds state for concurrent pipeline progress display."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    live: Live | None = None

    # Fetcher state
    fetch_progress: Progress | None = None
    fetch_task: TaskID | None = None
    emails_fetched: int = 0
    current_mailbox: str = ""
    fetch_complete: bool = False

    # Processor state
    process_progress: Progress | None = None
    process_task: TaskID | None = None
    emails_processed: int = 0
    emails_queued: int = 0

    # Stats
    llm_calls: int = 0
    tokens_used: int = 0
    files_written: int = 0
    errors: list[str] = field(default_factory=list)


def _make_async_callbacks() -> tuple[AsyncRunCallbacks, AsyncProgressState]:
    """Create callbacks for async pipeline with concurrent progress display."""
    state = AsyncProgressState()

    # Create progress bars for fetch and process
    fetch_progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Fetching:"),
        TextColumn("{task.description}"),
        TimeElapsedColumn(),
    )

    process_progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold green]Processing:"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TextColumn("({task.description})"),
        TimeElapsedColumn(),
    )

    state.fetch_progress = fetch_progress
    state.process_progress = process_progress

    def create_layout() -> Panel:
        """Create the layout for concurrent display."""
        # Build status lines
        fetch_status = (
            f"[cyan]Fetched: {state.emails_fetched} emails"
            + (f" from {state.current_mailbox}" if state.current_mailbox else "")
            + (" [green]DONE" if state.fetch_complete else "")
        )

        process_status = (
            f"[green]Processed: {state.emails_processed} emails | "
            f"Queued: {state.emails_queued} | "
            f"LLM calls: {state.llm_calls} | "
            f"Files: {state.files_written}"
        )

        if state.tokens_used > 0:
            process_status += f" | Tokens: {state.tokens_used:,}"

        error_lines = ""
        if state.errors:
            error_lines = "\n[red]Errors: " + "; ".join(state.errors[-3:])
            if len(state.errors) > 3:
                error_lines += f" (+{len(state.errors) - 3} more)"

        content = Group(
            fetch_progress,
            process_progress,
            TextColumn(fetch_status),
            TextColumn(process_status + error_lines),
        )

        return Panel(content, title="[bold]Ringtwice Pipeline", border_style="blue")

    def on_fetch_start() -> None:
        with state.lock:
            state.fetch_task = fetch_progress.add_task("Starting...", total=None, start=True)
            state.process_task = process_progress.add_task(
                "Waiting for emails...", total=0, completed=0
            )
            state.live = Live(create_layout(), console=console, refresh_per_second=4)
            state.live.start()

    def on_fetch_progress(count: int, mailbox: str) -> None:
        with state.lock:
            state.emails_fetched = count
            state.current_mailbox = mailbox
            if fetch_progress and state.fetch_task is not None:
                fetch_progress.update(
                    state.fetch_task, description=f"{count} emails from {mailbox}"
                )
            if state.live:
                state.live.update(create_layout())

    def on_fetch_complete(total: int) -> None:
        with state.lock:
            state.fetch_complete = True
            state.emails_fetched = total
            if fetch_progress and state.fetch_task is not None:
                fetch_progress.update(
                    state.fetch_task,
                    description=f"[green]Complete: {total} emails",
                    completed=total,
                    total=total,
                )
            if process_progress and state.process_task is not None:
                process_progress.update(state.process_task, total=total)
            if state.live:
                state.live.update(create_layout())

    def on_fetch_error(error: Exception, mailbox: str) -> None:
        with state.lock:
            state.errors.append(f"{mailbox}: {error}")
            if state.live:
                state.live.update(create_layout())

    def on_process_start() -> None:
        pass  # Already started in fetch_start

    def on_process_progress(processed: int, queued: int) -> None:
        with state.lock:
            state.emails_processed = processed
            state.emails_queued = queued
            if process_progress and state.process_task is not None:
                process_progress.update(
                    state.process_task,
                    completed=processed,
                    description=f"queued: {queued}",
                )
            if state.live:
                state.live.update(create_layout())

    def on_process_complete(total: int) -> None:
        with state.lock:
            state.emails_processed = total
            if process_progress and state.process_task is not None:
                process_progress.update(
                    state.process_task,
                    completed=total,
                    description="[green]Complete",
                )
            if state.live:
                state.live.update(create_layout())

    def on_process_error(error: Exception, emails: list[Email]) -> None:
        with state.lock:
            subjects = ", ".join(e.subject[:20] for e in emails[:2])
            state.errors.append(f"LLM error for '{subjects}...': {error}")
            if state.live:
                state.live.update(create_layout())

    def on_write(path: Path, email_count: int) -> None:
        with state.lock:
            state.files_written += 1
            if state.live:
                state.live.update(create_layout())

    def on_stats_update(stats: PipelineStats) -> None:
        with state.lock:
            state.llm_calls = stats.llm_calls
            state.tokens_used = stats.tokens_used
            state.emails_processed = stats.emails_processed
            if state.live:
                state.live.update(create_layout())

    def on_no_emails() -> None:
        with state.lock:
            if state.live:
                state.live.stop()
        console.print("[yellow]No emails to process[/]")

    def on_complete(out_dir: Path, stats: PipelineStats) -> None:
        with state.lock:
            if state.live:
                state.live.stop()

        # Print summary table
        table = Table(title="Pipeline Summary", show_lines=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Emails fetched", str(stats.emails_fetched))
        table.add_row("Emails processed", str(stats.emails_processed))
        if stats.emails_failed > 0:
            table.add_row("[red]Emails failed[/]", str(stats.emails_failed))
        table.add_row("LLM calls", str(stats.llm_calls))
        table.add_row("Tokens used", f"{stats.tokens_used:,}")
        table.add_row("Files written", str(stats.files_written))
        table.add_row("Duration", f"{stats.elapsed_seconds():.1f}s")

        console.print(table)
        console.print(f"[bold green]Output saved to:[/] {out_dir}")

    callbacks = AsyncRunCallbacks(
        on_fetch_start=on_fetch_start,
        on_fetch_progress=on_fetch_progress,
        on_fetch_complete=on_fetch_complete,
        on_fetch_error=on_fetch_error,
        on_process_start=on_process_start,
        on_process_progress=on_process_progress,
        on_process_complete=on_process_complete,
        on_process_error=on_process_error,
        on_write=on_write,
        on_stats_update=on_stats_update,
        on_no_emails=on_no_emails,
        on_complete=on_complete,
    )

    return callbacks, state


def _show_config(config_file: Path | None = None) -> None:
    """Display the resolved config path and parsed content."""
    from dotenv import load_dotenv

    load_dotenv()
    config_path = config_file or get_default_config_path()
    console.print(f"[bold]Config path:[/] {config_path}")

    try:
        config = Config.load(config_path)
    except Exception:
        console.print("[red]Failed to parse config. See error below.[/]")
        raise

    console.print("[bold]Parsed config:[/]")
    console.print(json.dumps(config.model_dump(mode="json"), indent=2, sort_keys=True))

    console.print("\n[bold]Mailbox connectivity:[/]")
    table = Table(box=None)
    table.add_column("Mailbox", style="cyan")
    table.add_column("Status")
    table.add_column("Detail", overflow="fold")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        console=console,
    ) as progress:
        for name, mailbox_config in config.mailbox.items():
            task = progress.add_task(f"Connecting to {name}", total=None)
            status = "[green]OK[/]"
            detail = ""
            backend = None
            try:
                backend = create_backend(mailbox_config)
                iterator = backend.search(SearchCriteria(), ["INBOX"])
                try:
                    next(iterator)
                    detail = "connected (fetched first email)"
                except StopIteration:
                    detail = "connected (no emails fetched)"
            except Exception as exc:
                status = "[red]ERROR[/]"
                detail = str(exc)
            finally:
                if backend is not None:
                    with contextlib.suppress(Exception):
                        backend.close()
                progress.stop_task(task)

            table.add_row(name, status, detail)

    console.print(table)


class RingtwiceCLI:
    """Ringtwice CLI - process emails with LLMs."""

    def ask(
        self,
        parse_query: str,
        search_query: str | None = None,
        thread: bool = False,
        max_emails: int | None = None,
        boxes: list[str] | None = None,
        batch: bool = False,
        batch_size: int | None = None,
        output_dir: str | None = None,
        config_file: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sender: str | None = None,
        recipient: str | None = None,
        subject: str | None = None,
        legacy: bool = False,
    ) -> None:
        """
        Process emails with an LLM.

        Uses a concurrent pipeline that fetches emails while processing with LLM,
        showing progress for both operations in real-time.

        Args:
            parse_query: LLM prompt to apply to emails (required)
            search_query: Email search text
            thread: Retrieve full threads vs individual emails
            max_emails: Limit number of emails to process
            boxes: Mailbox names to search (from config)
            batch: Combine emails before sending to LLM
            batch_size: Number of emails per batch (default: fit to context)
            output_dir: Directory for JSONL output files
            config_file: Path to config TOML file
            date_from: Filter emails after this date (YYYY-MM-DD)
            date_to: Filter emails before this date (YYYY-MM-DD)
            sender: Filter by sender (comma-separated for multiple)
            recipient: Filter by recipient (comma-separated for multiple)
            subject: Filter by subject substring
            legacy: Use legacy synchronous mode (fetch all, then process)
        """
        params = AskParams(
            parse_query=parse_query,
            search_query=search_query,
            thread=thread,
            max_emails=max_emails,
            boxes=boxes,
            batch=batch,
            batch_size=batch_size,
            output_dir=Path(output_dir) if output_dir else None,
            config_file=Path(config_file) if config_file else None,
            date_from=parse_date(date_from),
            date_to=parse_date(date_to),
            sender=split_csv(sender),
            recipient=split_csv(recipient),
            subject=subject,
        )

        if legacy:
            # Use legacy synchronous mode
            sync_callbacks, _ = _make_callbacks()
            run_ask(params, sync_callbacks)
        else:
            # Use new concurrent pipeline
            async_callbacks, _ = _make_async_callbacks()
            run_ask_with_pipeline(params, async_callbacks)

    def config(self, config_file: str | None = None) -> None:
        """
        Show the config path and parsed values.

        Args:
            config_file: Path to config TOML file (optional)
        """
        _show_config(Path(config_file) if config_file else None)


def ask(
    parse_query: str,
    search_query: str | None = None,
    thread: bool = False,
    max_emails: int | None = None,
    boxes: list[str] | None = None,
    batch: bool = False,
    batch_size: int | None = None,
    output_dir: str | None = None,
    config_file: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sender: str | None = None,
    recipient: str | None = None,
    subject: str | None = None,
) -> None:
    """Standalone function for backwards compatibility and direct imports."""
    cli = RingtwiceCLI()
    cli.ask(
        parse_query=parse_query,
        search_query=search_query,
        thread=thread,
        max_emails=max_emails,
        boxes=boxes,
        batch=batch,
        batch_size=batch_size,
        output_dir=output_dir,
        config_file=config_file,
        date_from=date_from,
        date_to=date_to,
        sender=sender,
        recipient=recipient,
        subject=subject,
    )


def show_config(config_file: str | None = None) -> None:
    """Standalone function for backwards compatibility."""
    _show_config(Path(config_file) if config_file else None)


def main() -> None:
    """Entry point for the CLI."""
    fire.Fire(RingtwiceCLI)


if __name__ == "__main__":
    main()
