---
name: gmail-labeler
description: "Hourly automation that fetches unread Gmail messages, classifies them via OCR + rule engine + LLM interest matching, applies labels, and marks emails as read."
version: 1.0.0
author: tkottke
license: UNLICENSED

schedule: "0 * * * *"

platforms: [macos, linux]

metadata:
  hermes:
    tags: [gmail, email, labels, ocr, automation]
    scripts:
      - name: main
        file: main.py
        no_agent: true
        deliver: origin
    dependencies:
      - google-api-python-client
      - google-auth-httplib2
      - google-auth-oauthlib
      - weasyprint
      - pdf2image
      - pytesseract
    env:
      - AUTOMATIONS_GMAIL_JSON_KEY
---

# Gmail Labeler

Hourly automation that processes unread Gmail messages through a configurable rule engine:

1. Fetches unread emails via the Gmail API
2. Computes an MD5 hash per email for deduplication
3. Converts email HTML → PDF → images → OCR text via weasyprint + pdf2image + pytesseract
4. Classifies each email using a configured rule set (keywords, domains, xkeywords, interest)
5. For `interest` rules, calls the Hermes LLM for semantic relevance analysis
6. Applies matching labels and marks the email as read
7. Logs all actions to `data/processed_log.json`

## Setup

### 1. System Dependencies

```bash
brew install poppler tesseract
```

### 2. Python Dependencies

```bash
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib weasyprint pdf2image pytesseract
```

### 3. Environment Variable

Add to `~/.hermes/.env`:

```
AUTOMATIONS_GMAIL_JSON_KEY=/path/to/oauth_client_secrets.json
```

### 4. First-Run OAuth

```bash
python3 scripts/setup_auth.py --auth-url
# Approve in browser, then:
python3 scripts/setup_auth.py --auth-code "4/0AX4XfWi..."
```

Token is saved to `~/.hermes/google_token.json` (shared with other Gmail automations).

### 5. Configure Labels

Copy `data/config.example.json` → `data/config.json` and configure `label_rules`.

**Important:** All labels referenced in `config.json` must already exist in Gmail. Create them in the Gmail UI before running. The script warns and skips missing labels.

### 6. Test

```bash
python3 scripts/main.py --dry-run --limit 5
```

## Files

| File | Purpose |
|---|---|
| `scripts/main.py` | Entry point — orchestrates the pipeline |
| `scripts/gmail_client.py` | Gmail API wrapper (fetch, label, mark read) |
| `scripts/ocr_pipeline.py` | Email → PDF → images → OCR text |
| `scripts/classifier.py` | Rule engine + Hermes LLM interest bridge |
| `scripts/log_store.py` | JSON log read/write with deduplication |
| `scripts/setup_auth.py` | First-run OAuth helper |
| `data/config.json` | Live config (gitignored) |
| `data/config.example.json` | Config template (committed) |
| `data/processed_log.json` | Processing history (gitignored) |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AUTOMATIONS_GMAIL_JSON_KEY` | Yes | Path to OAuth 2.0 Client Secrets JSON |

## CLI Usage

```bash
# Dry-run (no changes applied)
python3 scripts/main.py --dry-run

# Dry-run with custom limit
python3 scripts/main.py --dry-run --limit 5

# Full run
python3 scripts/main.py

# Full run with limit override
python3 scripts/main.py --limit 100

# Verbose output
python3 scripts/main.py --dry-run --verbose
```
