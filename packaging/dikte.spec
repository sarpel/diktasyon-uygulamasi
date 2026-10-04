# -*- mode: python -*-
import importlib.util
import os

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs, collect_submodules

# SPECPATH: bu .spec dosyasının bulunduğu dizin. pyinstaller hangi dizinden
# çalıştırılırsa çalıştırılsın yollar doğru çözülsün diye kullanılır.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas, binaries, hiddenimports = [], [], []
for pkg in (
    "faster_whisper",
    "ctranslate2",
    "ollama",
    "sounddevice",
    "av",
    "openai",  # LLM sağlayıcı extra'ları (llm_tab bu seçenekleri sunuyor)
    "anthropic",
    "google.genai",
):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
# Medya duraklatma (`media` extra'sı, yalnızca Windows): pywinrt (`winrt-*` paketleri).
# `winrt` __init__.py'siz bir ad alanı paketidir ve pyinstaller-hooks-contrib'de kancası
# yoktur; projeksiyonlar (ör. winrt.windows.foundation.collections) çalışma anında
# dinamik içe aktarılır, statik analiz onları göremez. Bu yüzden tüm alt modüller
# (collect_submodules ad alanı paketlerini de gezer) ve _winrt*.pyd yanındaki DLL'ler
# (msvcp140.dll) açıkça toplanır. Kurulu değilse paket onsuz üretilir (özellik devre dışı).
# (find_spec noktalı adda üst paket yoksa ModuleNotFoundError yükseltir; üst ad denetlenir.)
if importlib.util.find_spec("winrt") is not None:
    hiddenimports += collect_submodules("winrt")
    binaries += collect_dynamic_libs("winrt")
else:
    print("UYARI: pywinrt (winrt-*) kurulu değil; kayıtta medyayı duraklatma pakette çalışmayacak.")
# collect_all paketlerin kendi test paketlerini de toplar (ör. google.genai.tests);
# bunlar pytest'i pakete sürükler ve boyutu gereksiz büyütür.
hiddenimports = [m for m in hiddenimports if ".tests" not in m and not m.endswith(".tests")]
for pkg in ("nvidia.cublas", "nvidia.cudnn"):
    libs = collect_dynamic_libs(pkg)
    # collect_dynamic_libs paket kurulu değilse sessizce boş liste döner (yalnızca uyarı
    # loglar, build'i başarısız etmez) — bu STT'nin GPU'da hiç çalışmayacağı bir paket
    # üretiminin fark edilmeden yayınlanması anlamına gelir.
    assert libs, (
        f"{pkg} için hiçbir dinamik kütüphane bulunamadı. "
        f'`pip install -e ".[cuda]"` çalıştırıldı mı?'
    )
    binaries += libs

# Qt standart düğme/diyalog çevirisi (Tamam/İptal/Evet/Hayır, sağ tık menüsü). Paket içinde
# QLibraryInfo'nun çeviri yolu güvenilir değil; app._install_qt_translator bulamazsa
# paketteki "translations" klasörüne bakar. qtbase_tr.qm'nin başka .qm bağımlılığı yoktur.
from PySide6.QtCore import QLibraryInfo  # noqa: E402

_qt_tr = os.path.join(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath), "qtbase_tr.qm")
assert os.path.exists(_qt_tr), f"Qt Türkçe çevirisi bulunamadı: {_qt_tr}"
datas.append((_qt_tr, "translations"))

a = Analysis(
    [os.path.join(ROOT, "src", "dikte", "__main__.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["dikte.app", "PySide6.QtNetwork"],
    excludes=[
        "tkinter",
        "matplotlib",
        "PySide6.QtWebEngineCore",
        "PySide6.Qt3DCore",
        "pytest",
        "_pytest",
        "py",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Dikte",
    console=False,
    icon=os.path.join(SPECPATH, "dikte.ico"),
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Dikte")
