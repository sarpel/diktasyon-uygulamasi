"""packaging/dikte.ico ve packaging/linux/dikte.png dosyalarını tepsi simgesinden üretir.

Çalıştırma:  .venv/bin/python scripts/make_icon.py   (argüman almaz)
"""

import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from dikte.ui.icons import make_tray_icon

PACKAGING = Path(__file__).resolve().parent.parent / "packaging"
OUT = PACKAGING / "dikte.ico"
OUT_PNG = PACKAGING / "linux" / "dikte.png"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    app = QGuiApplication(sys.argv)  # QPixmap için gerekli
    # En büyük boy ana görüntü; Windows küçük boyları kendisi ölçekler.
    pm = make_tray_icon("idle", size=max(SIZES)).pixmap(max(SIZES))
    if not pm.save(str(OUT), "ICO"):
        print("ICO yazılamadı:", OUT, file=sys.stderr)
        return 1
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    if not pm.save(str(OUT_PNG), "PNG"):
        print("PNG yazılamadı:", OUT_PNG, file=sys.stderr)
        return 1
    print("OK:", OUT, OUT_PNG, pm.size())
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
