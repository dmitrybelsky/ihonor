#!/bin/bash
# Один тик синка: гарантировать HonorWorkStation с CDP-портом, затем цикл движка.
set -e
REPO="/Users/dmitrybelsky/projects/ihonor"
LOG="$HOME/.ihonor/sync.log"
mkdir -p "$HOME/.ihonor"

# HonorWorkStation с remote-debugging (для HONOR write через CDP)
if ! curl -s http://localhost:9222/json >/dev/null 2>&1; then
  pkill -f 'MacOS/Hihonornote' 2>/dev/null || true
  sleep 2
  open -a HonorWorkStation --args --remote-debugging-port=9222
  sleep 10
fi
# foreground + Electron AX (для best-effort delete)
osascript -e 'tell application "HonorWorkStation" to activate' >/dev/null 2>&1 || true

cd "$REPO"
echo "=== $(date) tick ===" >> "$LOG"
/opt/homebrew/bin/uv run python -m ihonor.runner >> "$LOG" 2>&1
