# Features

Every feature below is implemented. "Experimental" means functional but intentionally conservative.

## Conversation

- Streaming responses from DeepSeek, OpenRouter or any OpenAI-compatible endpoint.
- Persistent conversation history (searchable, per-conversation).
- Personality, language (`auto` / English / Hinglish) and response length are configurable.
- Agent mode asks the model to state a numbered plan before multi-step work.
- The tool-calling loop executes real tools, checks their results, reports failures and retries where it makes sense.
- Cancellation at any point with **Stop** or **EMERGENCY STOP**.

## Voice

| Capability | Implementation |
|---|---|
| Push-to-talk | Hold the mic button; energy VAD trims silence; release to transcribe |
| Wake word | Optional Vosk grammar (`jarvis`, `hey jarvis`) |
| Speech-to-text | Vosk offline (default) or Google Web Speech |
| Text-to-speech | SAPI5 voices via pyttsx3, interruptible |
| Voice history | Transcripts appear in the chat and are stored as user messages |
| Microphone indicator | Orb waveform, MIC LIVE/OFF, level meter |
| Privacy | No background recording; wake word must be explicitly enabled; audio never leaves the machine with Vosk |

## PC control

| Tool | Risk | What it does |
|---|---|---|
| `open_app` | LOW | Resolve by name/path (aliases, App Paths, Start Menu, PATH), launch, verify process |
| `list_running_apps` | LOW | Running apps with window titles and PIDs |
| `switch_app` | LOW | Bring an open window to the foreground |
| `close_app` | MEDIUM | Terminate a process (unsaved work can be lost) |
| `focus_window` | LOW | Focus by title/process |
| `close_window` | MEDIUM | Send WM_CLOSE to a window |
| `set_window_state` | LOW | Minimize / maximize / restore |
| `get_active_window` | LOW | Title and process of the focused window |
| `read_clipboard` | LOW | Read clipboard text |
| `write_clipboard` | MEDIUM | Replace clipboard text |
| `set_volume` / `get_volume` | LOW | Master volume 0–100 or relative step |
| `set_mute` | LOW | Mute/unmute |
| `media_control` | LOW | playpause, next, prev, stop, volume keys |
| `set_brightness` | LOW | Internal/external display brightness where supported |
| `open_settings` | LOW | Open a `ms-settings:` page |
| `lock_workstation` / `sleep_pc` | MEDIUM | Lock or sleep |
| `power_action` | HIGH | Shutdown, restart, sign out (confirmation every time) |
| `empty_recycle_bin` | HIGH | Empty Recycle Bin (confirmation every time) |

## Files

| Tool | Risk | Notes |
|---|---|---|
| `list_directory` | LOW | Allowed folders only |
| `search_files` | LOW | Name or wildcard, depth-limited |
| `find_duplicate_filenames` | LOW | Groups by filename |
| `read_text_file` | LOW | 2 MB cap, returned as untrusted data |
| `get_file_info` | LOW | Size, dates, type |
| `search_in_documents` | LOW | Line matches across text/code files |
| `create_file` | MEDIUM | Refuses to overwrite unless asked |
| `append_to_file` | MEDIUM | |
| `create_folder` | MEDIUM | |
| `rename_path` / `move_path` / `copy_path` | MEDIUM | Destination must not exist |
| `organize_folder` | MEDIUM | Sorts files into Documents/Images/Video/Audio/Archives/Code/Other |
| `delete_path` | HIGH | Recycle Bin only; never permanent |

Text and code files are read directly. PDF and Office formats are not parsed (no extra native dependencies are installed); convert them to text or use a plugin if you need that. Arbitrary shell/script execution is intentionally not exposed — use workflows or a reviewed plugin instead.

## Screen intelligence

- `capture_screen` — explicit request only; saves PNG; optional monitor selection.
- `capture_window` — captures a specific window by title.
- `describe_screen` — captures and asks a vision-capable model to explain the screen or suggest a click. If the selected model has no vision support, JARVIS says so instead of guessing.

There is no background screenshot loop, no screen recording and no activity monitoring.

## Web

- `web_search` — DuckDuckGo HTML results (title + URL).
- `open_url` — opens the default browser.
- `fetch_page` — readable text extraction, capped at 40,000 characters.
- `download_file` — HTTP(S) only, 25 MB cap, refuses to overwrite.
- All fetched content is wrapped as **untrusted data**; the model is instructed not to follow instructions inside it.

## Memory

- `remember`, `recall`, `list_memory`, `update_memory`, `forget`, `clear_memory`.
- User-controlled: view, edit, delete, clear, or disable in Settings → Memory.
- Secret-shaped text (API keys, passwords, OTPs, long tokens) is rejected at the storage layer.

## Productivity

- Reminders with natural times: `in 20 minutes`, `at 18:30`, `tomorrow at 09:00`, ISO timestamps.
- To-dos with optional due time.
- Quick notes with search.
- Study timer with desktop notification and optional spoken alert.
- Daily summary: open/done tasks, upcoming reminders, recent actions.

## Workflows

- Create named sequences of tool calls (`[{"tool": "...", "args": {...}}]`).
- Run them from the Workflows dialog or by asking JARVIS.
- Each step is risk-checked and confirmed independently; failures are reported without pretending success.
- Stored in SQLite, editable and deletable.

## System dashboard

- CPU %, RAM used/total, disk used/free, battery %/charging, uptime, top memory processes, platform, admin status.
- Refreshes every 2.5 s in the right-hand panel.

## Action history

- Every tool call: tool, risk, success/failure, one-line summary, duration and timestamp.
- Visible in the Tasks panel and persisted in the database.
- Redacted before storage.

## Plugins

Drop a Python module in `%LOCALAPPDATA%\JARVIS\plugins` with:

```python
def register(registry, config):
    ...
```

It is loaded at startup. A broken plugin is logged and skipped; it never prevents JARVIS from starting.

## Emergency stop

Always visible in the title bar. It:

1. Cancels the in-flight model request.
2. Stops speech playback.
3. Stops push-to-talk and wake-word listening.
4. Sets a shared cancellation flag so no further workflow step or tool call runs.
5. Logs the event and notifies you.

## Planned / not included

Deliberately absent because a fake version would be worse than none: cloud account sync, mobile app, email/calendar OAuth integration, browser extension, and a marketplace. The plugin API is the supported path for custom integrations.