"""CLI entry point using Fire."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from dataclasses import dataclass

import fire
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn
from rich.table import Table

from ringtwice.config import Config, get_default_config_path
from ringtwice.mailbox import SearchCriteria, create_backend
from ringtwice.runner import AskParams, RunCallbacks, parse_date, run_ask, split_csv

console = Console(width=200, soft_wrap=True)


@dataclass
class ProgressState:
    """Holds progress bars and task IDs for callbacks."""

    fetch_progress: Progress | None = None
    fetch_task: TaskID | None = None
    process_progress: Progress | None = None
    process_task: TaskID | None = None


def _make_callbacks() -> tuple[RunCallbacks, ProgressState]:
    """Create callbacks with Rich progress bars."""
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
    ) -> None:
        """
        Process emails with an LLM.

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
        callbacks, _ = _make_callbacks()
        run_ask(params, callbacks)

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
