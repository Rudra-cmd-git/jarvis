# Architecture

## Design rules

1. **Backend has no Qt dependency.** Tools, AI, storage and automation are pure Python and testable headlessly.
2. **Tools are data.** Each tool is a `ToolSpec`: a JSON schema plus a callable. The same schema is sent to the model, so what it sees is exactly what runs.
3. **Every action is verified.** A tool returns a real result; the engine never claims success on its own.
4. **One event loop for I/O.** The UI thread stays responsive; asyncio runs on a dedicated thread and talks to Qt through signals.
5. **Least privilege.** File tools are path-guarded; high-risk tools are disabled by default.

## Layers

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ UI (PySide6, GUI thread) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ MainWindow Â· Orb Â· ChatPanel Â· InputBar Â· StatusPanel Â· TaskPanel Â· Dialogs      â”‚
â”‚        â”‚ signals (queued)                        â–² callbacks                      â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
         â”‚                                          â”‚
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ AppController (asyncio loop on jarvis-backend thread)                             â”‚
â”‚  â”œâ”€ AIEngine â”€â”€ ChatClient â”€â”€â–º provider (DeepSeek / OpenRouter / OpenAI-compatible)â”‚
â”‚  â”œâ”€ PermissionPolicy â”€â”€â–º ConfirmDialog (via UiBridge)                             â”‚
â”‚  â”œâ”€ ToolRegistry â”€â”€â–º tools/* (apps, files, system, web, screen, productivityâ€¦)    â”‚
â”‚  â”œâ”€ Store (SQLite)  Â·  SecretStore (DPAPI)  Â·  AutomationController               â”‚
â”‚  â””â”€ SpeechToText Â· TextToSpeech Â· WakeWordListener                                 â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

## Request flow

1. `InputBar` emits text (or a push-to-talk transcript).
2. `AppController.send()` persists the user message and submits `_process()` to the asyncio loop.
3. `AIEngine.chat()` builds the system prompt (personality, memory, environment, tool list), sends the history and streams the response.
4. If the model returns `tool_calls`, the engine validates arguments, asks `PermissionPolicy`, executes the tool, appends the real result and loops.
5. Tokens are emitted to the UI as they arrive; the final assistant message is persisted.
6. If speech is enabled, the reply is spoken; `stop()` or **EMERGENCY STOP** cancels both generation and speech.

## Tool execution

```
LLM tool_call
  â†’ JSON parse (with repair for common model mistakes)
  â†’ schema validation (required fields, types, additionalProperties)
  â†’ risk classification (LOW / MEDIUM / HIGH)
  â†’ permission decision
      LOW   â†’ run
      MEDIUMâ†’ confirmation dialog (allow once / allow always / deny)
      HIGH  â†’ refused unless enabled, then confirmation every time
  â†’ run in asyncio (async tools) or a worker thread (sync tools), with timeout
  â†’ audit log + UI action event
  â†’ result text appended to the conversation
```

## Persistence

SQLite at `%LOCALAPPDATA%\JARVIS\jarvis.db` (WAL mode, one locked connection):

- `conversations`, `messages`
- `memories` (secret-shaped content rejected)
- `actions` (risk, ok, summary, duration)
- `todos`, `reminders`, `notes`, `workflows`, `timers`

Settings: `%APPDATA%\JARVIS\config.json`.
Secrets: `%APPDATA%\JARVIS\secrets.bin` (DPAPI-wrapped, base64).
Logs: `%APPDATA%\JARVIS\logs\jarvis.log` (rotating, 2 MB Ã— 3).
Screenshots: `%LOCALAPPDATA%\JARVIS\screenshots`.

## Extending

### Add a tool

```python
from jarvis.security.permissions import Risk
from jarvis.tools.registry import ToolSpec

def _my_tool(ctx, value: int) -> str:
    return f"saw {value}"

def build_specs():
    return [ToolSpec(
        name="my_tool",
        description="One sentence the model will read.",
        parameters={"type": "object", "properties": {"value": {"type": "integer"}},
                    "required": ["value"], "additionalProperties": False},
        handler=_my_tool,
        risk=Risk.LOW,
        category="custom",
    )]
```

Register it in `jarvis/tools/builtin.py` (built-in) or expose it from a plugin.

### Add a plugin

Create `%APPDATA%\JARVIS\plugins\my_plugin.py`:

```python
def register(registry, config):
    registry.register(my_tool_spec)
```

Plugins run with the same OS privileges as JARVIS. Only install code you trust.

### Add a provider

`jarvis/ai/providers.py` is a table of `ProviderPreset`s. Add one entry; the client, settings UI and validation pick it up automatically because all providers speak the OpenAI Chat Completions protocol.

## Why this stack

| Concern | Choice | Reason |
|---|---|---|
| UI | PySide6 Essentials | GPU-composited, smooth animation, no browser runtime; ~150 MB |
| AI | `openai` SDK | One protocol covers DeepSeek, OpenRouter and local servers |
| Windows control | pywin32 + `uiautomation` + ctypes | Stable APIs (window handles, App Paths, SendInput) instead of screen coordinates |
| Volume | pycaw (Core Audio) | Per-app and master volume via COM |
| Clipboard | win32clipboard | Unicode-safe |
| Files | pathlib + `SHFileOperationW` | Recycle Bin semantics, no shell parsing |
| Screenshots | mss | Fast, no Pillow requirement |
| STT | Vosk | Offline, free, 40 MB; Google Web Speech fallback |
| TTS | pyttsx3 / SAPI5 | Offline, uses installed Windows voices |
| Storage | sqlite3 | Zero-config, transactional enough for a desktop app |
| Secrets | DPAPI via ctypes | No key material on disk, tied to the Windows account |
| Tests | pytest | No GUI needed for 95% of the logic |
| Packaging | PyInstaller | One-folder distribution |

## Known limits

- Wake word is a small-grammar Vosk recognizer, not a commercial wake-word engine; false accepts are possible while enabled.
- The free Vosk English model is weaker than cloud ASR on accented Hinglish. Choose the Google backend for better Hinglish, or install a Hindi Vosk model and point `JARVIS_VOSK_MODEL`/the models folder at it.
- Vision Q&A depends on the selected model supporting image input. If it does not, JARVIS saves the screenshot and says so.
- UIPI prevents typing into elevated windows from a non-elevated process. JARVIS intentionally does not elevate.
- PyInstaller support depends on the Python version; see `docs/BUILD.md`.
