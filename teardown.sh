#!/usr/bin/env bash
# teardown.sh — Remove ~/.hermes symlinks created by setup.sh
# Usage: ./teardown.sh [--dry-run]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=false

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "🔍 DRY RUN — no changes will be made"
fi

# ── Helper ────────────────────────────────────────────────────────────────────
remove_link() {
  local target="$1"

  if [[ -L "$target" ]]; then
    echo "  🗑️  Removing symlink: $target → $(readlink "$target")"
    if [[ "$DRY_RUN" == "false" ]]; then
      rm "$target"
      echo "  ✅ Removed"
    fi
  elif [[ -e "$target" ]]; then
    echo "  ⚠️  SKIPPED: $target exists but is NOT a symlink. Will not touch it."
  else
    echo "  ℹ️  Not found (nothing to remove): $target"
  fi
}

# ── Directory symlinks ────────────────────────────────────────────────────────
echo ""
echo "🧹 Tearing down hermes-automations symlinks..."
echo ""

MANAGED_LINKS=(
  "$HOME/.hermes/automations"
  "$HOME/.hermes/skills/custom"
)

for target in "${MANAGED_LINKS[@]}"; do
  remove_link "$target"
done

# ── lib/ — remove individual file symlinks ────────────────────────────────────
echo ""
echo "📚 Removing lib file symlinks from ~/.hermes/lib/..."
echo ""

for src_file in "$REPO_DIR/lib"/*; do
  [[ -f "$src_file" ]] || continue
  filename="$(basename "$src_file")"
  remove_link "$HOME/.hermes/lib/$filename"
done

echo ""
if [[ "$DRY_RUN" == "true" ]]; then
  echo "✅ Dry run complete. Run without --dry-run to apply changes."
else
  echo "✅ Teardown complete."
fi
