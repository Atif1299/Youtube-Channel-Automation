# YouTube Channel Automation

Desktop app for automated TV-style fitness warm-up videos: **script → stock clips (optional Veo) → FFmpeg render → human review → YouTube upload**.

## Architecture

- **Electron** — desktop UI (`electron/`)
- **Python API** — internal backend started automatically (`backend/server.py`)
- **Pipeline** — video generation engine (`pipeline/`)

Run the app with **`npm start`** — no CLI or browser UI required.

## Requirements

- Python 3.11+
- Node.js 18+
- FFmpeg on PATH
- API keys in `.env`

### Install FFmpeg (Windows)

```powershell
winget install --id Gyan.FFmpeg -e
```

## Setup (one time)

```powershell
git clone https://github.com/Atif1299/Youtube-Channel-Automation.git
cd Youtube-Channel-Automation

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
# Edit .env with your keys

npm install
```

Required in `.env`:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Script + TTS |
| `PEXELS_API_KEY` | Stock clips |

Optional:

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Veo 3 (Premium video mode) |
| `YOUTUBE_API_KEY` | Trending research |
| YouTube OAuth env vars | Upload to YouTube |

## Run the app

```powershell
npm start
```

The Electron window opens and starts the Python backend automatically.

## Workflows (two equal paths)

### Path A — Video studio

1. **Create → Quick generate** — topic, duration, coach voice or music only, stock or premium
2. Track progress under **Active**, then **Review**
3. **Approve** or **Reject**
4. **Publish** (now or scheduled) after OAuth in Settings

### Path B — Research

1. **Research** tab — load trending, save ideas
2. **New script draft** — edit scenes if needed
3. **Generate video** — switches to studio with the new job selected
4. Same review → approve → publish flow as Path A

See [TESTING.md](TESTING.md) for a full manual checklist and [AUDIT.md](AUDIT.md) for feature traces and architecture notes.

Progress stages while generating: script → clips → render → TTS → mix.

## Optional assets

- `assets/music/` — MP3 background tracks (for `music_only`)
- `assets/clips/` — local B-roll fallback (filename keyword match)

## Project layout

```
backend/server.py       # Internal FastAPI (auto-started by Electron)
electron/
  main.js               # Desktop shell + backend process manager
  preload.js
  renderer/             # UI (HTML/CSS/JS)
pipeline/               # Core generation logic
config/                 # Brand + niche YAML
prompts/                # LLM prompts
scripts/check_env.py    # Dev-only environment check
assets/output/          # Generated videos (gitignored)
AUDIT.md                # Codebase audit notes
TESTING.md              # Manual test checklist
```

## Dev / debug

Check environment without opening the app:

```powershell
.venv\Scripts\activate
python scripts/check_env.py
```

Backend only (for API debugging):

```powershell
python backend/server.py
```

## Security

- Never commit `.env` or real keys in `.env.example`
- `client_secret.json` and `token.json` are gitignored
- Rotate any key that was ever committed to git

## License

Private project — see repository owner for usage terms.
