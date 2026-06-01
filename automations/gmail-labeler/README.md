# gmail-labeler

**Audience:** AI agents and automated tooling. This document is the authoritative reference for understanding, operating, modifying, and debugging this automation.

## What It Does

Hourly cron automation that processes a user's unread Gmail messages through a four-stage pipeline:

1. **Fetch** — pulls unread messages from Gmail API (up to `processing_limit`)
2. **Deduplicate** — computes MD5 hash of `subject + sender + body`; skips emails already in the log
3. **OCR** — converts email HTML → PDF → page images → Tesseract OCR text (fast-path: emails with ≥100 plain-text chars skip OCR entirely)
4. **Classify** — runs a rule engine against the OCR text; calls Hermes LLM for `interest` rules and for no-match recommendation
5. **Act** — applies matched labels, removes `INBOX` and `UNREAD` system labels, optionally moves to Trash
6. **Log** — writes a structured JSON entry to `data/processed_log.json` for every email processed

Emails that match **no rules** are left unread and in the inbox. Their log entry includes `no_match_reasons` (per-rule explanation) and `label_recommendations` (LLM suggestions).

---

## Directory Layout

```
automations/gmail-labeler/
├── AUTOMATION.md            # Hermes manifest (schedule, deps, env vars)
├── README.md                # This file
├── scripts/
│   ├── main.py              # Entry point — orchestrates the full pipeline
│   ├── gmail_client.py      # Gmail API wrapper (fetch, label, mark-read, trash)
│   ├── ocr_pipeline.py      # HTML → PDF → images → Tesseract OCR
│   ├── classifier.py        # Rule engine + Hermes LLM bridge
│   ├── log_store.py         # JSON log CRUD with retention pruning
│   └── setup_auth.py        # One-time OAuth 2.0 flow helper
└── data/
    ├── config.example.json  # Config template (committed)
    ├── config.json          # Live config (gitignored — you must create this)
    └── processed_log.json   # Processing history (gitignored — auto-created)
```

---

## Prerequisites

### System Dependencies

```bash
brew install poppler tesseract   # macOS
# apt install poppler-utils tesseract-ocr  # Debian/Ubuntu
```

### Python Environment

Venv lives at `~/.hermes-automations/.venv`. All script shebangs point there directly.

```bash
cd ~/.hermes-automations
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib \
            weasyprint pdf2image pytesseract
```

### Environment Variable

```bash
# In ~/.hermes/.env or the shell environment:
AUTOMATIONS_GMAIL_JSON_KEY=/path/to/oauth_client_secrets.json
```

This must point to a **Google OAuth 2.0 Client Secrets JSON** file (not a service account key). Download it from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client ID → Download JSON.

Required Gmail API scopes: `gmail.modify` (read, label, trash).

---

## First-Run Setup

### 1. OAuth Token

The token is written to `~/.hermes/google_token.json` and reused across runs.

```bash
cd automations/gmail-labeler

# Step 1: get the auth URL
python3 scripts/setup_auth.py --auth-url
# → prints a URL — open it in a browser and approve access

# Step 2: exchange the code
python3 scripts/setup_auth.py --auth-code "4/0AX4XfWi..."
# → writes ~/.hermes/google_token.json
```

If the token expires, delete `~/.hermes/google_token.json` and repeat.

### 2. Create Config

```bash
cp data/config.example.json data/config.json
# Edit data/config.json — see Configuration section below
```

### 3. Create Gmail Labels

All labels referenced in `config.json` **must already exist in Gmail** before the first run. The script warns and skips any label it cannot resolve — it will not create labels automatically.

Create labels in the Gmail UI or via:
```bash
# Not automated — use Gmail Settings → Labels → Create new label
```

### 4. Dry Run

```bash
python3 scripts/main.py --dry-run --limit 5 --verbose
```

Verify the log at `data/processed_log.json`. Dry-run entries are keyed with a `DR-` prefix and do **not** modify Gmail.

