# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for J.A.R.V.I.S.

Build with:  powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
Output:      dist\JARVIS\JARVIS.exe
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)
ASSETS = ROOT / "assets"

datas = []
binaries = []
hiddenimports = [
    "jarvis.ui.app",
    "win32timezone",
    "win32com",
    "pythoncom",
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "comtypes",
    "sounddevice",
    "uiautomation",
    "pycaw",
    "screen_brightness_control",
]

for package in ("vosk", "sounddevice", "uiautomation", "pycaw", "screen_brightness_control"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hidden
    except Exception as exc:  # a missing optional package must not break the build
        print(f"warning: could not collect {package}: {exc}")

if ASSETS.exists():
    datas.append((str(ASSETS), "assets"))

icon_path = ASSETS / "jarvis.ico"
icon = str(icon_path) if icon_path.exists() else None

analysis = Analysis(
    [str(ROOT / "src" / "jarvis" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="JARVIS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="JARVIS",
)