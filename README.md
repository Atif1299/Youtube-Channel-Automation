# YouTube Channel Automation

Desktop app for automated TV-style fitness warm-up videos: **script → stock clips → FFmpeg render → human review → YouTube upload**.

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

Optional: YouTube keys for research and upload.

## Run the app

```powershell
npm start
```

The Electron window opens and starts the Python backend automatically.

### Workflow in the app

1. **Generate** — topic, duration, coach voice or music only
2. **Review** — preview video, approve or reject
3. **Publish** — upload to YouTube (now or scheduled)
4. **Research** — refresh competitor cache (YouTube API)
5. **OAuth** — connect YouTube for uploads

Progress stages show while a job is generating (script → clips → render → TTS → mix).

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
- Rotate any key that was ever committed to git

## License

Private project — see repository owner for usage terms.
