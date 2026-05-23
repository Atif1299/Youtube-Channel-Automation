# YouTube Channel Automation

Automated pipeline for TV-style fitness warm-up videos: **script → stock clips → FFmpeg render → human review → YouTube upload**.

Inspired by channels like [TV Fitness Runner](https://www.youtube.com/@TVFitnessRunner), [Interactive Warm-Up Studio](https://www.youtube.com/@InteractiveWarm-UpStudio), and [purplewarm](https://www.youtube.com/@purplewarm).

## Features

- **AI script generation** — OpenAI (default) or Anthropic; structured JSON with scenes, voiceover, and stock queries
- **Stock video clips** — Pexels API with local clip fallback (`assets/clips/`)
- **FFmpeg rendering** — Segment loop/scale, on-screen labels, concat, audio mix
- **Coach voice** — OpenAI TTS narration per scene (`coach_voice` mode)
- **Human review** — Videos land in `pending_review/` before publish
- **YouTube upload** — OAuth + optional scheduled publish
- **Web UI** — Generate, preview, approve, and publish at `http://127.0.0.1:8765`
- **CLI** — Full pipeline from the terminal

## Requirements

- Python 3.11+
- [FFmpeg](https://ffmpeg.org/download.html) on your PATH
- API keys (see below)

### Install FFmpeg (Windows)

```powershell
winget install --id Gyan.FFmpeg -e
```

Restart your terminal, then verify:

```powershell
ffmpeg -version
python main.py check
```

## Quick start

### 1. Clone and install

```powershell
git clone https://github.com/Atif1299/Youtube-Channel-Automation.git
cd Youtube-Channel-Automation
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure secrets

```powershell
copy .env.example .env
```

Edit `.env` and add your keys. **Never commit `.env`.**

| Variable | Required for | Notes |
|----------|--------------|-------|
| `OPENAI_API_KEY` | Script + TTS | Required for generation |
| `PEXELS_API_KEY` | Stock clips | Falls back to `assets/clips/` if missing |
| `YOUTUBE_API_KEY` | Competitor research | Optional |
| `YOUTUBE_CLIENT_ID` / `SECRET` / `REFRESH_TOKEN` | Upload | Run `python main.py auth-youtube` first |

### 3. Add assets (optional)

- **Music** — Drop MP3 files in `assets/music/` (used with `music_only` mode)
- **Local clips** — Drop MP4 files in `assets/clips/` (matched by filename keywords)

Without music files, use **`coach_voice`** for AI narration (default for quick test).

### 4. Verify setup

```powershell
python main.py check
```

You should see `OK` for keys, folders, and FFmpeg.

## Usage

### Web UI (recommended)

```powershell
python main.py ui
```

Open **http://127.0.0.1:8765** — generate, preview, approve, reject, and publish.

### CLI — quick test (1 min)

```powershell
python main.py quick-test
```

Uses `coach_voice` by default. First run may take several minutes (Pexels download + FFmpeg render).

### CLI — full generate

```powershell
python main.py generate --topic "15 min morning desk stretch" --duration 12 --audio coach_voice
python main.py generate --topic "desk stretch" --duration 3 --audio music_only
```

### Review workflow

```powershell
python main.py list --status pending_review
python main.py show <job_id>
python main.py approve <job_id>
python main.py reject <job_id>
```

Approved videos move to `assets/output/approved/` with metadata sidecar.

### YouTube upload

```powershell
python main.py auth-youtube
python main.py publish <job_id>
python main.py publish <job_id> --at 2026-06-01T18:00:00+05:00
```

### Competitor research

```powershell
python main.py research
```

Caches competitor channel data to `data/competitor_cache.json` (requires `YOUTUBE_API_KEY`).

## Pipeline flow

```
Topic + duration
    → OpenAI script (scenes, voiceover, stock queries)
    → Pexels / local clips per scene
    → FFmpeg segment render + concat
    → TTS voiceover (coach_voice) + optional music
    → FFmpeg audio mix → final.mp4
    → pending_review/  (human approve/reject)
    → approved/ + metadata
    → YouTube upload
```

## Project layout

```
config/
  brand.yaml                    # Channel branding, colors
  niches/fitness_warmup.yaml    # Niche settings, resolution
pipeline/                       # Core logic (script, render, publish)
prompts/                        # LLM system prompts
ui/                             # FastAPI web UI
electron/                       # Optional desktop shell
assets/
  clips/                        # Local B-roll fallback
  music/                        # Background tracks
  output/
    pending_review/             # Awaiting approval
    approved/                   # Ready to publish
    rejected/                   # Rejected renders
    .cache/pexels/              # Downloaded stock (gitignored)
    .work/                      # Per-job temp files (gitignored)
data/
  jobs.db                       # Job state (gitignored)
  competitor_cache.json         # Research cache (gitignored)
main.py                         # CLI entry point
.env                            # Secrets (gitignored — copy from .env.example)
```

## Commands reference

| Command | Description |
|---------|-------------|
| `python main.py check` | Verify keys, FFmpeg, folders |
| `python main.py ui` | Start web UI on port 8765 |
| `python main.py quick-test` | 1-minute test video |
| `python main.py generate --topic "..."` | Full generate pipeline |
| `python main.py list [--status STATUS]` | List jobs |
| `python main.py show <job_id>` | Job details (JSON) |
| `python main.py approve <job_id>` | Approve + generate metadata |
| `python main.py reject <job_id>` | Reject video |
| `python main.py publish <job_id>` | Upload to YouTube |
| `python main.py auth-youtube` | OAuth flow for upload |
| `python main.py research` | Refresh competitor cache |

## Audio modes

| Mode | Behavior |
|------|----------|
| `coach_voice` | OpenAI TTS narration per scene; optional background music if MP3s exist |
| `music_only` | Background music only; requires MP3s in `assets/music/` |

## Video providers

Per scene in the generated script JSON:

| Provider | Description |
|----------|-------------|
| `stock` | Pexels + local clips (default) |
| `veo` | Gemini Veo (falls back to stock if unavailable) |

Set `provider: veo` on intro/transition scenes only to control cost.

## Electron desktop (optional)

```powershell
cd electron
npm install
npm start
```

Wraps the web UI in a desktop window.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ffmpeg not found on PATH` | Install FFmpeg (`winget install Gyan.FFmpeg`) and restart terminal |
| UI stuck on **generating** | Generation can take 5–15 min with no progress text; check `assets/output/.work/<job_id>/` for partial files |
| `music_only` silent video | Add MP3s to `assets/music/` or switch to `coach_voice` |
| Push blocked (GitHub secrets) | Never put real keys in `.env.example` — placeholders only |

## Security

- **Never commit** `.env`, `client_secret*.json`, `token.json`, or `credentials.json`
- `.env.example` must contain **placeholders only**
- Rotate any API key that was ever committed or shared in logs

## License

Private project — see repository owner for usage terms.
