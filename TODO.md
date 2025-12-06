- [ ] https://twardoch.github.io/ringtwice/gmail/ returns 404 while other pages work 

- [ ] THIS: 

```
[08:32:42] $ ./build.sh
[INFO] Syncing dependencies...
Resolved 74 packages in 3ms
Audited 73 packages in 1ms
[OK] Dependencies synced
[INFO] Fixing linting issues...
PLR0915 Too many statements (105 > 50)
   --> src/ringtwice/cli.py:159:5
    |
159 | def _make_async_callbacks() -> tuple[AsyncRunCallbacks, AsyncProgressState]:
    |     ^^^^^^^^^^^^^^^^^^^^^
160 |     """Create callbacks for async pipeline with concurrent progress display."""
161 |     state = AsyncProgressState()
    |

PLR0912 Too many branches (24 > 12)
   --> src/ringtwice/pipeline.py:277:9
    |
275 |             return False
276 |
277 |     def run(self, loop: asyncio.AbstractEventLoop) -> None:
    |         ^^^
278 |         """Run the fetcher (called from a thread).
    |

PLR0915 Too many statements (69 > 50)
   --> src/ringtwice/pipeline.py:277:9
    |
275 |             return False
276 |
277 |     def run(self, loop: asyncio.AbstractEventLoop) -> None:
    |         ^^^
278 |         """Run the fetcher (called from a thread).
    |

SIM105 Use `contextlib.suppress(Exception)` instead of `try`-`except`-`pass`
   --> src/ringtwice/pipeline.py:358:25
    |
356 |                   finally:
357 |                       if backend:
358 | /                         try:
359 | |                             backend.close()
360 | |                         except Exception:
361 | |                             pass
    | |________________________________^
362 |
363 |                   if self._max_emails and self._stats.emails_fetched >= self._max_emails:
    |
help: Replace `try`-`except`-`pass` with `with contextlib.suppress(Exception): ...`

SIM105 Use `contextlib.suppress(asyncio.CancelledError)` instead of `try`-`except`-`pass`
   --> src/ringtwice/pipeline.py:623:13
    |
621 |           finally:
622 |               stats_task.cancel()
623 | /             try:
624 | |                 await stats_task
625 | |             except asyncio.CancelledError:
626 | |                 pass
    | |____________________^
627 |               executor.shutdown(wait=False)
    |
help: Replace `try`-`except`-`pass` with `with contextlib.suppress(asyncio.CancelledError): ...`

Found 6 errors (1 fixed, 5 remaining).
No fixes available (2 hidden fixes can be enabled with the `--unsafe-fixes` option).
~/Developer/github2/twardoch/pub/ringtwice (main)
[08:34:03] $
```

