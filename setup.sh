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

# ── Directory symlinks ────────────────────────────────────────────────────────
echo ""
echo "🚀 Setting up hermes-automations symlinks..."
echo ""

DIR_LINKS=(
  "$HOME/.hermes/automations|$REPO_DIR/automations"
  "$HOME/.hermes/skills/custom|$REPO_DIR/skills"
)

for entry in "${DIR_LINKS[@]}"; do
  target="${entry%%|*}"
  source="${entry##*|}"
  create_link "$target" "$source"
done

# ── lib/ — symlink individual files (target dir already exists) ───────────────
echo ""
echo "📚 Symlinking lib files into ~/.hermes/lib/..."
echo ""

mkdir -p "$HOME/.hermes/lib"
for src_file in "$REPO_DIR/lib"/*; do
  [[ -f "$src_file" ]] || continue
  filename="$(basename "$src_file")"
  target="$HOME/.hermes/lib/$filename"
  create_link "$target" "$src_file"
done

echo ""
if [[ "$DRY_RUN" == "true" ]]; then
  echo "✅ Dry run complete. Run without --dry-run to apply changes."
else
  echo "✅ Setup complete."
fi
