#!/bin/bash
# Server Update Summary - Display updates from JSON file

set -euo pipefail

DATA_DIR="$HOME/.hermes/server-update-monitor/data"
OUTPUT_FILE="$DATA_DIR/updates.json"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required. Install with: brew install jq"
    exit 1
fi

# Check if output file exists
if [ ! -f "$OUTPUT_FILE" ]; then
    echo "No updates found yet. Run monitor.sh first."
    exit 0
fi

echo "=== Server Update Summary ==="
echo

# Check if the output is an array or single object
if jq 'type' "$OUTPUT_FILE" | grep -q '"object"'; then
    # Single object - wrap in array for jq commands
    SERVERS=$(jq '.server' "$OUTPUT_FILE")
    UPDATE_COUNT=$(jq '.update_count' "$OUTPUT_FILE")
else
    # Array
    total_updates=$(jq '[.[] | .update_count] | add' "$OUTPUT_FILE")
    total_servers=$(jq '[.[] | .server] | length' "$OUTPUT_FILE")
    
    echo "Servers checked: $total_servers"
    echo "Total updates detected: $total_updates"
    echo
    
    # Display latest update per server
    echo "=== Latest Update per Server ==="
    jq -r '.[] | "\(.server): \(.update_count) updates"' "$OUTPUT_FILE" | while read -r line; do
        server=$(echo "$line" | cut -d: -f1)
        count=$(echo "$line" | cut -d: -f2)
        
        if [ "$count" -gt 0 ]; then
            echo -e "  ${GREEN}✓${NC} $server: $count updates available"
            
            # Show top 3 packages
            echo -n "    Top 3 packages: "
            jq -r ".[] | select(.server == \"$server\") | .packages[] | .name" "$OUTPUT_FILE" | head -3 | tr '\n' ' '
            echo
        else
            echo -e "  ${GREEN}✓${NC} $server: No updates"
        fi
    done
    echo
    echo "Full JSON output: $OUTPUT_FILE"
    exit 0
fi

echo "Servers checked: 1"
echo "Total updates detected: $UPDATE_COUNT"
echo
echo "=== Latest Update per Server ==="
echo -e "  ${GREEN}✓${NC} $SERVERS: No updates"
echo
echo "Full JSON output: $OUTPUT_FILE"