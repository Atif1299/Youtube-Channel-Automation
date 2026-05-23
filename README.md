<<<<<<< HEAD
# YouTube Automations — Fitness Warm-Up Pipeline

Automated pipeline for TV-style fitness warm-up videos: script → stock clips → FFmpeg render → human review → YouTube upload.

Inspired by channels like [TV Fitness Runner](https://www.youtube.com/@TVFitnessRunner), [Interactive Warm-Up Studio](https://www.youtube.com/@InteractiveWarm-UpStudio), and [purplewarm](https://www.youtube.com/@purplewarm).

## Quick start

### 1. Install dependencies

```bash
cd "d:\Projects\Youtube Automations"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Install [FFmpeg](https://ffmpeg.org/download.html) and ensure `ffmpeg` is on your PATH.

### 2. Configure secrets

Copy `.env.example` to `.env` and fill in your keys:

```bash
copy .env.example .env
```

Required for generation:
- `OPENAI_API_KEY`
- `PEXELS_API_KEY`

Optional:
- `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`
- `YOUTUBE_API_KEY` (competitor research)
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` (upload)

### 3. Add assets (optional)

- Drop MP3 files in `assets/music/`
- Drop MP4 clips in `assets/clips/` (matched by filename keywords)

### 4. Verify setup

```bash
python main.py check
```

### 4b. Web UI (no CMD commands)

```bash
python main.py ui
```

Open **http://127.0.0.1:8765** — generate, preview video, approve, publish.

**Electron desktop window (optional):**

```bash
cd electron
npm install
npm start
```

### 5. Generate a video

```bash
python main.py quick-test
```

Or longer:
```bash
python main.py research
python main.py generate --topic "desk stretch" --duration 1 --audio coach_voice
```

Output lands in `assets/output/pending_review/`.

### 6. Review workflow

```bash
python main.py list --status pending_review
python main.py approve <job_id>
python main.py reject <job_id>
```

After approve, metadata is saved next to the video in `assets/output/approved/`.

### 7. YouTube upload

```bash
python main.py auth-youtube
python main.py publish <job_id>
python main.py publish <job_id> --at 2026-06-01T18:00:00+05:00
```

## Project layout

```
config/brand.yaml              # Channel branding
config/niches/fitness_warmup.yaml
pipeline/                      # Core logic
assets/clips/                  # Local B-roll fallback
assets/music/                  # Background tracks
assets/output/pending_review/  # Awaiting your approval
assets/output/approved/        # Ready to publish
data/jobs.db                   # Job state (gitignored)
data/competitor_cache.json     # YouTube research cache
```

## Swappable video providers

Per scene in the generated script JSON:

- `stock` — Pexels + local clips (default)
- `veo` — Gemini Veo (falls back to stock if unavailable)

Set `provider: veo` on intro/transition scenes only to control cost.

## Commands

| Command | Description |
|---------|-------------|
| `python main.py check` | Verify keys, ffmpeg, folders |
| `python main.py research` | Cache competitor titles (YouTube API) |
| `python main.py generate --topic "..."` | Full generate pipeline |
| `python main.py list` | List jobs |
| `python main.py approve <id>` | Approve + generate metadata |
| `python main.py publish <id>` | Upload to YouTube |

## Security

- Never commit `.env` or API keys
- Rotate any key that was shared in chat logs
=======
# Youtube-Channel-Automation
>>>>>>> 3d82ee9bf26ff8e5d3cd5466c45be6c2af750b6a
