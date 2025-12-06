# Gmail Setup Guide

This guide walks you through setting up Gmail access for ringtwice. It takes about 10 minutes.

## Overview

ringtwice uses the Gmail API with OAuth 2.0. You'll create a "project" in Google Cloud Console, enable the Gmail API, and download a credentials file. On first run, ringtwice opens your browser to authorize access.

!!! info "Privacy & Security"
    Your credentials never leave your computer. `ringtwice` only requests read-only access to your email.

---

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)

2. Sign in with the Google account that has the Gmail you want to access

3. Click the project dropdown at the top (next to "Google Cloud"):
   - If you see "Select a project", click it
   - Click **New Project** (top right of the popup)

4. Fill in:
   - **Project name**: `ringtwice` (or anything you like)
   - **Organization**: Leave as "No organization" for personal accounts

5. Click **Create**

6. Wait a few seconds, then click **Select Project** in the notification, or select it from the project dropdown

---

## Step 2: Enable the Gmail API

1. Go directly to: [Enable Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)

   Or navigate manually: **Menu (☰)** → **APIs & Services** → **Library** → search "Gmail API"

2. Make sure your project is selected (check the dropdown at the top)

3. Click **Enable**

---

## Step 3: Configure OAuth (Branding)

This tells Google what your "app" is. Since you're the only user, this is just formality.

1. Go to: [Google Auth Platform](https://console.cloud.google.com/auth/overview)

   Or: Search "oauth" in the console search bar

2. If prompted to configure, click **Get Started**

3. Fill in the **Branding** information:
   - **App name**: `ringtwice`
   - **User support email**: Select your email from dropdown
   - **App logo**: Skip (leave empty)
   - **App domain**: Skip all fields (leave empty)
   - **Developer contact information**: Enter your email address

4. Click **Save and Continue** (or just **Save**)

You should now see the **OAuth Overview** page with "OAuth configuration created!" message.

---

## Step 4: Configure Audience (Scopes & Test Users)

1. In the left sidebar, click **Audience**

2. Under **User type**, select **External** (required for personal @gmail.com accounts)

3. Click **Save**

### Add Scopes

1. In the left sidebar, click **Data Access**

2. Click **Add or Remove Scopes**

3. In the filter/search box, type: `gmail.readonly`

4. Check the box next to:

   ```text
   https://www.googleapis.com/auth/gmail.readonly
   ```
   (Description: "View your email messages and settings")

5. Click **Update**

6. Click **Save**

### Add Test Users

Since your app is in "Testing" mode, only listed test users can authorize it.

1. In the left sidebar, click **Audience**

2. Scroll down to **Test users**

3. Click **Add Users**

4. Enter **your Gmail address** (the one you want ringtwice to access)

5. Click **Save**

---

## Step 5: Create OAuth Client

Now create the actual credentials file that ringtwice uses.

1. In the left sidebar, click **Clients**

2. Click **Create Client** (or **Create OAuth client**)

3. **Application type**: Select **Desktop app**

4. **Name**: `ringtwice` (or anything)

5. Click **Create**

6. A popup appears with your client ID. Click **Download JSON**

7. **Save this file** - you can only download it once!

---

## Step 6: Install the Credentials File

Move the downloaded JSON file to your ringtwice config directory.

### Find your config directory

```bash
uv run python -c "from platformdirs import user_config_dir; print(user_config_dir('ringtwice'))"
```

This returns:

- **macOS**: `~/Library/Application Support/ringtwice`
- **Linux**: `~/.config/ringtwice`
- **Windows**: `%APPDATA%\ringtwice`

### Move and rename the file

```bash
# macOS
mv ~/Downloads/client_secret_*.json ~/Library/Application\ Support/ringtwice/gmail_credentials.json

# Linux
mv ~/Downloads/client_secret_*.json ~/.config/ringtwice/gmail_credentials.json

# Windows (PowerShell)
Move-Item ~\Downloads\client_secret_*.json $env:APPDATA\ringtwice\gmail_credentials.json
```

---

## Step 7: Configure ringtwice

Edit your `config.toml` (in the same directory as the credentials file):

```toml
[llm]
endpoint = "${LLM_API_ENDPOINT}"
api_key = "${LLM_API_KEY}"
model = "your-model-name"
max_context = 8192

[mailbox.gmail]
type = "gmail"
credentials_file = "gmail_credentials.json"  # Just the filename - same directory as config
```

---

## Step 8: First Run

```bash
uv run ringtwice ask "Summarize this email" --max-emails 1
```

**What happens:**

1. Your default browser opens to Google's authorization page
2. Select your Google account
3. You'll see a warning: "Google hasn't verified this app"
   - Click **Continue** (it's your own app)
4. Grant permission to "View your email messages and settings"
5. Browser shows "The authentication flow has completed"
6. Return to terminal - ringtwice is now running

A token file (`gmail_token.json`) is saved in your config directory. Future runs won't need the browser.

---

## Troubleshooting

### "Access blocked: This app's request is invalid"

**Cause**: OAuth consent screen not configured properly.

**Fix**: Go back to Step 3 and ensure you've added the `gmail.readonly` scope.

### "Error 403: access_denied"

**Cause**: Your email isn't in the test users list.

**Fix**: Go to [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent) → **Test users** → Add your email.

### Token expires every 7 days

**Cause**: Apps in "Testing" mode have tokens that expire weekly.

**Two options:**

1. **Live with it**: Just re-authorize weekly when prompted. ringtwice will open your browser automatically.
   > **Note:** Just run the command again if it fails with an auth error.

2. **Publish the app**: Go to OAuth consent screen → **Publishing status** → **Publish App**.
   - For personal use with just the `gmail.readonly` scope, Google typically doesn't require verification.
   - Tokens will then last until you revoke access.

### "This app is blocked"

**Cause**: Google sometimes blocks apps that haven't been verified.

**Fix**: Since this is your own app for personal use:
1. Go to OAuth consent screen
2. Click **Publish App**
3. Confirm the prompt

### Can't find the downloaded JSON file

**Cause**: The client secret can only be downloaded once, right after creation.

**Fix**: Delete the OAuth client and create a new one (Step 4).

---

## Security Notes

- **Credentials file** (`gmail_credentials.json`): Identifies your app. Not secret, but don't share publicly.
- **Token file** (`gmail_token.json`): Contains access to your Gmail. Keep private. Delete to revoke access.
- **Scopes**: ringtwice only requests `gmail.readonly` - it cannot send, delete, or modify emails.
- **Local only**: All processing happens on your machine. Emails are sent to your configured LLM endpoint.

---

## Revoking Access

To remove ringtwice's access to your Gmail:

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Scroll to "Third-party apps with account access"
3. Click **ringtwice**
4. Click **Remove Access**

Or simply delete the `gmail_token.json` file from your config directory.
