"""Local browser interface for the clipper pipeline."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8765"))
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")
JOBS: dict[str, dict[str, object]] = {}
JOBS_LOCK = threading.Lock()
UPLOADS = ROOT / "uploads"
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}


PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Clipper Studio</title>
  <style>
    :root { color-scheme: dark; --bg:#0f172a; --panel:#1e293b; --muted:#94a3b8; --accent:#38bdf8; }
    * { box-sizing:border-box; } body { margin:0; background:var(--bg); color:#f8fafc; font:15px system-ui,sans-serif; }
    main { max-width:1100px; margin:0 auto; padding:40px 24px; } h1 { margin:0 0 8px; font-size:32px; }
    p { color:var(--muted); } .layout { display:grid; grid-template-columns:340px 1fr; gap:20px; margin-top:28px; }
    section { background:var(--panel); border-radius:14px; padding:22px; } label { display:block; margin:14px 0 6px; color:#cbd5e1; }
    input, select, button { width:100%; border:0; border-radius:8px; padding:11px; font:inherit; }
    input, select { background:#334155; color:#f8fafc; } button { margin-top:20px; background:var(--accent); color:#082f49; font-weight:700; cursor:pointer; }
    button:disabled { opacity:.5; cursor:wait; } .grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .status { margin-top:16px; color:var(--muted); min-height:24px; } progress { width:100%; margin-top:12px; }
    .results { min-height:300px; } .clip { border-top:1px solid #334155; padding:16px 0; }
    .clip:first-child { border-top:0; } .clip strong { display:block; margin-bottom:5px; }
    a { color:var(--accent); } pre { white-space:pre-wrap; color:var(--muted); font-size:12px; max-height:180px; overflow:auto; }
    @media (max-width:760px) { .layout { grid-template-columns:1fr; } }
  </style>
</head>
<body>
<main>
  <h1>Clipper Studio</h1>
  <p>Choose a local video or paste a video URL to create upload-ready clips.</p>
  <div class="layout">
    <section>
      <form id="form">
        <label for="source">Video path or URL</label>
        <input id="source" required placeholder="C:\Videos\podcast.mp4 or https://...">
        <label for="output">Output folder</label>
        <input id="output" value="clips_output">
        <div class="grid">
          <div><label for="num">Clips</label><input id="num" type="number" min="1" value="1"></div>
          <div><label for="model">Model</label><select id="model"><option>tiny</option><option>base</option><option selected>small</option><option>medium</option><option>large-v3</option></select></div>
          <div><label for="min">Min seconds</label><input id="min" type="number" min="1" value="20"></div>
          <div><label for="max">Max seconds</label><input id="max" type="number" min="1" value="55"></div>
        </div>
        <label for="format">Video format</label>
        <select id="format"><option value="vertical">Vertical 9:16</option><option value="original">Original</option></select>
        <label><input id="captions" type="checkbox" checked style="width:auto"> Burn in captions</label>
        <button id="submit" type="submit">Create clips</button>
      </form>
      <div class="status" id="status">Ready</div>
      <progress id="progress" value="0" max="100"></progress>
    </section>
    <section class="results">
      <h2>Rendered clips</h2>
      <div id="results"><p>Your clips will appear here when the job finishes.</p></div>
      <pre id="log"></pre>
    </section>
  </div>
</main>
<script>
const $ = id => document.getElementById(id);
let timer;
function value(id) { return $(id).value; }
function showResults(items) {
  $('results').innerHTML = items.length ? items.map((item, i) =>
    `<div class="clip"><strong>${i + 1}. ${escapeHtml(item.title_suggestion || 'Clip')}</strong>` +
    `${Number(item.duration || 0).toFixed(1)} seconds · score ${Number(item.score || 0).toFixed(2)}<br>` +
    `<a href="${item.url}" target="_blank">Open clip</a></div>`).join('') :
    '<p>No clips were rendered.</p>';
}
function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
async function poll(id) {
  const response = await fetch(`/api/jobs/${id}`);
  const job = await response.json();
  $('status').textContent = job.message;
  $('progress').value = job.progress;
  $('log').textContent = job.log.join('\n');
  if (job.status === 'running') { timer = setTimeout(() => poll(id), 800); return; }
  $('submit').disabled = false;
  if (job.status === 'done') showResults(job.results);
  if (job.status === 'failed') $('status').textContent = `Failed: ${job.message}`;
}
$('form').addEventListener('submit', async event => {
  event.preventDefault();
  $('submit').disabled = true; $('results').innerHTML = ''; $('log').textContent = '';
  const payload = {
    source:value('source'), output:value('output'), num:Number(value('num')),
    minimum:Number(value('min')), maximum:Number(value('max')), model:value('model'),
    format:value('format'), captions:$('captions').checked
  };
  const response = await fetch('/api/jobs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) { $('submit').disabled = false; $('status').textContent = data.error || 'Could not start job'; return; }
  $('status').textContent = 'Starting...'; $('progress').value = 0; poll(data.id);
});
</script>
</body>
</html>"""


