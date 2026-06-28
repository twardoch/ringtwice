# Changelog

All notable changes to ringtwice are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added

- `--dry-run` flag on `ringtwice ask`: fetch and process emails, call the LLM,
  print results to the terminal, but skip writing any JSONL files to disk.
  Useful for validating prompts and configs without accumulating output files.
- `src_docs/imap.md` — IMAP Quickstart covering Gmail App Passwords, Outlook,
  Fastmail, Dovecot, common provider settings, and a troubleshooting FAQ.
- Expanded `src_docs/configuration.md` with:
  - Full `[llm]` key reference table including `max_context` sizing guidance
  - Full `[mailbox.<name>]` key reference for both `gmail` and `imap` backends
  - JSONL output schema documentation with field-level descriptions for single
    and batch records
- Inline comments in `processor.py` explaining why the two-pass HTML→plain-text
  pipeline (html2text then mail-parser-reply) reduces LLM token cost by 30–80 %
- Detailed docstrings on `LLMClient.complete()` and `LLMClient.process_batch()`
  with explicit type annotations on intermediate variables
- `OutputWriter.__init__` now accepts `dry_run: bool = False`

### Changed

- `mail-parser-reply` dependency upper-bounded to `<2` to guard against
  breaking API changes in a future major release
- `mkdocs.yml` nav updated to include the new IMAP Quickstart page
- Pre-existing test regex patterns updated to match current error messages in
  `config.py` and `runner.py` (error text had diverged from test assertions)

### Fixed

- `test_raises_on_unknown_type` regex now matches the actual error message
  (`"Unsupported mailbox type"` instead of `"Unknown mailbox type"`)
- `test_raises_on_missing_var` regex now matches `"Missing environment variable"`
- `test_load_raises_on_missing_file` regex now matches `"Missing config file"`
- `test_resolve_missing_mailbox_raises` regex now matches
  `"Unknown mailbox requested"`

---

## [1.1.6] — 2026-05-17

- Initial public release on PyPI
- Gmail API (OAuth2) and IMAP backends
- OpenAI-compatible LLM endpoint support
- Async producer-consumer pipeline with Rich progress UI
- TOML config with environment variable interpolation
- JSONL output with empty-response filtering
