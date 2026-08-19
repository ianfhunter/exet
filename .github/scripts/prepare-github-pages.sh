#!/usr/bin/env bash
set -euo pipefail

# Rewrite local Exolve asset paths to the official Exolve GitHub Pages site.
# Used only at deploy time so forks can keep relative paths in source/PRs.

EXOLVE_BASE="${EXOLVE_BASE:-https://viresh-ratnakar.github.io/}"
SITE_DIR="${1:-.}"

HTML_FILES=(
  exet.html
  exet-brazilian.html
  exet-hindi.html
)

for file in "${HTML_FILES[@]}"; do
  path="${SITE_DIR%/}/${file}"
  if [[ ! -f "$path" ]]; then
    echo "Skipping missing file: $path" >&2
    continue
  fi
  sed -i \
    -e "s|href=\"exolve-|href=\"${EXOLVE_BASE}exolve-|g" \
    -e "s|src=\"exolve-|src=\"${EXOLVE_BASE}exolve-|g" \
    "$path"
  echo "Rewrote Exolve URLs in $path"
done
