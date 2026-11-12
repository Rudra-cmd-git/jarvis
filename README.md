# J.A.R.V.I.S.

A local-first Windows desktop assistant: talk or type, and it can control apps, files, windows, media, the web and your productivity data â€” with explicit permissions, a transparent action log and an emergency stop.

This is an original project. It is not affiliated with Marvel or Disney, ships no copyrighted assets or voice recordings, and does not pretend to be a chatbot mockup: every visible control is wired to a real implementation.

---

## What works today

| Area | Status | Notes |
|---|---|---|
| Text chat + streaming | Working | DeepSeek, OpenRouter or any OpenAI-compatible endpoint |
| Tool-calling agent loop | Working | Multi-step tasks, real verification, retry on tool failure |
| Voice input (push-to-talk) | Working | Vosk offline model; Google Web Speech fallback |
| Spoken replies | Working | Windows SAPI voices, interruptible |
| Wake word | Experimental | Optional, off by default, uses a tiny Vosk grammar |
| App launch / switch / close | Working | Start Menu, App Paths registry, aliases, PATH |
| Window management | Working | Focus, minimize, maximize, restore, close |
| Typing into apps | Working | Clipboard paste (Unicode-safe), key combos |
| Clipboard read/write | Working | |
| Volume, mute, media keys, brightness | Working | pycaw, Windows media keys, DDC/WMI |
| File search, read, create, rename, move, copy | Working | Confined to allowed folders |
| Delete files | Working | Always to Recycle Bin, never permanent, high-risk confirmation |
| Folder organization, duplicate names | Working | |
| Screenshots + screen Q&A | Working | Capture only on explicit request; vision model required for Q&A |
| Web search, page fetch, download | Working | DuckDuckGo, readable text, 25 MB download cap |
| Memory (view/edit/delete/disable) | Working | Secret-shaped text is rejected |
| Reminders, to-dos, notes, study timer | Working | Local SQLite, notifications |
| Workflows (reusable macros) | Working | Stored steps, confirmation per risk level |
| System dashboard | Working | CPU, RAM, disk, battery, uptime, top processes |
| Action history | Working | Every tool call logged with risk and result |
| Plugin loading | Working | Drop a `.py` with `register(registry, config)` into the plugin folder |
| Executable build | Scripted | `scripts\build_exe.ps1` (PyInstaller) |

---

## Requirements

- Windows 10 or 11 (64-bit). Built and verified on Windows 11 build 26300.
- Python 3.11â€“3.13 recommended. Python 3.15 works with the current dependency set; if PyInstaller does not yet support your Python version, build with 3.12/3.13.
- A free or paid API key for **one** provider (DeepSeek, OpenRouter, or a local OpenAI-compatible server). Without a key the UI runs but cannot reason or call tools.
- About 1.5 GB disk for the virtual environment, Qt and the 40 MB speech model.

The application does **not** need administrator rights and never requests elevation.

---

## Quick start

```powershell
cd C:\Users\rudra\OneDrive\Desktop\Jarvis
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_jarvis.ps1
```

You can also double-click `run_jarvis.bat`.

The environment is created at `%LOCALAPPDATA%\JARVIS\venv` (outside the OneDrive-synced project folder). Override it with `JARVIS_VENV`.

### Connect an AI provider

1. Open **Settings â†’ API**.
2. Pick a provider.
3. Paste the key and press **Test connection**.
4. Save.

| Provider | Key URL | Default model | Notes |
|---|---|---|---|
| DeepSeek | https://platform.deepseek.com/api-keys | `deepseek-chat` | Low cost, strong tool calling |
| OpenRouter | https://openrouter.ai/keys | `meta-llama/llama-3.3-70b-instruct:free` | One key, many models, free variants exist |
| Custom | â€” | your model name | Ollama (`http://127.0.0.1:11434/v1`), LM Studio, vLLM, Azure, proxy |

