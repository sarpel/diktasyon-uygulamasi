#!/usr/bin/env bash
# Dikte'yi kullanıcı düzeyinde kurar (root gerekmez).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"

if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx bulunamadı. Kurulum: python3 -m pip install --user pipx" >&2
  exit 1
fi

echo "1/3 Uygulama kuruluyor…"
pipx install --force "$ROOT"

echo "2/3 Masaüstü kaydı yazılıyor…"
mkdir -p "$APPS" "$ICONS"
install -m 644 "$ROOT/packaging/linux/dikte.desktop" "$APPS/dikte.desktop"
install -m 644 "$ROOT/packaging/linux/dikte.png" "$ICONS/dikte.png"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" || true

echo "3/3 Modeller indiriliyor…"
"$(pipx environment --value PIPX_LOCAL_VENVS)/dikte/bin/python" "$ROOT/scripts/download_models.py"

cat <<'HINT'

Kurulum tamam. Global kısayol için masaüstü ortamınızda özel bir kısayol tanımlayın:
  GNOME : Ayarlar → Klavye → Özel Kısayollar → Komut: dikte --toggle
  KDE   : Sistem Ayarları → Kısayollar → Özel → Komut: dikte --toggle
HINT