---

## CLI Reference

```
python3 scripts/main.py [OPTIONS]

Options:
  --dry-run        Classify and log without applying labels, marking read, or trashing
  --limit N        Override processing_limit from config (default: config value or 50)
  --verbose        Print per-rule classification trace to stdout
```

---

## Utility Scripts

### report_unlabeled_emails.py

Analyzes the processed log and reports on emails that did not match any label rules. Useful for identifying gaps in your configuration and deciding what new rules to add.

**Usage:**

```bash
# Show summary + first 20 unlabeled emails (default)
python3 scripts/report_unlabeled_emails.py

# Show all unlabeled emails
python3 scripts/report_unlabeled_emails.py --all

# Show first N unlabeled emails
python3 scripts/report_unlabeled_emails.py --limit 50

# Save report to file
python3 scripts/report_unlabeled_emails.py --all --output unlabeled_report.txt

# Use custom log path
python3 scripts/report_unlabeled_emails.py --log /path/to/custom/log.json
```

**Output Format:**

Lists unlabeled emails sorted by most recent first, showing:
- Subject line
- Sender email
- Email ID
- Timestamp

**Workflow Tip:**

Run this script after each config update to see how many emails are now being filtered:

```bash
python3 scripts/main.py --limit 100    # Reprocess batch of emails
python3 scripts/report_unlabeled_emails.py --limit 30  # Review what's still missing
```

---

## Configuration

`data/config.json` — full schema:

```jsonc
{
  "label_rules": {
    "<Gmail Label Name>": {
      "keywords":  ["..."],   // Positive match: any keyword found in OCR text
      "xkeywords": ["..."],   // Disqualifier: if any match, label is NOT applied (checked last)
      "domains":   ["..."],   // Positive match: sender domain equals or is subdomain of entry
      "interest":  ["..."],   // Semantic match: Hermes LLM judges relevance to these topics
      "trash":     false      // Optional. If true, email is moved to Trash after labeling
    }
  },
  "processing_limit": 50,       // Max emails per run (overridable via --limit)
  "retention_period_days": 30   // Log entries older than this are pruned each run
}
```

### Rule Evaluation Order (per label)

1. **Domain match** — sender domain checked against `domains` list (subdomain-aware)
2. **Keyword match** — OCR text checked for any `keywords` entry (case-insensitive)
3. **Interest / LLM** — if `interest` is non-empty and no prior signal fired, Hermes CLI is called for semantic relevance
4. **xkeywords disqualification** — checked last; overrides any positive signal

A label is applied only if **at least one positive signal fired AND no xkeyword matched**.

### `trash` Flag Behavior

- `trash: false` (or omitted) — labels applied, `INBOX`+`UNREAD` removed, email archived
- `trash: true` — labels applied first, then `POST /messages/{id}/trash` called; Gmail auto-purges after 30 days
- If multiple matched rules have conflicting `trash` values, **any** `true` wins

---

## Log Schema

`data/processed_log.json` — keyed by MD5 hash (or `DR-<md5>` for dry runs):

```jsonc
{
  "<md5>": {
    "email_id":       "Gmail message ID",
    "email_title":    "Subject line",
    "sender":         "Raw From header",
    "applied_labels": ["Label A", "Label B"],
    "justification": {
      "Label A": "domain match (newegg.com)",
      "Label B": "keyword match ['shipped']"
    },
    "trashed":   false,
    "timestamp": "2024-06-01T12:00:00Z",
    "md5":       "<md5>",
    "dry_run":   false,

    // Only present when applied_labels is empty:
    "no_match_reasons": {
      "Promotions": "no configured keywords found in content; sender domain 'nextdoor.com' not in configured domains [...]",
      "Receipts":   "disqualified by xkeywords ['tracking'] (would have matched via keyword match ['order'])"
    },
    "label_recommendations": [
      {"label": "Newsletters", "reason": "Weekly digest from a community platform — not promotional or transactional."}
    ]
  }
}
```

