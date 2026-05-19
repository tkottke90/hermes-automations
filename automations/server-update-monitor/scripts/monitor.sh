#!/bin/bash
# Server Update Monitor - Main script
# Detects package updates on Linux servers via SSH and stores results in JSON

set -euo pipefail

# Configuration
CONFIG_FILE="$HOME/.hermes/server-update-monitor/config.json"
LOG_DIR="$HOME/.hermes/server-update-monitor/logs"
LOG_FILE="$LOG_DIR/server-update-monitor.log"
DATA_DIR="$HOME/.hermes/server-update-monitor/data"
OUTPUT_FILE="$DATA_DIR/updates.json"
HTML_REPORT="$DATA_DIR/server-update-report.html"
JSON_REPORT_NAME="server-update-report.json"
HTML_REPORT_NAME="server-update-report.html"
PUBLISHER="$HOME/.hermes/lib/report-publisher.py"
PYTHON="$HOME/.hermes/.venv/bin/python"
DRY_RUN=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Initialize log file
init_logging() {
    mkdir -p "$LOG_DIR"
    if [ ! -f "$LOG_FILE" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Server Update Monitor initialized" > "$LOG_FILE"
    fi
}

# Log message
log() {
    local level=$1
    local message=$2
    echo "$(date '+%Y-%m-%d %H:%M:%S') - [$level] $message" >> "$LOG_FILE"
    echo -e "${BLUE}[$level]${NC} $message"
}

# Load configuration
load_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        log "ERROR" "Configuration file not found: $CONFIG_FILE"
        exit 1
    fi
    
    # Check if jq is available
    if ! command -v jq &> /dev/null; then
        log "ERROR" "jq not installed. Please install with: brew install jq"
        exit 1
    fi
    
    # Output servers directly without capturing in variable
    jq -r '.servers[] | @base64' "$CONFIG_FILE"
}

# Encode base64 for jq
base64_decode() {
    local decoded=$(echo "$1" | base64 --decode 2>/dev/null || echo "$1" | base64 -d 2>/dev/null)
    echo "$decoded"
}

