# -*- mode: python -*-
import os

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

# SPECPATH: bu .spec dosyasının bulunduğu dizin. pyinstaller hangi dizinden
# çalıştırılırsa çalıştırılsın yollar doğru çözülsün diye kullanılır.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas, binaries, hiddenimports = [], [], []
for pkg in ("faster_whisper", "ctranslate2", "ollama", "sounddevice", "av"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
for pkg in ("nvidia.cublas", "nvidia.cudnn"):
    binaries += collect_dynamic_libs(pkg)

a = Analysis(
    [os.path.join(ROOT, "src", "dikte", "__main__.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["dikte.app", "PySide6.QtNetwork"],
    excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore"],
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