**Key facts for agents reading this log:**
- `applied_labels: []` + `no_match_reasons` present → email was left unread/in-inbox
- `trashed: true` → email is in Gmail Trash, will auto-delete in 30 days
- `dry_run: true` → no Gmail changes were made; key has `DR-` prefix
- `label_recommendations` entries may reference existing labels OR suggest net-new ones — useful for identifying gaps in `config.json`
- Log is pruned of entries older than `retention_period_days` at end of each run

---

## Module Responsibilities

| Module | Owns |
|---|---|
| `main.py` | Arg parsing, config loading, pipeline orchestration, MD5, `_write_log_entry` |
| `gmail_client.py` | `GmailClient` class: `fetch_unread()`, `apply_labels()`, `resolve_label_ids()`, `mark_as_read()`, `trash_message()` |
| `ocr_pipeline.py` | `email_to_text()` fast-path (plain text) + full path (weasyprint→pdf2image→pytesseract); `_check_system_deps()` |
| `classifier.py` | `classify_email()` (returns `Dict[label→justification]`), `explain_no_match()`, `recommend_labels()`, `_check_interest_llm()`, `_find_hermes_bin()` |
| `log_store.py` | `LogStore`: `is_duplicate()`, `write_entry()`, `prune_expired()` |
| `setup_auth.py` | One-shot OAuth flow; reads `AUTOMATIONS_GMAIL_JSON_KEY`, writes `~/.hermes/google_token.json` |

---

## Cron Job

- **Hermes cron ID:** `c5fe886f4bf0`
- **Schedule:** `0 * * * *` (hourly)
- **Delegator stub:** `~/.hermes/scripts/gmail_labeler.py`
- **Deliver:** origin (back to the Hermes session that created it)

To pause/resume/inspect:
```bash
hermes cron list
hermes cron pause c5fe886f4bf0
hermes cron resume c5fe886f4bf0
```

---

## Common Failure Modes

| Symptom | Likely Cause | Fix |
|---|---|---|
| `FileNotFoundError: config.json` | `data/config.json` missing | `cp data/config.example.json data/config.json` |
| `WARN: Label 'X' not found in Gmail` | Label exists in config but not in Gmail | Create the label in Gmail UI |
| `Token expired / invalid_grant` | OAuth token stale | Delete `~/.hermes/google_token.json`, re-run `setup_auth.py` |
| OCR returns empty string | `poppler` or `tesseract` not installed / not on PATH | `brew install poppler tesseract`; confirm with `which pdftoppm tesseract` |
| `LLM interest check timed out` | Hermes CLI slow or unavailable | Non-fatal — label skipped; check `hermes` binary on PATH |
| All emails skipped as duplicates | `processed_log.json` has stale entries with same MD5 | Delete or prune `data/processed_log.json`; reduce `retention_period_days` |
| `AUTOMATIONS_GMAIL_JSON_KEY` not set | Env var missing from `~/.hermes/.env` | Add `AUTOMATIONS_GMAIL_JSON_KEY=/path/to/secrets.json` |

---

## Extending This Automation

### Adding a New Rule

Edit `data/config.json` — no code changes needed. Ensure the label exists in Gmail first.

### Adding a New Rule Field

1. Add the field to `data/config.example.json`
2. Read it in `classifier.py` → `classify_email()` and/or `explain_no_match()`
3. Update this README

### Changing the LLM Prompt

Edit `_check_interest_llm()` or `recommend_labels()` in `classifier.py`. Both expect the Hermes CLI to return a raw JSON block — keep that contract intact or update the `re.search` parser accordingly.

### Changing Log Fields

1. Update `_write_log_entry()` in `main.py`
2. Update the log schema section in this README
3. If adding a required field, backfill or handle `KeyError` in any consumer reading old entries