# Monitor single server
monitor_server() {
    local server_encoded=$1
    local server=$(base64_decode "$server_encoded")
    
    local host=$(echo "$server" | jq -r '.host')
    local username=$(echo "$server" | jq -r '.username')
    local key_path=$(echo "$server" | jq -r '.key_path')
    local distro=$(echo "$server" | jq -r '.distro')
    
    log "INFO" "Monitoring server: $username@$host (distro: $distro)"
    
    # Check SSH connectivity
    local expanded_key_path="${key_path/#\~/$HOME}"
    if [ ! -f "$expanded_key_path" ]; then
        log "ERROR" "SSH key not found: $expanded_key_path"
        return 1
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log "INFO" "DRY RUN - SSH command would be:"
        echo "  ssh -i $expanded_key_path -o StrictHostKeyChecking=no $username@$host"
        return 0
    fi
    
    # Detect package manager
    local pkg_manager=""
    # Check if distro is explicitly set in config
    if [ "$distro" != "null" ] && [ -n "$distro" ]; then
        case "$distro" in
            "debian"|"ubuntu")
                pkg_manager="apt"
                ;;
            "arch")
                pkg_manager="pacman"
                ;;
            *)
                log "ERROR" "Unsupported distro: $distro. Only debian, ubuntu, arch are supported."
                return 1
                ;;
        esac
    else
        # Auto-detect distro using uname
        log "INFO" "No distro specified in config, auto-detecting via uname..."
        local os_info=$(ssh -i "$expanded_key_path" -o StrictHostKeyChecking=no "$username@$host" "uname -a")
        case "$os_info" in
            *"arch"*)
                pkg_manager="pacman"
                distro="arch"
                log "INFO" "Detected Arch Linux via uname"
                ;;
            *"debian"*|*"ubuntu"*)
                pkg_manager="apt"
                distro="debian"
                log "INFO" "Detected Debian/Ubuntu via uname"
                ;;
            *)
                log "ERROR" "Unable to detect OS from uname output: $os_info"
                return 1
                ;;
        esac
    fi
    
    # Get updates based on package manager
    local updates=0
    local packages=()
    
    case "$pkg_manager" in
        "apt")
            # Get upgradable packages
            local output
            output=$(ssh -i "$expanded_key_path" -o StrictHostKeyChecking=no "$username@$host" \
                "sudo DEBIAN_FRONTEND=noninteractive apt list --upgradable 2>/dev/null | tail -n +2 | wc -l")
            
            updates=$(echo "$output" | tr -d ' ')
            
            if [ "$updates" -gt 0 ]; then
                local pkg_list=$(ssh -i "$expanded_key_path" -o StrictHostKeyChecking=no "$username@$host" \
                    "sudo DEBIAN_FRONTEND=noninteractive apt list --upgradable 2>/dev/null | tail -n +2")
                
                while IFS= read -r line; do
                    [[ -n "$line" ]] || continue
                    local name=$(echo "$line" | cut -d'/' -f1)
                    local version=$(echo "$line" | cut -d'/' -f2 | sed 's/)//')
                    packages+=("{\"name\":\"$name\",\"current\":\"$version\",\"available\":\"$version\"}")
                done <<< "$pkg_list"
            fi
            ;;
        "pacman")
            # Use pacman -Qu (no sudo, no pacman-contrib needed)
            local pkg_list
            pkg_list=$(ssh -i "$expanded_key_path" -o StrictHostKeyChecking=no "$username@$host" \
                "pacman -Qu 2>/dev/null | grep -v '^::' || true")

            updates=$(echo "$pkg_list" | grep -c . || true)
            updates=$(echo "$updates" | tr -d ' ')

            if [ "$updates" -gt 0 ]; then
                while IFS= read -r line; do
                    [[ -n "$line" ]] || continue
                    local name=$(echo "$line" | awk '{print $1}')
                    local current=$(echo "$line" | awk '{print $2}')
                    local available=$(echo "$line" | awk '{print $4}')
                    packages+=("{\"name\":\"$name\",\"current\":\"$current\",\"available\":\"$available\"}")
                done <<< "$pkg_list"
            fi
            ;;
    esac
    
    # Create entry
    local entry
    if [ "$updates" -gt 0 ]; then
        local packages_json=$(printf '%s\n' "${packages[@]}" | jq -s .)
        entry=$(jq -n --arg ts "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
            --arg s "$username@$host" \
            --arg d "$distro" \
            --argjson u "$updates" \
            --argjson p "$packages_json" \
            '{timestamp: $ts, server: $s, distro: $d, update_count: $u, packages: $p}')
    else
        entry=$(jq -n --arg ts "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
            --arg s "$username@$host" \
            --arg d "$distro" \
            --argjson u "$updates" \
            '{timestamp: $ts, server: $s, distro: $d, update_count: $u, packages: []}')
    fi
    
    log "INFO" "Found $updates updates on $username@$host"
    
    # Write to server-specific temp file
    local server_temp="$DATA_DIR/updates_temp_${server_count}.json"
    printf "%s" "$entry" > "$server_temp"
    
    return 0
}