def json_response(handler: BaseHTTPRequestHandler, data: object, status: int = 200) -> None:
    body = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def run_job(job_id: str, payload: dict[str, object]) -> None:
    try:
        output = Path(str(payload["output"])).expanduser()
        if not output.is_absolute():
            output = ROOT / output
        command = [
            sys.executable, str(ROOT / "clipper.py"), str(payload["source"]),
            "--out", str(output), "--num", str(payload["num"]),
            "--min", str(payload["minimum"]), "--max", str(payload["maximum"]),
            "--format", str(payload["format"]
                            ), "--model", str(payload["model"]),
        ]
        if not payload["captions"]:
            command.append("--no-captions")
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        with JOBS_LOCK:
            JOBS[job_id]["process"] = process
        assert process.stdout is not None
        log: list[str] = []
        for line in process.stdout:
            line = line.rstrip()
            log.append(line)
            progress = 0
            if line.startswith("[") and "/4]" in line:
                try:
                    progress = (int(line[1]) - 1) * 25
                except ValueError:
                    progress = 0
            with JOBS_LOCK:
                JOBS[job_id].update(
                    log=log[-200:], progress=progress, message=line or "Working...")
        code = process.wait()
        results: list[dict[str, object]] = []
        if code == 0:
            metadata = output / "clips.json"
            results = json.loads(metadata.read_text(encoding="utf-8"))
            for item in results:
                item["url"] = f"/api/jobs/{job_id}/files/{Path(str(item['file'])).name}"
        failure_message = next(
            (line for line in reversed(log) if line.startswith(("Error:", "ERROR:"))),
            "The clipper process failed.",
        )
        with JOBS_LOCK:
            JOBS[job_id].update(
                status="done" if code == 0 else "failed",
                progress=100 if code == 0 else JOBS[job_id]["progress"],
                message="Complete" if code == 0 else failure_message,
                results=results,
            )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        with JOBS_LOCK:
            JOBS[job_id].update(status="failed", message=str(exc), results=[])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            frontend_index = FRONTEND_DIST / "index.html"
            if frontend_index.is_file():
                self._serve_path(frontend_index)
                return
            body = PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path.startswith("/assets/") and FRONTEND_DIST.is_dir():
            candidate = (FRONTEND_DIST /
                         parsed.path.removeprefix("/")).resolve()
            if FRONTEND_DIST.resolve() in candidate.parents and candidate.is_file():
                self._serve_path(candidate)
                return
        parts = parsed.path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
            with JOBS_LOCK:
                job = dict(JOBS.get(parts[2], {}))
            if not job:
                json_response(self, {"error": "Job not found."}, 404)
                return
            job.pop("process", None)
            json_response(self, job)
            return
        if len(parts) == 5 and parts[0:2] == ["api", "jobs"] and parts[3] == "files":
            self._serve_file(parts[2], unquote(parts[4]))
            return
        json_response(self, {"error": "Not found."}, 404)

    def _serve_path(self, path: Path) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)
                         [0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if self.path == "/api/uploads":
            self._handle_upload()
            return
        if self.path != "/api/jobs":
            json_response(self, {"error": "Not found."}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            if not str(payload.get("source", "")).strip():
                raise ValueError("A video path or URL is required.")
            if payload["minimum"] <= 0 or payload["maximum"] < payload["minimum"] or payload["num"] <= 0:
                raise ValueError("Check the clip count and duration range.")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            json_response(self, {"error": str(exc)}, 400)
            return
        job_id = uuid.uuid4().hex
        job = {"status": "running", "progress": 0,
               "message": "Preparing...", "log": [], "results": []}
        with JOBS_LOCK:
            JOBS[job_id] = job
        threading.Thread(target=run_job, args=(
            job_id, payload), daemon=True).start()
        json_response(self, {"id": job_id}, 202)

    def _handle_upload(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        match = re.search(r"boundary=(?:\"([^\"]+)\"|([^;]+))", content_type)
        if not match:
            json_response(
                self, {"error": "A multipart video upload is required."}, 400)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            json_response(
                self, {"error": "Video uploads must be between 1 byte and 500 MB."}, 413)
            return
        body = self.rfile.read(length)
        boundary = (match.group(1) or match.group(2)).encode("utf-8")
        filename = ""
        file_data = b""
        for part in body.split(b"--" + boundary):
            header_end = part.find(b"\r\n\r\n")
            if header_end < 0:
                continue
            headers = part[:header_end].decode("utf-8", errors="replace")
            filename_match = re.search(r'filename="([^"]*)"', headers)
            if filename_match:
                filename = Path(filename_match.group(1)).name
                file_data = part[header_end + 4:].rstrip(b"\r\n")
                if file_data.endswith(b"\r\n"):
                    file_data = file_data[:-2]
                break
        extension = Path(filename).suffix.lower()
        if not file_data or extension not in ALLOWED_UPLOAD_EXTENSIONS:
            json_response(
                self, {"error": "Upload an MP4, MOV, MKV, AVI, M4V, or WebM video."}, 400)
            return
        UPLOADS.mkdir(parents=True, exist_ok=True)
        destination = UPLOADS / f"{uuid.uuid4().hex}{extension}"
        destination.write_bytes(file_data)
        json_response(self, {"source": str(destination)}, 201)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_file(self, job_id: str, filename: str) -> None:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
        if not job:
            json_response(self, {"error": "Job not found."}, 404)
            return
        result = next((item for item in job["results"] if Path(
            str(item["file"])).name == filename), None)
        if not result:
            json_response(self, {"error": "File not found."}, 404)
            return
        path = Path(str(result["file"])).resolve()
        if not path.is_file():
            json_response(self, {"error": "File no longer exists."}, 404)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)
                         [0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"Clipper Studio is running at {url}")
    if os.getenv("OPEN_BROWSER", "true").lower() == "true":
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Clipper Studio.")
        server.server_close()
