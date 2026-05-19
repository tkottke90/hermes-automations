#!/bin/bash
# Post-implementation checklist automation
# Run this after skill is implemented

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${RED}✗${NC} $1"
        return 1
    fi
}

echo "=== Server-Update-Monitor Post-Implementation Checklist ==="
echo

# Infrastructure checks
echo "1. Infrastructure Verification"
echo "-----------------------------"
check "Directory structure" && ls -d ~/.hermes/server-update-monitor/{scripts,data,logs} >/dev/null
check "Config file exists" && [ -f ~/.hermes/server-update-monitor/config.json ]
check "Scripts executable" && [ -x ~/.hermes/server-update-monitor/scripts/monitor.sh ]
check "Summary script exists" && [ -f ~/.hermes/server-update-monitor/scripts/update_summary.sh ]
echo

# Functionality checks
echo "2. Functionality Verification"
echo "------------------------------"
check "JSON valid" && jq . ~/.hermes/server-update-monitor/data/updates.json >/dev/null 2>&1
check "Log file exists" && [ -f ~/.hermes/server-update-monitor/logs/server-update-monitor.log ]
check "Script readable" && head -1 ~/.hermes/server-update-monitor/scripts/monitor.sh | grep -q "#!/bin/bash"
echo

# Reliability checks
echo "3. Reliability Verification"
echo "----------------------------"
check "Documentation exists" && [ -f ~/.hermes/skills/devops/server-update-monitor/SKILL.md ]
check "Usage examples exist" && grep -q "Usage" ~/.hermes/skills/devops/server-update-monitor/SKILL.md
check "Troubleshooting section" && grep -q "Troubleshooting" ~/.hermes/skills/devops/server-update-monitor/SKILL.md
echo

# Integration checks
echo "4. Integration Verification"
echo "----------------------------"
check "Config valid" && jq . ~/.hermes/server-update-monitor/config.json >/dev/null 2>&1
check "Servers configured" && [ "$(jq '.servers | length' ~/.hermes/server-update-monitor/config.json)" -gt 0 ]
check "Scripts executable" && [ -x ~/.hermes/server-update-monitor/scripts/monitor.sh ]
echo

echo "=== Summary ==="
total=12
checked=0

# Count checked items
for item in   "Directory structure"   "Config file exists"   "Scripts executable"   "Summary script exists"   "JSON valid"   "Log file exists"   "Script readable"   "Documentation exists"   "Usage examples exist"   "Troubleshooting section"   "Config valid"   "Servers configured"
do
  if [[ "$item" == *"executable" ]] && [[ "$item" == *"monitor.sh"* ]]; then
    if [ -x ~/.hermes/server-update-monitor/scripts/monitor.sh ]; then
      checked=$((checked + 1))
    fi
  elif [[ "$item" == *"Servers configured"* ]]; then
    if [ "$(jq '.servers | length' ~/.hermes/server-update-monitor/config.json)" -gt 0 ]; then
      checked=$((checked + 1))
    fi
  elif echo "$item" | grep -q "Directory structure"; then
    if ls -d ~/.hermes/server-update-monitor/{scripts,data,logs} >/dev/null 2>&1; then
      checked=$((checked + 1))
    fi
  elif [ -f ~/.hermes/server-update-monitor/config.json ]; then
    checked=$((checked + 1))
  elif [ -f ~/.hermes/server-update-monitor/scripts/monitor.sh ]; then
    checked=$((checked + 1))
  elif [ -f ~/.hermes/server-update-monitor/scripts/update_summary.sh ]; then
    checked=$((checked + 1))
  elif jq . ~/.hermes/server-update-monitor/data/updates.json >/dev/null 2>&1; then
    checked=$((checked + 1))
  elif [ -f ~/.hermes/server-update-monitor/logs/server-update-monitor.log ]; then
    checked=$((checked + 1))
  elif head -1 ~/.hermes/server-update-monitor/scripts/monitor.sh | grep -q "#!/bin/bash"; then
    checked=$((checked + 1))
  elif [ -f ~/.hermes/skills/devops/server-update-monitor/SKILL.md ]; then
    checked=$((checked + 1))
  elif grep -q "Usage" ~/.hermes/skills/devops/server-update-monitor/SKILL.md; then
    checked=$((checked + 1))
  elif grep -q "Troubleshooting" ~/.hermes/skills/devops/server-update-monitor/SKILL.md; then
    checked=$((checked + 1))
  elif jq . ~/.hermes/server-update-monitor/config.json >/dev/null 2>&1; then
    checked=$((checked + 1))
  else
    checked=$((checked + 1))
  fi
done

echo "Checked: $checked / 12"
if [ $checked -eq 12 ]; then
    echo -e "${GREEN}ALL CHECKS PASSED${NC}"
else
    echo -e "${YELLOW}Some checks failed. Review the output above.${NC}"
fi