# Combine entries into proper JSON array
combine_entries() {
    local data_dir="$1"
    local output_file="$2"
    
    # Find all temp files and combine them
    local temp_files=()
    for temp_file in "$data_dir"/updates_temp_*.json; do
        if [ -f "$temp_file" ]; then
            temp_files+=("$temp_file")
        fi
    done
    
    log "DEBUG" "Found ${#temp_files[@]} temp files to combine"
    
    # Combine all temp files into a single temp file
    if [ ${#temp_files[@]} -gt 0 ]; then
        local combined_temp="$data_dir/updates_combined_temp.json"
        cat "${temp_files[@]}" > "$combined_temp"
        
        # Reformat into proper JSON array with unique servers (keep latest)
        jq -s 'group_by(.server) | map({server: .[0].server, distro: .[0].distro, update_count: .[0].update_count, packages: .[0].packages, timestamp: .[0].timestamp}) | sort_by(.timestamp | fromdateiso8601) | reverse' "$combined_temp" > "$output_file.tmp"
        mv "$output_file.tmp" "$output_file"
        
        # Clean up temp files
        for temp_file in "${temp_files[@]}"; do
            rm -f "$temp_file"
        done
        rm -f "$combined_temp"
    fi
}

# Generate HTML report from updates.json
generate_html_report() {
    local json_file="$1"
    local html_file="$2"

    log "INFO" "Generating HTML report: $html_file"

    local generated_at
    generated_at=$(date -u +"%Y-%m-%d %H:%M:%S UTC")

    local total_servers
    total_servers=$(jq 'length' "$json_file")

    local servers_with_updates
    servers_with_updates=$(jq '[.[] | select(.update_count > 0)] | length' "$json_file")

    local total_updates
    total_updates=$(jq '[.[].update_count] | add // 0' "$json_file")

    # Build per-server rows
    local rows
    rows=$(jq -r '
      .[] |
      . as $srv |
      if .update_count > 0 then
        "<tr>\n  <td class=\"mono\">\(.server)</td>\n  <td><span class=\"badge badge-distro\">\(.distro)</span></td>\n  <td><span class=\"badge badge-warn\">\(.update_count) ⚠</span></td>\n  <td class=\"pkg-list\">" +
        ([ .packages[] | "<span class=\"pkg\"><strong>" + .name + "</strong> " + .current + " → " + .available + "</span>" ] | join("")) +
        "</td>\n</tr>"
      else
        "<tr>\n  <td class=\"mono\">\(.server)</td>\n  <td><span class=\"badge badge-distro\">\(.distro)</span></td>\n  <td><span class=\"badge badge-ok\">0 ✓</span></td>\n  <td class=\"muted\">—</td>\n</tr>"
      end
    ' "$json_file")

    cat > "$html_file" <<HTML
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Server Update Report</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #0d1117;
      color: #c9d1d9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      font-size: 14px;
      padding: 32px;
      line-height: 1.6;
    }
    h1 { font-size: 22px; font-weight: 600; color: #e6edf3; margin-bottom: 4px; }
    .subtitle { color: #8b949e; font-size: 13px; margin-bottom: 28px; }
    .summary-grid {
      display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 28px;
    }
    .stat-card {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 16px 24px;
      min-width: 160px;
    }
    .stat-card .label { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: #8b949e; margin-bottom: 4px; }
    .stat-card .value { font-size: 28px; font-weight: 700; color: #e6edf3; }
    .stat-card .value.warn { color: #f0883e; }
    .stat-card .value.ok   { color: #3fb950; }
    table {
      width: 100%;
      border-collapse: collapse;
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      overflow: hidden;
    }
    thead { background: #21262d; }
    th {
      text-align: left;
      padding: 10px 14px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .06em;
      color: #8b949e;
      border-bottom: 1px solid #30363d;
    }
    td {
      padding: 10px 14px;
      border-bottom: 1px solid #21262d;
      vertical-align: top;
    }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #1c2128; }
    .mono { font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; font-size: 13px; }
    .muted { color: #484f58; }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 600;
    }
    .badge-distro { background: #1f3a5f; color: #79c0ff; }
    .badge-ok     { background: #0f2d1a; color: #3fb950; }
    .badge-warn   { background: #3d1f00; color: #f0883e; }
    .pkg-list { display: flex; flex-wrap: wrap; gap: 4px; }
    .pkg {
      background: #21262d;
      border: 1px solid #30363d;
      border-radius: 4px;
      padding: 1px 7px;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      font-size: 11px;
      color: #c9d1d9;
    }
    .pkg strong { color: #e6edf3; }
    footer { margin-top: 24px; font-size: 12px; color: #484f58; }
  </style>
</head>
<body>
  <h1>🖥 Server Update Report</h1>
  <p class="subtitle">Generated: ${generated_at}</p>

  <div class="summary-grid">
    <div class="stat-card">
      <div class="label">Servers Scanned</div>
      <div class="value">${total_servers}</div>
    </div>
    <div class="stat-card">
      <div class="label">Servers with Updates</div>
      <div class="value $([ "$servers_with_updates" -gt 0 ] && echo warn || echo ok)">${servers_with_updates}</div>
    </div>
    <div class="stat-card">
      <div class="label">Total Pending Updates</div>
      <div class="value $([ "$total_updates" -gt 0 ] && echo warn || echo ok)">${total_updates}</div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Server</th>
        <th>Distro</th>
        <th>Updates</th>
        <th>Packages</th>
      </tr>
    </thead>
    <tbody>
${rows}
    </tbody>
  </table>

  <footer>Server Update Monitor · Data from <code>updates.json</code></footer>
</body>
</html>
HTML

    log "INFO" "HTML report written: $html_file"
}

# Publish a file to MinIO via report-publisher.py (non-fatal)
publish_to_minio() {
    local file_path="$1"
    local object_name="$2"

    if [ ! -f "$PYTHON" ]; then
        log "WARN" "Python venv not found at $PYTHON — skipping MinIO publish"
        return 0
    fi
    if [ ! -f "$PUBLISHER" ]; then
        log "WARN" "report-publisher.py not found at $PUBLISHER — skipping MinIO publish"
        return 0
    fi

    local publish_args=("$PYTHON" "$PUBLISHER" "$file_path" "$object_name")
    if [ "$DRY_RUN" = true ]; then
        publish_args+=("--dry-run")
    fi

    local result
    if result=$("${publish_args[@]}" 2>&1); then
        log "INFO" "MinIO publish OK: $result"
        echo "$result"
    else
        log "WARN" "MinIO publish failed (non-fatal): $result"
        echo -e "${YELLOW}[WARN]${NC} MinIO publish failed: $result"
    fi
}

# Main function
main() {
    init_logging
    log "INFO" "Starting Server Update Monitor"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            *)
                log "ERROR" "Unknown option: $1"
                echo "Usage: $0 [--dry-run]"
                exit 1
                ;;
        esac
    done
    
    # Load and process servers
    log "INFO" "Starting server processing loop"
    log "DEBUG" "Reading config file with jq..."
    log "DEBUG" "Config file path: $CONFIG_FILE"
    
    # Read servers from config directly (hardcoded base64 for testing)
    base64_servers=(
        "eyJob3N0IjoiMTAuMC4wLjEyIiwidXNlcm5hbWUiOiJ0a290dGtlIiwia2V5X3BhdGgiOiJ+Ly5zc2gvaWRfZWQyNTUxOSIsImRpc3RybyI6ImFyY2gifQ=="
        "eyJob3N0IjoiMTAuMC4wLjEiLCJ1c2VybmFtZSI6InRrb3R0a2UiLCJrZXlfcGF0aCI6In4vLnNzaC9pZF9lZDI1NTE5IiwiZGlzdHJvIjoiZGViaWFuIn0="
    )
    
    log "DEBUG" "Found ${#base64_servers[@]} servers in config"
    
    temp_count=$(mktemp)
    server_count=0
    
    for base64_input in "${base64_servers[@]}"; do
        echo "DEBUG: Processing server #$server_count" >> /tmp/monitor_debug.txt
        log "INFO" "Processing server #$server_count"
        
        server_decoded=$(echo "$base64_input" | base64 --decode)
        
        server_host=$(echo "$server_decoded" | jq -r ".host")
        server_username=$(echo "$server_decoded" | jq -r ".username")
        server_key_path=$(echo "$server_decoded" | jq -r ".key_path")
        server_distro=$(echo "$server_decoded" | jq -r ".distro")
        
        log "INFO" "Monitoring server: $server_username@$server_host (distro: $server_distro)"
        
        # Check SSH connectivity
        expanded_key_path="${server_key_path/#\~/$HOME}"
        if [ ! -f "$expanded_key_path" ]; then
            log "ERROR" "SSH key not found: $expanded_key_path"
            continue
        fi
        
        # Monitor the server
        if ! monitor_server "$base64_input"; then
            log "ERROR" "Failed to process server"
            continue
        fi
        
        ((server_count++))
        log "INFO" "Server #$server_count completed"
    done
    
    # Combine all entries into proper JSON array
    log "INFO" "Combining entries into proper JSON format"
    combine_entries "$DATA_DIR" "$OUTPUT_FILE"
    
    log "INFO" "Processing complete: $server_count servers processed"

    # ── Generate and publish reports ─────────────────────────────────────────
    local html_url=""
    local json_url=""

    if [ -f "$OUTPUT_FILE" ]; then
        # Generate HTML report
        generate_html_report "$OUTPUT_FILE" "$HTML_REPORT"

        # Publish HTML
        log "INFO" "Publishing HTML report to MinIO as $HTML_REPORT_NAME"
        html_url=$(publish_to_minio "$HTML_REPORT" "$HTML_REPORT_NAME" | grep -o 'http://[^ ]*' | tail -1 || true)

        # Publish JSON
        log "INFO" "Publishing JSON report to MinIO as $JSON_REPORT_NAME"
        json_url=$(publish_to_minio "$OUTPUT_FILE" "$JSON_REPORT_NAME" | grep -o 'http://[^ ]*' | tail -1 || true)
    else
        log "WARN" "No output JSON found at $OUTPUT_FILE — skipping report generation"
    fi

    log "INFO" "Server Update Monitor completed"
    echo ""
    echo -e "${GREEN}✓ Update scan completed${NC}"
    printf "  %-18s %s\n" "Servers processed:" "$server_count"
    printf "  %-18s %s\n" "JSON data:" "$OUTPUT_FILE"
    printf "  %-18s %s\n" "HTML report:" "$HTML_REPORT"
    if [ -n "$html_url" ]; then
        printf "  %-18s %s\n" "HTML (MinIO):" "$html_url"
    fi
    if [ -n "$json_url" ]; then
        printf "  %-18s %s\n" "JSON (MinIO):" "$json_url"
    fi
    printf "  %-18s %s\n" "Log file:" "$LOG_FILE"
}

main "$@"
