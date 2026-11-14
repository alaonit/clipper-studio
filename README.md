# clipper

`clipper` is a free, local Python command-line tool that downloads or reads a
long video, finds promising transcript/audio moments, and renders upload-ready
clips for YouTube Shorts, Instagram Reels, and TikTok. It uses no paid APIs.

## Setup

Requirements: Python 3.10+, `ffmpeg` on PATH, and a machine capable of running
the selected Whisper model. Install ffmpeg with one of:

```powershell
winget install Gyan.FFmpeg.Shared
```

```bash
brew install ffmpeg                 # macOS
sudo apt install ffmpeg             # Debian/Ubuntu
```

Then install Python dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Desktop app

Run the native desktop interface from the project folder:

```powershell
python app.py
```

The app wraps the same local pipeline as the CLI. Choose a video file or enter
a URL, configure the clip settings, then double-click a rendered result to
open it in the default video player. `ffmpeg` and the Python dependencies
listed below are still required.

### Browser app

The browser interface is a React/Vite website. Install the frontend packages
once:

```powershell
cd frontend
npm install
```

For development, start the Python API in one PowerShell window:

```powershell
cd ..
python web_app.py
```

Then start the React development site in another:

```powershell
cd frontend
npm run dev
```

Open `http://localhost:5173`. Enter a local video path or URL, choose the clip
settings, and click **Create clips**. The React site runs entirely on your
computer and proxies clip jobs to the local Python API.

The frontend is organized for future growth: API access lives in
`frontend/src/api`, job lifecycle state lives in `frontend/src/hooks`, and
screen sections are reusable components under `frontend/src/components`.
`VITE_API_BASE_URL` can point the website at a separately deployed API; see
`frontend/.env.example`.

To serve the production React build from the Python app:

```powershell
cd frontend
npm run build
cd ..
python web_app.py
```

Then open `http://127.0.0.1:8765`. Press `Ctrl+C` in PowerShell to stop it.

### Deploying the API to Render

The repository includes a `Dockerfile` and `render.yaml` for deploying the
Python API to Render. Create a new Render Blueprint from this repository and
set `ALLOWED_ORIGIN` to your Vercel domain, for example:

```text
https://clipper-studio-five.vercel.app
```

After Render gives you an API URL, add it to the Vercel project as the
`VITE_API_BASE_URL` environment variable and redeploy the frontend. The current
API accepts direct URLs and browser video uploads. Local filesystem paths on
your own computer are not available to a remote Render service. Uploaded files
are stored on the service's temporary disk and should be replaced with
persistent object storage before public use.

### Command line

```bash
python clipper.py "https://www.youtube.com/watch?v=..." --num 8
python clipper.py "https://twitch.tv/videos/..." --out my_clips --min 25 --max 50
python clipper.py "C:\videos\podcast.mp4" --format original --no-captions
python clipper.py URL --cookies-from-browser chrome --model small --crf 18
```

For local YouTube processing, explicitly allow the local backend to read your
browser's cookie database:

```powershell
$env:YTDLP_COOKIES_FROM_BROWSER="chrome"
python web_app.py
```

Use `edge` or another browser name when appropriate. Keep this setting local;
do not configure it on Render or commit cookies to the repository.

The source and audio/transcript cache are stored in `OUT/_work`; metadata is
written to `OUT/clips.json`. YouTube downloads require a current yt-dlp
installation and a JavaScript runtime. The Render image installs Deno and
the yt-dlp EJS challenge scripts automatically. YouTube may still block
requests from cloud datacenter IPs; for those videos, use a direct video URL
or upload the source file instead of relying on YouTube extraction.

| Option | Default | Description |
|---|---:|---|
| `SOURCE` | required | URL or local video path |
| `--out` | `clips_output` | Output folder |
| `--num` | `8` | Maximum number of clips |
| `--min` / `--max` | `20` / `55` | Clip length bounds in seconds |
| `--format` | `vertical` | `vertical` (1080x1920 blurred background) or `original` |
| `--no-captions` | off | Do not burn in captions |
| `--model` | `small` | faster-whisper model |
| `--crf` | `18` | H.264 quality setting |
| `--cookies-from-browser` | none | Browser name passed to yt-dlp |

## How scoring works

Candidate clips begin and end at transcript segment boundaries. The heuristic
combines normalized mean and peak RMS energy, speech rate, hook words and
questions, punctuation, clean sentence endings, speech density, and filler
penalties. It greedily chooses high-scoring clips that do not overlap and have
at least three seconds between them.

Laughter is detected independently from 50 ms RMS-envelope frames. Rhythmic
150–350 ms bursts, envelope depth, and gaps in word coverage are combined;
explicit `haha`, `lol`, `lmao`, `laugh`, and `[laughter]` transcript text is
also recognized. Laughter raises the score, especially when it appears in the
last third, and rendering may extend a clip by up to four seconds to preserve
the reaction.

## Limitations and reminders

This is a heuristic, not a guarantee of virality. Watch every clip before
posting. CPU transcription can be slow, especially with larger models.
Laughter can be missed when it overlaps speech and can be confused with
cheering or other rhythmic sounds. Captions depend on Whisper word timestamps.

Only clip source content you are allowed to use under the campaign's terms, and
follow the Content Rewards rules and each platform's policies.
