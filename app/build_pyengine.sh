#!/usr/bin/env bash
# Кладёт relocatable Python + установленный ihonor в каталог $1 (Resources/pyengine).
set -euo pipefail

DEST="${1:?usage: build_pyengine.sh <dest-dir>}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
case "$(uname -m)" in
  arm64|aarch64) PBS_ARCH="aarch64-apple-darwin" ;;
  x86_64)        PBS_ARCH="x86_64-apple-darwin" ;;
  *) echo "✗ неподдерживаемая архитектура: $(uname -m)"; exit 1 ;;
esac
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.12.7+20241016-${PBS_ARCH}-install_only.tar.gz"

# Фаст-путь: python+apsw+ihonor уже на месте → обновляем только пакет ihonor
# (исходники могли поменяться) и доустанавливаем недостающие зависимости.
if [ -x "$DEST/bin/python3" ] && "$DEST/bin/python3" -c "import apsw, requests, websocket, gmssl, pyicloud, dotenv" 2>/dev/null; then
  echo "→ обновляю ihonor в существующем pyengine"
  "$DEST/bin/python3" -m pip install --force-reinstall --no-deps --no-warn-script-location "$REPO"
  "$DEST/bin/python3" -m pip install --no-warn-script-location "$REPO"  # реконсиляция deps
  "$DEST/bin/python3" -c "import ihonor, apsw" || { echo "✗ pyengine битый"; exit 1; }
  echo "✓ pyengine обновлён: $DEST/bin/python3"; exit 0
fi

TMP="$(mktemp -d)"
# чистим temp + неудавшийся staging при любом выходе ($DEST.old НЕ трогаем — это бэкап для восстановления)
trap 'rm -rf "$TMP" "$DEST.new"' EXIT

echo "→ скачиваю python-build-standalone"
curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 20 "$PBS_URL" -o "$TMP/py.tar.gz"
echo "→ проверяю sha256"
EXPECTED="$(curl -fsSL --retry 3 --connect-timeout 20 "$PBS_URL.sha256")"
echo "$EXPECTED  $TMP/py.tar.gz" | shasum -a 256 -c - || { echo "✗ sha256 mismatch"; exit 1; }

# Сборка в staging, атомарный swap — $DEST всегда либо старый-рабочий, либо новый-рабочий.
STAGE="$DEST.new"
rm -rf "$STAGE"; mkdir -p "$STAGE"
tar -xzf "$TMP/py.tar.gz" -C "$TMP"
cp -R "$TMP/python/." "$STAGE/"
echo "→ ставлю ihonor + deps в bundled python"
"$STAGE/bin/python3" -m pip install --no-warn-script-location "$REPO"
"$STAGE/bin/python3" -c "import ihonor, apsw" || { echo "✗ staging битый"; exit 1; }
# Swap с бэкапом: старый отводим в .old, ставим новый, чистим .old. Окно «нет pyengine»
# минимально (mv внутри одной ФС атомарен), а при краше остаётся .old для восстановления.
[ -d "$DEST" ] && mv "$DEST" "$DEST.old"
mv "$STAGE" "$DEST"
rm -rf "$DEST.old"
echo "✓ pyengine готов: $DEST/bin/python3"
