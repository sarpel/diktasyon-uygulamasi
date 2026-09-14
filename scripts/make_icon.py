"""packaging/dikte.ico dosyasını ui.icons.make_tray_icon'dan üretir."""

import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from dikte.ui.icons import make_tray_icon

OUT = Path(__file__).resolve().parent.parent / "packaging" / "dikte.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    app = QGuiApplication(sys.argv)  # QPixmap için gerekli
    # En büyük boy ana görüntü; Windows küçük boyları kendisi ölçekler.
    pm = make_tray_icon("idle", size=max(SIZES)).pixmap(max(SIZES))
    if not pm.save(str(OUT), "ICO"):
        print("ICO yazılamadı:", OUT, file=sys.stderr)
        return 1
    print("OK:", OUT, pm.size())
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
