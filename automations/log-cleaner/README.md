# log-cleaner

A Hermes automation that deletes expired cron job log files from
`~/.hermes/cron/output/`. Log files accumulate quickly for high-frequency cron
jobs (e.g. one every 15 minutes = ~96 files/day per job). This automation
keeps disk usage in check by removing `.md` log files older than a configurable
expiration period.

---

## How It Works

Hermes stores cron job output logs at:

```
~/.hermes/cron/output/<cron_job_id>/<YYYY-MM-DD_HH-MM-SS>.md
```

The `log-cleaner` script:

1. Reads `data/config.json` for base log directory, default expiration, and per-job overrides.
2. For each configured job, scans `<log_dir>/<log_dir_field ?? cron_job_id>/` for `*.md` files.
3. Deletes any file whose **modification time** is older than the configured expiration threshold.
4. Updates the `last_run` timestamp for each job and saves `config.json` atomically.
5. Prints a per-job summary line to stdout (delivered verbatim by the Hermes scheduler).

Runs **daily at 3 AM** (local time) via a registered Hermes cron job.

---

## Configuration (`data/config.json`)

Copy `config.example.json` to `data/config.json` and edit as needed.

### Top-level fields

| Field | Type | Required | Description |
|---|---|---|---|
| `log_dir` | `string` | Yes | Base path where all job log subdirectories live. Supports `~`. Default: `~/.hermes/cron/output` |
| `default_exp` | `integer` | Yes | Default expiration in **days** applied to any job that does not set its own `exp`. |
| `jobs` | `array` | Yes | List of job entries to clean up (see below). |

### Job object fields

| Field | Type | Required | Description |
|---|---|---|---|
| `cron_job_id` | `string` | Yes | The Hermes cron job ID (short hex string visible in `hermes cron list`). |
| `alias` | `string` | No | Human-friendly label shown in output alongside the `cron_job_id`. |
| `exp` | `integer` | No | Expiration in **days** for this job's logs. Defaults to `default_exp` if omitted. |
| `log_dir` | `string` | No | Subdirectory name under the base `log_dir`. Defaults to the value of `cron_job_id` if omitted. |
| `last_run` | `string\|null` | Auto | ISO 8601 UTC timestamp of the last time the cleaner ran for this job. Written automatically — do not edit by hand. |

### Example

```json
{
  "log_dir": "~/.hermes/cron/output",
  "default_exp": 30,
  "jobs": [
    {
      "cron_job_id": "7c0a3f856508",
      "exp": 14,
      "last_run": null
    },
    {
      "cron_job_id": "657c2d4389d2",
      "last_run": null
    },
    {
      "cron_job_id": "job_with_custom_dir",
      "exp": 7,
      "log_dir": "my_custom_subdir",
      "last_run": null
    }
  ]
}
```

In the example above:
- `7c0a3f856508` logs are deleted after **14 days** from `~/.hermes/cron/output/7c0a3f856508/`
- `657c2d4389d2` logs are deleted after **30 days** (inherits `default_exp`)
- `job_with_custom_dir` logs are deleted after **7 days** from `~/.hermes/cron/output/my_custom_subdir/`

---

## Manual Usage

```bash
# Dry-run (preview what would be deleted, no files removed)
python3 ~/.hermes-automations/automations/log-cleaner/scripts/clean_logs.py --dry-run

# Normal run
python3 ~/.hermes-automations/automations/log-cleaner/scripts/clean_logs.py

# With verbose per-file output
python3 ~/.hermes-automations/automations/log-cleaner/scripts/clean_logs.py --dry-run --verbose

# Use a custom config file
python3 ~/.hermes-automations/automations/log-cleaner/scripts/clean_logs.py --config /path/to/config.json
```

Via the delegator stub (same as the Hermes scheduler runs it):

```bash
python3 ~/.hermes/scripts/log_cleaner.py --dry-run
```

---

## Registering the Cron Job

Once `data/config.json` is configured, register the automation in Hermes:

```
Schedule:  0 3 * * *       (daily at 3 AM local time)
Script:    log_cleaner.py
no_agent:  true
deliver:   origin
```

The cron job entry script (`~/.hermes/scripts/log_cleaner.py`) is a thin
delegator stub that calls the real script in this directory.

---

## Adding a New Job

1. Find the cron job ID with `hermes cron list`.
2. Add a new entry to `data/config.json`:
   ```json
   {
     "cron_job_id": "<your-job-id>",
     "exp": 14,
     "last_run": null
   }
   ```
3. The cleaner will pick it up on its next run (no restart needed).

---

## Safety Notes

- Only `*.md` files are targeted — no other file types are touched.
- If a job's resolved log directory does not exist, the cleaner logs a warning and skips it silently (no crash).
- `config.json` is written atomically (write to `.tmp`, then rename) to prevent corruption on failure.
- Exit code is `0` on clean success, `1` if any file produced an OS error.
