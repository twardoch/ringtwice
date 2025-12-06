"""Producer-consumer pipeline for parallel email fetching and LLM processing.

This module implements a concurrent architecture where:
1. Fetcher (producer): Runs in a thread, fetches emails and fills a buffer
2. Processor (consumer): Async workers that process emails with LLM and write output
3. Buffer: Bounded asyncio.Queue with backpressure to prevent memory overflow
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ringtwice.llm import LLMClient, LLMResponse
from ringtwice.mailbox import DEFAULT_FOLDERS, Email, MailboxBackend, SearchCriteria, create_backend
from ringtwice.output import OutputWriter
from ringtwice.processor import EmailProcessor

if TYPE_CHECKING:
    from ringtwice.config import MailboxConfig

logger = logging.getLogger(__name__)


class WorkItemType(Enum):
    """Type of work item in the queue."""

    EMAIL = "email"
    BATCH = "batch"
    POISON = "poison"  # Signals workers to stop


@dataclass
class WorkItem:
    """A unit of work for the LLM processor."""

    type: WorkItemType
    emails: list[Email] = field(default_factory=list)
    content: str = ""
    mailbox_name: str = ""

    @classmethod
    def poison(cls) -> WorkItem:
        """Create a poison pill to signal worker shutdown."""
        return cls(type=WorkItemType.POISON)

    @classmethod
    def from_email(cls, email: Email, content: str, mailbox_name: str = "") -> WorkItem:
        """Create a work item from a single email."""
        return cls(
            type=WorkItemType.EMAIL,
            emails=[email],
            content=content,
            mailbox_name=mailbox_name,
        )

    @classmethod
    def from_batch(cls, emails: list[Email], content: str, mailbox_name: str = "") -> WorkItem:
        """Create a work item from a batch of emails."""
        return cls(
            type=WorkItemType.BATCH,
            emails=emails,
            content=content,
            mailbox_name=mailbox_name,
        )


@dataclass
class PipelineStats:
    """Statistics for the pipeline execution."""

    emails_fetched: int = 0
    emails_processed: int = 0
    emails_failed: int = 0
    llm_calls: int = 0
    llm_retries: int = 0
    tokens_used: int = 0
    files_written: int = 0
    fetch_complete: bool = False
    process_complete: bool = False
    start_time: datetime = field(default_factory=datetime.now)

    def elapsed_seconds(self) -> float:
        """Return elapsed time since start."""
        return (datetime.now() - self.start_time).total_seconds()


@dataclass
class PipelineCallbacks:
    """Callbacks for pipeline progress reporting."""

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


class EmailBuffer:
    """Bounded async queue with backpressure for email work items.

    The buffer size is calculated based on the LLM context length to ensure
    we don't accumulate too much data in memory while still maintaining
    good throughput.
    """

    def __init__(
        self,
        max_context_tokens: int,
        buffer_multiplier: int = 20,
        avg_email_tokens: int = 500,
    ) -> None:
        """Initialize the buffer.

        Args:
            max_context_tokens: LLM maximum context window size
            buffer_multiplier: How many context windows worth of data to buffer
            avg_email_tokens: Estimated average tokens per email
        """
        # Calculate buffer size: buffer_multiplier * context / avg_email_size
        self._max_size = max(
            10,  # Minimum buffer size
            (max_context_tokens * buffer_multiplier) // avg_email_tokens,
        )
        self._queue: asyncio.Queue[WorkItem] = asyncio.Queue(maxsize=self._max_size)
        self._closed = False
        self._items_added = 0
        self._items_processed = 0

    @property
    def max_size(self) -> int:
        """Maximum number of items the buffer can hold."""
        return self._max_size

    @property
    def current_size(self) -> int:
        """Current number of items in the buffer."""
        return self._queue.qsize()

    @property
    def items_added(self) -> int:
        """Total items added to the buffer."""
        return self._items_added

    @property
    def items_processed(self) -> int:
        """Total items removed from the buffer."""
        return self._items_processed

    async def put(self, item: WorkItem, timeout: float = 30.0) -> bool:
        """Add an item to the buffer with timeout for backpressure.

        Returns True if successful, False if buffer is closed or timeout.
        """
        if self._closed:
            return False
        try:
            await asyncio.wait_for(self._queue.put(item), timeout=timeout)
            self._items_added += 1
            return True
        except TimeoutError:
            logger.warning("Buffer put timeout - consumer may be too slow")
            return False

    async def get(self, timeout: float = 5.0) -> WorkItem | None:
        """Get an item from the buffer with timeout.

        Returns None if timeout or buffer is empty and closed.
        """
        try:
            item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            self._items_processed += 1
            return item
        except TimeoutError:
            return None

    def task_done(self) -> None:
        """Mark a task as done."""
        self._queue.task_done()

    def close(self) -> None:
        """Close the buffer - no more items will be accepted."""
        self._closed = True

    @property
    def is_closed(self) -> bool:
        """Check if buffer is closed."""
        return self._closed

    async def drain(self) -> None:
        """Wait for all items to be processed."""
        await self._queue.join()


class EmailFetcher:
    """Producer that fetches emails and fills the buffer.

    Runs in a separate thread since mailbox backends are blocking.
    Uses backpressure from the buffer to avoid overwhelming memory.
    """

    def __init__(
        self,
        mailbox_configs: list[tuple[str, MailboxConfig]],
        criteria: SearchCriteria,
        folders: list[str] | None = None,
        buffer: EmailBuffer,
        processor: EmailProcessor,
        thread: bool = False,
        max_emails: int | None = None,
        batch: bool = False,
        batch_size: int | None = None,
        callbacks: PipelineCallbacks | None = None,
    ) -> None:
        self._mailbox_configs = mailbox_configs
        self._criteria = criteria
        self._folders = folders or list(DEFAULT_FOLDERS)
        self._buffer = buffer
        self._processor = processor
        self._thread = thread
        self._max_emails = max_emails
        self._batch = batch
        self._batch_size = batch_size or 10
        self._callbacks = callbacks or PipelineCallbacks()
        self._stop_event = Event()
        self._stats = PipelineStats()
        self._loop: asyncio.AbstractEventLoop | None = None

    def stop(self) -> None:
        """Signal the fetcher to stop."""
        self._stop_event.set()

    @property
    def stats(self) -> PipelineStats:
        """Get current statistics."""
        return self._stats

    def _put_to_buffer(self, item: WorkItem) -> bool:
        """Thread-safe way to put item to buffer."""
        if self._loop is None:
            return False
        future = asyncio.run_coroutine_threadsafe(self._buffer.put(item), self._loop)
        try:
            return future.result(timeout=60.0)
        except Exception as e:
            logger.error(f"Failed to put item to buffer: {e}")
            return False

    def run(self, loop: asyncio.AbstractEventLoop) -> None:
        """Run the fetcher (called from a thread).

        Args:
            loop: The asyncio event loop to use for buffer operations
        """
        self._loop = loop
        self._callbacks.on_fetch_start()

        batch_emails: list[Email] = []
        batch_contents: list[str] = []

        try:
            for mailbox_name, mailbox_config in self._mailbox_configs:
                if self._stop_event.is_set():
                    break

                backend: MailboxBackend | None = None
                try:
                    backend = create_backend(mailbox_config)

                    for email in backend.search(self._criteria, self._folders):
                        if self._stop_event.is_set():
                            break

                        # Get thread if requested
                        if self._thread:
                            try:
                                thread_emails = backend.get_thread(email)
                            except Exception as e:
                                logger.warning(f"Failed to get thread for {email.uid}: {e}")
                                thread_emails = [email]
                        else:
                            thread_emails = [email]

                        for thread_email in thread_emails:
                            if self._max_emails and self._stats.emails_fetched >= self._max_emails:
                                break

                            # Process email content
                            if self._thread:
                                content = self._processor.process_thread([thread_email])
                            else:
                                content = self._processor.process(thread_email)

                            if self._batch:
                                batch_emails.append(thread_email)
                                batch_contents.append(content)

                                if len(batch_emails) >= self._batch_size:
                                    combined = "\n---\n".join(batch_contents)
                                    item = WorkItem.from_batch(
                                        list(batch_emails), combined, mailbox_name
                                    )
                                    if not self._put_to_buffer(item):
                                        logger.error("Failed to add batch to buffer")
                                        break
                                    batch_emails.clear()
                                    batch_contents.clear()
                            else:
                                item = WorkItem.from_email(thread_email, content, mailbox_name)
                                if not self._put_to_buffer(item):
                                    logger.error("Failed to add email to buffer")
                                    break

                            self._stats.emails_fetched += 1
                            self._callbacks.on_fetch_progress(
                                self._stats.emails_fetched, mailbox_name
                            )

                        if self._max_emails and self._stats.emails_fetched >= self._max_emails:
                            break

                except Exception as e:
                    logger.error(f"Error fetching from {mailbox_name}: {e}")
                    self._callbacks.on_fetch_error(e, mailbox_name)
                finally:
                    if backend:
                        try:
                            backend.close()
                        except Exception:
                            pass

                if self._max_emails and self._stats.emails_fetched >= self._max_emails:
                    break

            # Flush remaining batch
            if batch_emails:
                combined = "\n---\n".join(batch_contents)
                item = WorkItem.from_batch(list(batch_emails), combined, "")
                self._put_to_buffer(item)

        finally:
            self._stats.fetch_complete = True
            self._buffer.close()
            self._callbacks.on_fetch_complete(self._stats.emails_fetched)


class LLMWorker:
    """Consumer that processes work items with the LLM.

    Runs as an async task, pulls from buffer, calls LLM, writes output.
    Includes retry logic and error handling.
    """

    def __init__(
        self,
        worker_id: int,
        buffer: EmailBuffer,
        llm: LLMClient,
        writer: OutputWriter,
        parse_query: str,
        callbacks: PipelineCallbacks | None = None,
        stats: PipelineStats | None = None,
    ) -> None:
        self._worker_id = worker_id
        self._buffer = buffer
        self._llm = llm
        self._writer = writer
        self._parse_query = parse_query
        self._callbacks = callbacks or PipelineCallbacks()
        self._stats = stats or PipelineStats()
        self._running = True

    def stop(self) -> None:
        """Signal the worker to stop."""
        self._running = False

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1, max=30, jitter=5),
        before_sleep=lambda retry_state: logger.warning(
            f"LLM call retry attempt {retry_state.attempt_number}"
        ),
    )
    async def _call_llm(self, content: str) -> LLMResponse:
        """Call LLM with retry logic."""
        # Run in executor since openai client is sync
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._llm.complete, self._parse_query, content)

    async def _process_item(self, item: WorkItem) -> bool:
        """Process a single work item. Returns True on success."""
        try:
            # Split content if too large
            chunks = self._llm.split_for_context(item.content)

            for chunk in chunks:
                response = await self._call_llm(chunk)
                self._stats.llm_calls += 1
                self._stats.tokens_used += (
                    response.usage_prompt_tokens + response.usage_completion_tokens
                )

                # Write output (may return None if response was empty/irrelevant)
                loop = asyncio.get_event_loop()
                if item.type == WorkItemType.BATCH:
                    path = await loop.run_in_executor(
                        None, self._writer.write_batch, item.emails, response
                    )
                else:
                    path = await loop.run_in_executor(
                        None, self._writer.write, item.emails[0], response
                    )

                if path:
                    self._stats.files_written += 1
                    self._callbacks.on_write(path, len(item.emails))

            self._stats.emails_processed += len(item.emails)
            return True

        except RetryError as e:
            logger.error(f"LLM call failed after retries: {e}")
            self._stats.emails_failed += len(item.emails)
            self._callbacks.on_process_error(e, item.emails)
            return False
        except Exception as e:
            logger.error(f"Error processing item: {e}")
            self._stats.emails_failed += len(item.emails)
            self._callbacks.on_process_error(e, item.emails)
            return False

    async def run(self) -> None:
        """Run the worker, processing items from the buffer."""
        logger.debug(f"Worker {self._worker_id} starting")

        while self._running:
            item = await self._buffer.get(timeout=2.0)

            if item is None:
                # Timeout - check if we should continue
                if self._buffer.is_closed and self._buffer.current_size == 0:
                    break
                continue

            if item.type == WorkItemType.POISON:
                self._buffer.task_done()
                break

            await self._process_item(item)
            self._buffer.task_done()

            self._callbacks.on_process_progress(
                self._stats.emails_processed, self._buffer.current_size
            )

        logger.debug(f"Worker {self._worker_id} finished")


class Pipeline:
    """Orchestrates the producer-consumer pipeline.

    Coordinates:
    - Email fetcher (producer) running in a thread
    - LLM workers (consumers) running as async tasks
    - Buffer with backpressure
    - Progress reporting and statistics
    """

    def __init__(
        self,
        mailbox_configs: list[tuple[str, MailboxConfig]],
        criteria: SearchCriteria,
        folders: list[str] | None,
        llm: LLMClient,
        writer: OutputWriter,
        processor: EmailProcessor,
        parse_query: str,
        thread: bool = False,
        max_emails: int | None = None,
        batch: bool = False,
        batch_size: int | None = None,
        buffer_multiplier: int = 20,
        num_workers: int = 1,
        callbacks: PipelineCallbacks | None = None,
    ) -> None:
        self._mailbox_configs = mailbox_configs
        self._criteria = criteria
        self._folders = folders or list(DEFAULT_FOLDERS)
        self._llm = llm
        self._writer = writer
        self._processor = processor
        self._parse_query = parse_query
        self._thread = thread
        self._max_emails = max_emails
        self._batch = batch
        self._batch_size = batch_size
        self._buffer_multiplier = buffer_multiplier
        self._num_workers = num_workers
        self._callbacks = callbacks or PipelineCallbacks()
        self._stats = PipelineStats()

        # Will be initialized in run()
        self._buffer: EmailBuffer | None = None
        self._fetcher: EmailFetcher | None = None
        self._workers: list[LLMWorker] = []

    @property
    def stats(self) -> PipelineStats:
        """Get current pipeline statistics."""
        return self._stats

    async def run(self) -> PipelineStats:
        """Run the complete pipeline.

        Returns statistics about the run.
        """
        # Initialize buffer based on LLM context size
        self._buffer = EmailBuffer(
            max_context_tokens=self._llm._config.max_context,
            buffer_multiplier=self._buffer_multiplier,
        )

        logger.info(f"Pipeline buffer size: {self._buffer.max_size} items")

        # Create fetcher
        self._fetcher = EmailFetcher(
            mailbox_configs=self._mailbox_configs,
            criteria=self._criteria,
            folders=self._folders,
            buffer=self._buffer,
            processor=self._processor,
            thread=self._thread,
            max_emails=self._max_emails,
            batch=self._batch,
            batch_size=self._batch_size,
            callbacks=self._callbacks,
        )

        # Create workers (share stats object)
        self._workers = [
            LLMWorker(
                worker_id=i,
                buffer=self._buffer,
                llm=self._llm,
                writer=self._writer,
                parse_query=self._parse_query,
                callbacks=self._callbacks,
                stats=self._stats,
            )
            for i in range(self._num_workers)
        ]

        # Get the current event loop for the fetcher thread
        loop = asyncio.get_event_loop()

        # Start fetcher in thread pool
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fetcher")
        fetch_future = loop.run_in_executor(executor, self._fetcher.run, loop)

        # Start worker tasks
        self._callbacks.on_process_start()
        worker_tasks = [asyncio.create_task(worker.run()) for worker in self._workers]

        # Start stats reporter
        stats_task = asyncio.create_task(self._report_stats())

        try:
            # Wait for fetcher to complete
            await fetch_future

            # Update stats from fetcher
            if self._fetcher:
                self._stats.emails_fetched = self._fetcher.stats.emails_fetched
                self._stats.fetch_complete = True

            # Wait for all workers to complete
            await asyncio.gather(*worker_tasks)

            self._stats.process_complete = True
            self._callbacks.on_process_complete(self._stats.emails_processed)

        except asyncio.CancelledError:
            logger.info("Pipeline cancelled")
            self._fetcher.stop()
            for worker in self._workers:
                worker.stop()
        finally:
            stats_task.cancel()
            try:
                await stats_task
            except asyncio.CancelledError:
                pass
            executor.shutdown(wait=False)

        return self._stats

    async def _report_stats(self) -> None:
        """Periodically report statistics."""
        while True:
            await asyncio.sleep(1.0)
            self._callbacks.on_stats_update(self._stats)

    def stop(self) -> None:
        """Stop the pipeline gracefully."""
        if self._fetcher:
            self._fetcher.stop()
        for worker in self._workers:
            worker.stop()


async def run_pipeline(
    mailbox_configs: list[tuple[str, MailboxConfig]],
    criteria: SearchCriteria,
    folders: list[str] | None = None,
    llm: LLMClient,
    writer: OutputWriter,
    processor: EmailProcessor,
    parse_query: str,
    thread: bool = False,
    max_emails: int | None = None,
    batch: bool = False,
    batch_size: int | None = None,
    buffer_multiplier: int = 20,
    num_workers: int = 1,
    callbacks: PipelineCallbacks | None = None,
) -> PipelineStats:
    """Convenience function to run the pipeline.

    Args:
        mailbox_configs: List of (name, config) tuples for mailboxes
        criteria: Search criteria for emails
        llm: LLM client instance
        writer: Output writer instance
        processor: Email processor instance
        parse_query: LLM prompt to use
        thread: Whether to fetch full threads
        max_emails: Maximum number of emails to process
        batch: Whether to batch emails
        batch_size: Size of batches when batching
        buffer_multiplier: How many LLM contexts worth of data to buffer
        num_workers: Number of concurrent LLM workers
        callbacks: Progress callbacks

    Returns:
        Statistics about the pipeline run
    """
    pipeline = Pipeline(
        mailbox_configs=mailbox_configs,
        criteria=criteria,
        folders=folders,
        llm=llm,
        writer=writer,
        processor=processor,
        parse_query=parse_query,
        thread=thread,
        max_emails=max_emails,
        batch=batch,
        batch_size=batch_size,
        buffer_multiplier=buffer_multiplier,
        num_workers=num_workers,
        callbacks=callbacks,
    )
    return await pipeline.run()
