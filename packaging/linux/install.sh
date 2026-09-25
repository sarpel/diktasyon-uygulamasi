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

echo "1/4 Uygulama kuruluyor… ($PYTHON)"
# [cuda] extra'sı cuBLAS/cuDNN'i pip tekerlekleriyle getirir; sistemde CUDA kurulu olmasa da
# model yüklenebilsin diye gerekli.
pipx install --python "$PYTHON" --force "${ROOT}[cuda]"
VENV="$(pipx environment --value PIPX_LOCAL_VENVS)/dikte"

echo "2/4 Başlatıcı yazılıyor…"
# ctranslate2, pip'in nvidia/*/lib dizinlerindeki kitaplıkları kendisi bulamaz; süreç
# başlamadan LD_LIBRARY_PATH'e eklenmeleri gerekir. Dizinler her açılışta yeniden taranır,
# böylece paket güncellemelerinden (ör. python sürümü değişimi) sonra da doğru kalır.
LAUNCHER_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/dikte"
LAUNCHER="$LAUNCHER_DIR/dikte-launcher"
mkdir -p "$LAUNCHER_DIR"
{
  echo "#!/usr/bin/env bash"
  echo "# install.sh tarafından üretildi: pip'in CUDA kitaplıklarını görünür kılıp Dikte'yi başlatır."
  printf 'VENV=%q\n' "$VENV"
} >"$LAUNCHER"
cat >>"$LAUNCHER" <<'LAUNCH'
libs=""
for dir in "$VENV"/lib/python3*/site-packages/nvidia/*/lib; do
  if [ -d "$dir" ]; then
    libs="${libs:+$libs:}$dir"
  fi
done
if [ -n "$libs" ]; then
  export LD_LIBRARY_PATH="$libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
exec "$VENV/bin/dikte" "$@"
LAUNCH
chmod 755 "$LAUNCHER"

echo "3/4 Masaüstü kaydı yazılıyor…"
mkdir -p "$APPS" "$ICONS"
# Exec satırı başlatıcıya çevrilir; yol boşluk içerirse diye tırnak içinde yazılır.
sed "s|^Exec=dikte\$|Exec=\"$LAUNCHER\"|" "$ROOT/packaging/linux/dikte.desktop" >"$APPS/dikte.desktop"
chmod 644 "$APPS/dikte.desktop"
install -m 644 "$ROOT/packaging/linux/dikte.png" "$ICONS/dikte.png"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS"
fi

echo "4/4 Model indiriliyor…"
# İndirme hatası kurulumu yarıda kesmemeli; model ilk açılışta da indirilebilir.
MODEL_OK=1
if ! "$VENV/bin/python" "$ROOT/scripts/download_models.py"; then
  MODEL_OK=0
fi

cat <<HINT

Kurulum tamam. Dikte'yi uygulama menüsünden ya da şu komutla başlatın:
  "$LAUNCHER"
Global kısayol için masaüstü ortamınızda özel bir kısayol tanımlayın:
  GNOME : Ayarlar → Klavye → Özel Kısayollar → Komut: "$LAUNCHER" --toggle
  KDE   : Sistem Ayarları → Kısayollar → Özel → Komut: "$LAUNCHER" --toggle
HINT

if [ "$MODEL_OK" -eq 0 ]; then
  echo "Uyarı: Konuşma tanıma modeli indirilemedi (ayrıntı yukarıda)."
  echo "       İnternet bağlantınızı kontrol edip şunu çalıştırın:"
  echo "         \"$VENV/bin/python\" \"$ROOT/scripts/download_models.py\""
  echo "       ya da uygulamada Ayarlar → Hakkında → Durum kontrolü… penceresinden indirin."
fi

# Otomatik yapıştırma için yardımcı araç kontrolü (kurulum yapılmaz, yalnızca uyarılır).
if ! command -v xdotool >/dev/null && ! command -v wtype >/dev/null; then
  echo "Uyarı: xdotool (X11) veya wtype (Wayland) bulunamadı."
  echo "       Bunlar olmadan sonuç metni aktif pencereye yapıştırılamaz, yalnızca panoya yazılır."
fi
