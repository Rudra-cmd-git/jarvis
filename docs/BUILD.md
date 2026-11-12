# Build a standalone executable

## Prerequisites

- The project environment created with `scripts\setup.ps1`.
- PyInstaller 6.x. It must support your Python version. If `pip install pyinstaller` has no compatible wheel for Python 3.15, create a second virtual environment with Python 3.12 or 3.13 and install the project there:

```powershell
py -3.13 -m venv "$env:LOCALAPPDATA\JARVIS\venv313"
$env:JARVIS_VENV = "$env:LOCALAPPDATA\JARVIS\venv313"
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$env:JARVIS_VENV = "$env:LOCALAPPDATA\JARVIS\venv313"
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

## Build

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

Output: `dist\JARVIS\JARVIS.exe` (one folder, not a single file).

PyInstaller bundles:

- Qt (PySide6 Essentials) and its plugins
- Vosk and its native library
- sounddevice/PortAudio
- pywin32 COM DLLs
- pycaw, uiautomation, screen-brightness-control
- the `assets` folder

## Run the build

Copy `dist\JARVIS` anywhere and run `JARVIS.exe`. Configuration, database, logs, models and screenshots are still created under `%APPDATA%\JARVIS` and `%LOCALAPPDATA%\JARVIS`, not inside the program folder, so the app remains portable.

## First run of the executable

1. Settings → API → add a key → Test connection.
2. Settings → Voice → Download voice model (once).
3. Settings → Security → confirm allowed folders.

## Size and startup

- Expected size: roughly 300–500 MB on disk (Qt dominates).
- Startup: 2–5 s on an SSD; first launch is slower because Qt builds caches.
- Memory: about 150–250 MB idle.

To reduce size, delete unused Qt translations and the `PySide6/Qt/translations` folder from `dist\JARVIS\_internal` after building. Do not delete `platforms`, `styles` or `imageformats`.

## Code signing (optional)

Unsigned executables trigger SmartScreen. For personal use, choose **More info → Run anyway**. For distribution, sign with an Authenticode certificate:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a "dist\JARVIS\JARVIS.exe"
```

## Troubleshooting

| Problem | Fix |
|---|---|
| "Failed to execute script" | Rebuild with `--clean`; ensure the venv used for the build matches the Python version |
| Qt platform plugin missing | Keep `_internal\PySide6\plugins\platforms` intact |
| Vosk model not found at runtime | Download it from Settings → Voice; it is stored outside the bundle |
| Microphone blocked | Windows privacy settings; the packaged app has no microphone permission declaration because it is a desktop process, but Windows may still ask |
| Antivirus flags the build | Unsigned PyInstaller output is sometimes flagged; sign the binary or add an exclusion |

## Debug build

Temporarily change `console=False` to `console=True` in `jarvis.spec` to see logs in a console window, or run `dist\JARVIS\JARVIS.exe --log-level DEBUG` (logging level is read from config/env).