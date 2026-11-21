#!/usr/bin/env bash
# Download the pinned Mondrian 3.2 runtime listed in mondrian/artifacts.txt into a folder and
# check the SHA-256 of every file before anything runs it. Usage: scripts/fetch-mondrian.sh <dir>
set -euo pipefail
list="$(cd "$(dirname "$0")/.." && pwd)/mondrian/artifacts.txt"
dir="$1"
mkdir -p "$dir"
while read -r sum file url; do
  [ -n "$sum" ] || continue
  curl -fsSL --retry 4 --retry-delay 10 -A p64-lab-fetch/1.0 -o "$dir/$file" "$url"
done < "$list"
awk 'NF { print $1 "  " $2 }' "$list" > "$dir/SHA256SUMS"
(cd "$dir" && sha256sum -c SHA256SUMS)
