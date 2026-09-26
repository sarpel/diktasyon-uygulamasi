"""Pano yardımcıları: geçmişten dışlanan MIME verisi ve önceki panoyu geri yükleme kararı.

Windows'ta pano geçmişi (Win+V) ve bulut panosu, pano sahibinin kayıtlı özel biçimlerle
dışlanmasına izin verir (Microsoft, "Clipboard Formats → Cloud Clipboard and Clipboard
History Formats"). Qt 6 bir Windows pano biçimini
`application/x-qt-windows-mime;value="<Ad>"` MIME türüyle kaydeder
(QWindowsMimeConverter::registerMimeType).
"""

from __future__ import annotations

import struct
import sys

from PySide6.QtCore import QMimeData, QStringListModel
from PySide6.QtGui import QGuiApplication

EXCLUDE_FORMAT = "ExcludeClipboardContentFromMonitorProcessing"
HISTORY_FORMAT = "CanIncludeInClipboardHistory"
CLOUD_FORMAT = "CanUploadToCloudClipboard"

RESTORE_BASE_MS = 300
RESTORE_MAX_MS = 1500
_RESTORE_MS_PER_CHAR = 0.2

_DWORD_ZERO = struct.pack("<I", 0)
_DWORD_ONE = struct.pack("<I", 1)


def windows_mime(format_name: str) -> str:
    """Qt'nin kayıtlı Windows pano biçimi için kullandığı MIME türü."""
    return f'application/x-qt-windows-mime;value="{format_name}"'


def new_mime_data() -> QMimeData:
    """Panoya verilecek boş, C++ tarafında oluşturulmuş bir QMimeData.

    Python'da `QMimeData()` ile kurulan nesne, sanal metotları (formats, retrieveData…)
    Python'a yönlenen bir shiboken alt sınıfıdır. Pano onu sahiplenir ve Qt kapanışta
    (Python yorumlayıcısı kapandıktan sonra) bu metotları çağırır: uygulama panoda dikte
    metni varken çıkarsa süreç segfault ile çöker. `QAbstractItemModel.mimeData` nesneyi
    C++'ta oluşturur; modelin eklediği iç biçim silinip boş nesne döndürülür."""
    model = QStringListModel([""])
    mime = model.mimeData([model.index(0, 0)])
    for fmt in mime.formats():
        mime.removeFormat(fmt)
    return mime


def build_mime(text: str, *, exclude_history: bool, platform: str = sys.platform) -> QMimeData:
    """Panoya konacak veri. Windows'ta `exclude_history` ise dikte metni pano geçmişine,
    bulut panosuna ve pano izleyicilerine düşmesin diye işaret biçimleri eklenir."""
    mime = new_mime_data()
    mime.setText(text)
    if exclude_history and platform == "win32":
        # Bu biçimin içeriği yok sayılır; varlığı yeterlidir.
        mime.setData(windows_mime(EXCLUDE_FORMAT), _DWORD_ONE)
        mime.setData(windows_mime(HISTORY_FORMAT), _DWORD_ZERO)
        mime.setData(windows_mime(CLOUD_FORMAT), _DWORD_ZERO)
    return mime


def copy_text(text: str, *, exclude_history: bool, platform: str = sys.platform) -> None:
    """Metni panoya yazar; tüm kopyalama yolları (sonuç, geçmiş, tray) bunu kullanır ki
    "pano geçmişine alma" ayarı hiçbir yolda atlanmasın."""
    clipboard = QGuiApplication.clipboard()
    clipboard.setMimeData(build_mime(text, exclude_history=exclude_history, platform=platform))


def should_restore(current_text: str | None, pasted_text: str) -> bool:
    """Önceki pano yalnızca pano hâlâ bizim yapıştırdığımız metni tutuyorsa geri yüklenir;
    kullanıcı arada yeni bir şey kopyaladıysa (ya da pano metin değilse) dokunulmaz."""
    return bool(pasted_text) and current_text == pasted_text


def restore_delay_ms(text: str) -> int:
    """Yapıştırmadan sonra önceki panoyu geri yüklemeden önce beklenecek süre (ms).

    Hedef uygulama panoyu yapıştırma tuşundan sonra eşzamansız okur; uzun metinlerde
    (ör. zengin metin editörleri) okuma daha uzun sürdüğünden bekleme biraz uzar."""
    delay = RESTORE_BASE_MS + int(len(text) * _RESTORE_MS_PER_CHAR)
    return min(RESTORE_MAX_MS, delay)
