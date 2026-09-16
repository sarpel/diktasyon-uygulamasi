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

# pipx her zaman kendi yalıtılmış ortamını kurar; etkin sanal ortamı değil, kendi varsayılan
# yorumlayıcısını kullanır. Bu yüzden pyproject'in istediği sürüm açıkça seçilir.
PYTHON="${DIKTE_PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON="$candidate"
      break
    fi
  done
fi
if [ -z "$PYTHON" ]; then
  echo "Python 3.11 veya 3.12 bulunamadı (pyproject: >=3.11,<3.13)." >&2
  echo "Kurulum: sudo apt install python3.12-venv  — ya da DIKTE_PYTHON=/yol/python ile belirtin." >&2
  exit 1
fi

echo "1/3 Uygulama kuruluyor… ($PYTHON)"
pipx install --python "$PYTHON" --force "$ROOT"

echo "2/3 Masaüstü kaydı yazılıyor…"
mkdir -p "$APPS" "$ICONS"
install -m 644 "$ROOT/packaging/linux/dikte.desktop" "$APPS/dikte.desktop"
install -m 644 "$ROOT/packaging/linux/dikte.png" "$ICONS/dikte.png"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS"
fi

echo "3/3 Modeller indiriliyor…"
"$(pipx environment --value PIPX_LOCAL_VENVS)/dikte/bin/python" "$ROOT/scripts/download_models.py"

cat <<'HINT'

Kurulum tamam. Global kısayol için masaüstü ortamınızda özel bir kısayol tanımlayın:
  GNOME : Ayarlar → Klavye → Özel Kısayollar → Komut: dikte --toggle
  KDE   : Sistem Ayarları → Kısayollar → Özel → Komut: dikte --toggle
HINT

# Otomatik yapıştırma için yardımcı araç kontrolü (kurulum yapılmaz, yalnızca uyarılır).
if ! command -v xdotool >/dev/null && ! command -v wtype >/dev/null; then
  echo "Uyarı: xdotool (X11) veya wtype (Wayland) bulunamadı."
  echo "       Bunlar olmadan sonuç metni aktif pencereye yapıştırılamaz, yalnızca panoya yazılır."
fi
