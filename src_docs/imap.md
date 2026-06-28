# IMAP Quickstart

Connect ringtwice to any standard IMAP server — Gmail via App Password,
Outlook, Fastmail, your self-hosted Dovecot instance, etc.

---

## Prerequisites

- IMAP access enabled on your mail account (check your provider's settings)
- An app-specific password if your provider requires one (Gmail, iCloud, etc.)

---

## Step 1: Enable IMAP on Your Mail Account

### Gmail

Gmail requires an **App Password** when 2-Step Verification is active
(direct IMAP with your main password is blocked).

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Under **2-Step Verification** → scroll to **App passwords**
3. Select **Mail** and **Other (custom name)** → enter `ringtwice`
4. Copy the 16-character app password shown

### Outlook / Microsoft 365

1. Sign in at [outlook.live.com](https://outlook.live.com)
2. **Settings** → **Mail** → **Sync email** → toggle **IMAP** on

### Fastmail

IMAP is on by default. Generate an app-specific password under
**Settings → Privacy & Security → Third-party apps**.

### Self-hosted (Dovecot / Cyrus)

No extra steps; use your normal credentials unless the admin requires a
dedicated service account.

---

## Step 2: Add the Mailbox to Your Config

Open (or create) `~/.config/ringtwice/config.toml` (macOS:
`~/Library/Application Support/ringtwice/config.toml`):

```toml
[llm]
endpoint = "${LLM_API_ENDPOINT}"
api_key  = "${LLM_API_KEY}"
model    = "llama-3.1-70b"

[mailbox.work]
type     = "imap"
host     = "imap.company.com"
port     = 993                   # 993 = IMAPS (TLS); 143 = plain IMAP
username = "${WORK_EMAIL}"
password = "${WORK_APP_PASSWORD}"
```

Set your secrets in a `.env` file next to the config or export them as
shell variables:

```bash
export LLM_API_ENDPOINT="https://api.cerebras.ai/v1"
export LLM_API_KEY="cb-..."
export WORK_EMAIL="me@company.com"
export WORK_APP_PASSWORD="abcd efgh ijkl mnop"
```

!!! tip "Environment variable interpolation"
    Any `${VAR}` in your `config.toml` is replaced at load time.
    Lines starting with `#` are skipped so you can document your config safely.

---

## Step 3: Verify the Connection

```bash
ringtwice config
```

This prints the resolved config and attempts a connection to every
configured mailbox. A green **OK** means ringtwice can log in and search.

---

## Step 4: Your First Query

```bash
ringtwice ask "Extract all action items with deadlines" \
    --boxes work \
    --max-emails 10
```

| Flag | Effect |
|---|---|
| `--boxes work` | Use only the `work` mailbox defined in config |
| `--max-emails 10` | Stop after fetching 10 messages |
| `--date-from 2024-01-01` | Restrict to emails after this date |
| `--search-query "invoice"` | Full-text search inside the mailbox |
| `--folders "INBOX,Sent"` | Search specific IMAP folders |

Results are saved as JSONL files under `output/<timestamp>/`.

---

## Common Provider Settings

| Provider | Host | Port | Notes |
|---|---|---|---|
| Gmail | `imap.gmail.com` | 993 | Use App Password |
| Outlook.com | `outlook.office365.com` | 993 | Use App Password |
| Yahoo Mail | `imap.mail.yahoo.com` | 993 | Use App Password |
| Fastmail | `imap.fastmail.com` | 993 | Use App Password |
| iCloud | `imap.mail.me.com` | 993 | Use App-Specific Password |
| Dovecot (default) | your server | 993 | Normal password or cert auth |

---

## Troubleshooting

### `[AUTHENTICATIONFAILED] Invalid credentials`

- For Gmail: you must use an **App Password**, not your Google account password.
- Confirm the username matches exactly (some servers require the full email address).
- Check that `${ENV_VAR}` references are exported before running ringtwice.

### `Connection refused` or `timed out`

- Verify the host and port (993 for TLS, 143 for STARTTLS).
- Check firewall rules on your machine or corporate VPN.
- Try `openssl s_client -connect imap.host.com:993` to test raw connectivity.

### Folder names not found

IMAP folder names are server-specific. List available folders:

```bash
python - <<'EOF'
from imap_tools import MailBox
mb = MailBox("imap.host.com").login("user@host.com", "password")
for f in mb.folder.list():
    print(f.name)
mb.logout()
EOF
```

Then pass the correct names with `--folders`.

---

## Differences vs Gmail API

| Feature | IMAP | Gmail API |
|---|---|---|
| Setup | Username + password | OAuth 2.0 credentials file |
| Thread support | Limited (no native grouping) | Full thread API |
| Search syntax | IMAP RFC 3501 | Gmail search operators |
| Rate limits | Server-dependent | 250 quota units/second |
| Works offline | No | No |

For Gmail accounts, the [Gmail Setup](gmail.md) route gives richer thread
support and avoids app-password management.
