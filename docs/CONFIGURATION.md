# Configuration

## Where things live

| Item | Path |
|---|---|
| Settings | `%APPDATA%\JARVIS\config.json` |
| Encrypted API keys | `%APPDATA%\JARVIS\secrets.bin` |
| Database | `%LOCALAPPDATA%\JARVIS\jarvis.db` |
| Logs | `%APPDATA%\JARVIS\logs\jarvis.log` |
| Speech model | `%LOCALAPPDATA%\JARVIS\models\` |
| Screenshots | `%LOCALAPPDATA%\JARVIS\screenshots\` |
| Plugins | `%LOCALAPPDATA%\JARVIS\plugins\` |
| Virtual environment | `%LOCALAPPDATA%\JARVIS\venv\` |

`%APPDATA%` is `C:\Users\<you>\AppData\Roaming`; `%LOCALAPPDATA%` is `C:\Users\<you>\AppData\Local`.

## Environment variables

Copy `.env.example` to `.env` in the project folder. Environment variables override stored secrets, which makes headless/CI use and local servers easier.

| Variable | Meaning |
|---|---|
| `JARVIS_PROVIDER` | `deepseek`, `openrouter`, `custom` |
| `JARVIS_MODEL_NAME` | Model id for the selected provider |
| `JARVIS_BASE_URL` | Base URL for a custom OpenAI-compatible server |
| `DEEPSEEK_API_KEY` | DeepSeek key |
| `OPENROUTER_API_KEY` | OpenRouter key |
| `JARVIS_API_KEY` | Key for a custom endpoint |
| `JARVIS_VOSK_MODEL` | Path to a Vosk model folder |
| `JARVIS_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `JARVIS_VENV` | Override the virtual environment path |

## Providers

### DeepSeek

- Base URL: `https://api.deepseek.com/v1`
- Default model: `deepseek-chat`
- Tools: supported.
- Key: https://platform.deepseek.com/api-keys

### OpenRouter

- Base URL: `https://openrouter.ai/api/v1`
- Default model: `meta-llama/llama-3.3-70b-instruct:free`
- Model names include the vendor prefix. Free variants are rate-limited; paid models are faster and more reliable for long agent loops.
- Key: https://openrouter.ai/keys

### Custom OpenAI-compatible

Examples:

| Server | Base URL |
|---|---|
| Ollama | `http://127.0.0.1:11434/v1` |
| LM Studio | `http://127.0.0.1:1234/v1` |
| vLLM | `http://127.0.0.1:8000/v1` |
| Azure OpenAI | your deployment endpoint |
| llama.cpp server | `http://127.0.0.1:8080/v1` |

A local server usually needs no key; JARVIS sends `not-needed`. Tool calling must be supported by the model/server for agent mode. If it is not, chat still works but tools will not be called.

## Settings reference

### General

| Setting | Default | Effect |
|---|---|---|
| Assistant name | `JARVIS` | Used in the prompt and UI |
| Personality | calm, precise, quietly witty butler | Injected into the system prompt |
| Language | `auto` | `auto` mirrors the user; `english` or `hinglish` forces one |
| Response style | `concise` | `detailed` produces longer explanations |
| Agent mode | off | Tells the model to state a plan before multi-step work |
| Max tool iterations | 8 | Hard cap per request (1–25) |
| Remembered messages | 20 | History sent to the model |

### API

Provider, base URL, model, API key, temperature (0–2), max response tokens, timeout (10–600 s), and **Test connection**. Saving with an empty key field keeps the existing key; **Clear key** deletes it.

### Voice

- **Text to speech**: enable spoken replies, choose a SAPI voice, rate (−50…100), volume (0–100), test.
- **Speech to text**: Vosk (offline) or Google Web Speech (online). The Vosk model is downloaded once (~40 MB) with **Download voice model**.
- **Microphone**: test records three seconds and transcribes it.
- **Push-to-talk**: hold the mic button or the GUI shortcut; release to send.
- **Wake word**: optional, off by default. While enabled, a small Vosk grammar listens for the word; detection records for up to six seconds. Audio is never stored or uploaded.

### Security

- Ask before medium-risk actions (default on).
- Allow high-risk actions after confirmation (default off).
- Allowed folders (default: your profile, Desktop, Documents, Downloads). Add or remove folders here. File tools refuse paths outside this list.
- The risk matrix is displayed in the dialog.

### Appearance

- Animations on/off.
- Low-spec mode (fewer frames, no glow).
- Accent intensity 30–150%.
- Start minimized to tray.
- Ask before quitting.

## Command line

```powershell
python -m jarvis          # run the app (requires the venv on PATH/PYTHONPATH)
```

The recommended entry points are `scripts\run_jarvis.ps1` and `run_jarvis.bat`, which set `PYTHONPATH` and create the environment if needed.

## Resetting

Close JARVIS, then delete `%APPDATA%\JARVIS\config.json` and `secrets.bin` to reset settings and keys. Delete `jarvis.db` to clear conversations, memory, actions, todos and notes. Deleting `models` forces a fresh speech-model download. The source folder is never modified by these resets.