Keys are encrypted with Windows DPAPI and stored in `%APPDATA%\JARVIS\secrets.bin`. You can instead put them in `.env` (copy `.env.example`); environment variables take precedence and are never written to disk by JARVIS.

### Try these

- "Open Chrome, open YouTube, search for a Python tutorial, and open the first result."
- "What is on my screen? Explain this error."
- "Find my project files, then summarize the largest one."
- "Remember that I prefer concise answers in Hinglish."
- "Start a 25 minute study timer."
- "Create a workflow called Morning that opens Chrome and my mail."
- "Show me everything you did in the last hour."

---

## Project layout

```
Jarvis/
  src/jarvis/
    config.py            paths, typed settings, env overrides
    core/                errors, logging, UI event contracts, helpers
    security/            DPAPI secrets, risk policy, confirmations
    ai/                  providers, prompts, streaming client, agent loop
    tools/               70 tools + Windows API wrappers + registry
    memory/              SQLite store (chat, memory, actions, todos, notes)
    automation/          emergency stop, workflow execution, task reporting
    voice/               audio capture, Vosk STT, SAPI TTS, wake word
    ui/                  PySide6 window, orb, panels, dialogs, controller
    plugins/             local plugin loader
  tests/                 53 tests (unit + tool integration)
  docs/                  architecture, configuration, security, features, build
  scripts/               setup, run, build
  jarvis.spec            PyInstaller configuration
```

See `docs/ARCHITECTURE.md` for the full design.

---

## Security model (short version)

- Three risk levels: **LOW** runs immediately, **MEDIUM** asks first, **HIGH** is disabled unless you enable it, and then still asks every time.
- All file tools are confined to folders you add in **Settings â†’ Security** (Desktop, Documents, Downloads and your profile by default).
- Deletes go to the Recycle Bin. There is no permanent-delete tool.
- No keylogger, no clipboard snooping in the background, no hidden commands, no registry edits, no Windows security changes, no elevation.
- Screen capture happens only when you ask.
- Text from web pages, documents, the clipboard and tool output is wrapped as untrusted data before it reaches the model.
- Secrets are rejected by memory and redacted from logs.
- The **EMERGENCY STOP** button cancels the current request, stops speech and listening, and blocks further workflow steps.

Full details: `docs/SECURITY.md`.

---

## Tests

```powershell
$env:PYTHONPATH = "src"
& "$env:LOCALAPPDATA\JARVIS\venv\Scripts\python.exe" -m pytest -q
```

The suite covers configuration, permission decisions, the tool registry, file tools (create/read/move/delete/organize), the agent loop with a fake provider, workflows, memory redaction, productivity tools and app/system tools. Network-dependent and GUI-display-dependent checks are limited or skipped.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "PySide6 is not installed" | Run `scripts\setup.ps1` |
| Chat says no provider configured | Settings â†’ API â†’ add key â†’ Test connection |
| Microphone test hears nothing | Windows Settings â†’ Privacy â†’ Microphone â†’ allow desktop apps; then re-test |
| "Vosk model not downloaded" | Settings â†’ Voice â†’ Download voice model (â‰ˆ40 MB) |
| No spoken replies | Settings â†’ Voice â†’ Test voice; check system volume and SAPI voices |
| Brightness control fails | Some external monitors do not expose DDC/CI; use the monitor's own controls |
| Typing into an app does nothing | The target window must be focused; elevated windows cannot receive input from a non-elevated app |
| High-risk action is blocked | That is intentional. Enable it in Settings â†’ Security if you understand the consequences |
| App closes instantly | Check `%APPDATA%\JARVIS\logs\jarvis.log` |

---

## License

MIT. See `LICENSE`.

J.A.R.V.I.S. is an independent project inspired by the *idea* of a conversational computer assistant. "Iron Man", "J.A.R.V.I.S." and related marks belong to their respective owners; no such assets are included.
