#!/usr/bin/env bash
# Кладёт relocatable Python + установленный ihonor в каталог $1 (Resources/pyengine).
set -euo pipefail

DEST="${1:?usage: build_pyengine.sh <dest-dir>}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.12.7+20241016-aarch64-apple-darwin-install_only.tar.gz"

if [ -x "$DEST/bin/python3" ] && "$DEST/bin/python3" -c "import ihonor, apsw" 2>/dev/null; then
  echo "pyengine уже собран: $DEST"; exit 0
fi

TMP="$(mktemp -d)"
echo "→ скачиваю python-build-standalone"
curl -fsSL "$PBS_URL" -o "$TMP/py.tar.gz"
rm -rf "$DEST"; mkdir -p "$DEST"
tar -xzf "$TMP/py.tar.gz" -C "$TMP"
cp -R "$TMP/python/." "$DEST/"
echo "→ ставлю ihonor + deps в bundled python"
"$DEST/bin/python3" -m pip install --no-warn-script-location "$REPO"
rm -rf "$TMP"
echo "✓ pyengine готов: $DEST/bin/python3"
