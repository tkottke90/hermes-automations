---
name: server-update-monitor
description: "SSH-based Linux server package update checker — polls configured servers daily and reports available updates via Hermes."
version: 1.0.0
author: tkottke
license: UNLICENSED
schedule: "0 9 * * *"
platforms: [macos, linux]
metadata:
  hermes:
    tags: [devops, monitoring, linux, ssh, updates]
    scripts:
      - name: server-update-monitor
        file: monitor.sh
        no_agent: false
        deliver: origin
        schedule: "0 9 * * *"
    env:
      - SSH key at ~/.ssh/hermes-agent
---

# Server Update Monitor

Connects to configured Linux servers via SSH and checks for available package updates. Supports both Arch Linux (pacman) and Debian/Ubuntu (apt). Results are reported through Hermes daily at 9 AM.

## Supported Distributions

| Distro | Package Manager | Check Command |
|---|---|---|
| Arch Linux | pacman | `checkupdates` |
| Debian/Ubuntu | apt | `apt list --upgradable` |

## Files

| File | Purpose |
|---|---|
| `scripts/monitor.sh` | Main SSH check script — runs on each configured server |
| `scripts/update_summary.sh` | Formats update output for Hermes delivery |
| `test-checklist.sh` | Manual test runner for validating SSH connectivity |
| `data/config.json` | Server list with SSH connection details (gitignored) |
| `data/updates.json` | Last-known update state (gitignored) |
| `data/logs/` | Script execution logs (gitignored) |

## Server Configuration

`data/config.json` defines which servers to monitor:

```json
{
  "servers": [
    {
      "host": "10.0.0.12",
      "username": "tkottke",
      "key_path": "~/.ssh/hermes-agent",
      "distro": "arch"
    },
    {
      "host": "10.0.0.1",
      "username": "tkottke",
      "key_path": "~/.ssh/hermes-agent",
      "distro": "debian"
    }
  ]
}
```

## SSH Key Setup

The monitor uses a dedicated SSH key at `~/.ssh/hermes-agent`. Ensure this key is authorized on each server:

```sh
ssh-copy-id -i ~/.ssh/hermes-agent.pub tkottke@<host>
```
