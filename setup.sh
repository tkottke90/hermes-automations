#!/usr/bin/env bash
# setup.sh — Create ~/.hermes symlinks for hermes-automations
# Usage: ./setup.sh [--dry-run]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=false

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "🔍 DRY RUN — no changes will be made"
fi

# ── Symlink definitions ───────────────────────────────────────────────────────
declare -A LINKS=(
  ["$HOME/.hermes/automations"]="$REPO_DIR/automations"
  ["$HOME/.hermes/skills/custom"]="$REPO_DIR/skills"
  ["$HOME/.hermes/lib"]="$REPO_DIR/lib"
)

# ── Helper ────────────────────────────────────────────────────────────────────
create_link() {
  local target="$1"
  local source="$2"

  if [[ -L "$target" ]]; then
    existing="$(readlink "$target")"
    if [[ "$existing" == "$source" ]]; then
      echo "  ✅ Already linked: $target → $source"
      return
    else
      echo "  ⚠️  Symlink exists but points elsewhere: $target → $existing"
      echo "     Will repoint to: $source"
      if [[ "$DRY_RUN" == "false" ]]; then
        rm "$target"
        ln -s "$source" "$target"
        echo "  ✅ Relinked: $target → $source"
      fi
    fi
  elif [[ -e "$target" ]]; then
    echo "  ❌ ERROR: $target exists and is NOT a symlink. Remove it manually before running setup."
    exit 1
  else
    echo "  🔗 Creating: $target → $source"
    if [[ "$DRY_RUN" == "false" ]]; then
      mkdir -p "$(dirname "$target")"
      ln -s "$source" "$target"
      echo "  ✅ Done"
    fi
  fi
}

# ── Run ───────────────────────────────────────────────────────────────────────
echo ""
echo "🚀 Setting up hermes-automations symlinks..."
echo ""

for target in "${!LINKS[@]}"; do
  create_link "$target" "${LINKS[$target]}"
done

echo ""
if [[ "$DRY_RUN" == "true" ]]; then
  echo "✅ Dry run complete. Run without --dry-run to apply changes."
else
  echo "✅ Setup complete."
fi
