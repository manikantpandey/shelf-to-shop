#!/usr/bin/env bash
# commit-msg hook: drop AI-attribution trailer lines from the commit message.
# Removes lines matching (case-insensitive):
#   ^Co-Authored-By:.*(claude|anthropic)
#   ^Claude-Session:
#   Generated with.*Claude Code
# Usage (via pre-commit): strip-ai-trailers.sh <path-to-commit-msg-file>
set -euo pipefail

msg_file="${1:?commit message file path required}"
tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

# awk + tolower() keeps this portable across GNU and BSD userlands.
awk '
  {
    line = tolower($0)
    sub(/\r$/, "", line)
    if (line ~ /^co-authored-by:.*(claude|anthropic)/) next
    if (line ~ /^claude-session:/) next
    if (line ~ /generated with.*claude code/) next
    print
  }
' "$msg_file" > "$tmp_file"

# Trim trailing blank lines left behind by removed trailers.
awk '
  { lines[NR] = $0 }
  END {
    last = NR
    while (last > 0 && lines[last] ~ /^[[:space:]]*$/) last--
    for (i = 1; i <= last; i++) print lines[i]
  }
' "$tmp_file" > "$msg_file"
