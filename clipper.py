"""Find, score, caption, and render short vertical clips from long videos."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import numpy as np


HOOK_WORDS = (
    "wait", "no way", "crazy", "insane", "never", "secret", "actually",
    "listen", "bro", "why", "how", "nobody", "worst", "best",
    "can't believe", "omg", "wtf", "literally", "mistake", "story",
)
FILLER_RE = re.compile(r"^\s*(um|uh|so yeah|and then|anyway)\b", re.I)
LAUGHTER_RE = re.compile(r"\b(haha|hehe|lol|lmao|laugh)\b|\[laughter\]", re.I)
DIRECT_VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}


def run(command: Sequence[str], *, cwd: Path | None = None) -> None:
    """Run a subprocess and raise a useful error when it fails."""
    try:
        subprocess.run(command, cwd=cwd, check=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required command was not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Command failed ({exc.returncode}): {' '.join(command)}") from exc


def download(source: str, work: Path, cookies: str | None) -> Path:
    """Resolve a local source or download a URL with yt-dlp, reusing cached media."""
    path = Path(source).expanduser()
    if path.is_file():
        return path.resolve()
    work.mkdir(parents=True, exist_ok=True)
    cached = next((p for p in work.glob("source.*") if p.suffix.lower() not in {".part", ".json"}), None)
    if cached:
        return cached
    parsed = urlparse(source)
    direct_extension = Path(parsed.path).suffix.lower()
    if parsed.scheme in {"http", "https"} and direct_extension in DIRECT_VIDEO_EXTENSIONS:
        destination = work / f"source{direct_extension}"
        try:
            request = Request(source, headers={"User-Agent": "ClipperStudio/1.0"})
            with urlopen(request, timeout=60) as response, destination.open("wb") as stream:
                shutil.copyfileobj(response, stream)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Direct video download failed: {exc}") from exc
        return destination
    output = str(work / "source.%(ext)s")
    deno = shutil.which("deno")
    node = shutil.which("node")
    js_runtime = ["--js-runtimes", f"deno:{deno}"] if deno else (
        ["--js-runtimes", f"node:{node}"] if node else []
    )
    command = [
        sys.executable, "-m", "yt_dlp", "-f", "bv*+ba/b", "--merge-output-format", "mp4",
        *js_runtime, "--no-playlist", "-o", output,
    ]
    if cookies:
        command.extend(["--cookies-from-browser", cookies])
    command.append(source)
    try:
        run(command)
    except RuntimeError as exc:
        raise RuntimeError(f"Download failed: {exc}") from exc
    cached = next((p for p in work.glob("source.*") if p.suffix.lower() != ".part"), None)
    if not cached:
        raise RuntimeError("Download failed: yt-dlp produced no source video.")
    return cached


def extract_wav(video: Path, wav_path: Path) -> None:
    """Extract mono, 16 kHz PCM audio."""
    if not wav_path.exists():
        run(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav_path)])


def transcribe(video: Path, work: Path, model_name: str) -> list[dict[str, Any]]:
    """Transcribe a video and cache segment and word timestamps."""
    cache = work / "transcript.json"
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        return data["segments"] if isinstance(data, dict) else data
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is required for transcription. Install requirements.txt.") from exc
    model = WhisperModel(model_name, compute_type="int8")
    segments, _ = model.transcribe(
        str(video), word_timestamps=True, vad_filter=True,
    )
    result: list[dict[str, Any]] = []
    for segment in segments:
        words = [
            {"start": float(word.start), "end": float(word.end), "word": word.word}
            for word in (segment.words or [])
            if word.start is not None and word.end is not None
        ]
        result.append({
            "start": float(segment.start), "end": float(segment.end),
            "text": segment.text.strip(), "words": words,
        })
    if not result:
        raise RuntimeError("No speech found in the source video.")
    cache.write_text(json.dumps({"segments": result}, indent=2), encoding="utf-8")
    return result


def audio_samples(wav_path: Path) -> tuple[np.ndarray, int]:
    """Read PCM WAV using only the standard library wave module."""
    with wave.open(str(wav_path), "rb") as wav:
        rate, frames = wav.getframerate(), wav.readframes(wav.getnframes())
        width = wav.getsampwidth()
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(width)
    if dtype is None:
        raise RuntimeError(f"Unsupported WAV sample width: {width}")
    samples = np.frombuffer(frames, dtype=dtype).astype(np.float32)
    if width == 1:
        samples = (samples - 128) / 128
    else:
        samples /= float(2 ** (width * 8 - 1))
    return samples, rate


def energy_track(wav_path: Path, win: float = 0.5) -> tuple[np.ndarray, float]:
    """Return RMS energy for each fixed-size window and its window duration."""
    samples, rate = audio_samples(wav_path)
    size = max(1, int(rate * win))
    values = np.array([
        float(np.sqrt(np.mean(np.square(samples[i:i + size]))))
        for i in range(0, len(samples), size)
    ])
    return values, win


def word_coverage(start: float, end: float, words: Sequence[dict[str, Any]]) -> float:
    """Return the share of a time range covered by word timestamps."""
    covered = sum(max(0.0, min(end, float(w["end"])) - max(start, float(w["start"])))
                 for w in words)
    return min(1.0, covered / max(end - start, 1e-6))


def laughter_track(
    wav_path: Path, segs: Sequence[dict[str, Any]], win: float = 0.5,
) -> np.ndarray:
    """Detect rhythmic, gappy laughter as a 0..1 value for each half-second."""
    samples, rate = audio_samples(wav_path)
    frame_size = max(1, int(rate * 0.05))
    envelope = np.array([
        np.sqrt(np.mean(np.square(samples[i:i + frame_size])))
        for i in range(0, len(samples), frame_size)
    ])
    if len(envelope) == 0:
        return np.zeros(0)
    global_median = float(median(envelope))
    word_list = [w for s in segs for w in s.get("words", [])]
    segment_laughter = [(float(s["start"]), float(s["end"]))
                        for s in segs if LAUGHTER_RE.search(str(s.get("text", "")))]
    windows = max(1, math.ceil(len(samples) / (rate * win)))
    output = np.zeros(windows)
    for index in range(windows):
        start_frame = int(index * win * rate / frame_size)
        center = (index + 0.5) * win
        frames = envelope[start_frame:start_frame + 30]
        if len(frames) < 3 or float(np.mean(frames)) < 1.5 * global_median:
            continue
        centered = frames - np.mean(frames)
        denom = float(np.dot(centered, centered))
        rhythm = 0.0
        if denom > 1e-12:
            for lag in range(3, min(8, len(frames))):
                rhythm = max(rhythm, float(np.dot(centered[:-lag], centered[lag:]) / denom))
        mean = float(np.mean(frames))
        depth = float(np.std(frames) / mean) if mean else 0.0
        speech = word_coverage(center - win / 2, center + win / 2, word_list)
        output[index] = max(0.0, min(1.0, rhythm / 0.4)) * max(0.0, min(1.0, depth / 0.6)) * (0.4 + 0.6 * (1 - speech))
    for index in range(windows):
        start, end = index * win, (index + 1) * win
        if any(start < e and end > s for s, e in segment_laughter):
            output[index] = max(output[index], 0.8)
    return output


def zscore(values: Iterable[float]) -> list[float]:
    """Z-score values, returning zeros for a constant sequence."""
    values = list(values)
    mean = float(np.mean(values)) if values else 0.0
    std = float(np.std(values)) if values else 0.0
    return [(v - mean) / std if std > 1e-9 else 0.0 for v in values]


def score_window(
    start: int, end: int, segs: Sequence[dict[str, Any]], energies: np.ndarray,
    laughter: np.ndarray, energy_z: Sequence[float], peak_z_value: float,
) -> dict[str, Any]:
    """Score one candidate window using speech, energy, hooks, and laughter."""
    first, selected = segs[start], segs[start:end + 1]
    words = [w for s in selected for w in s.get("words", [])]
    duration = float(selected[-1]["end"]) - float(first["start"])
    rates = len(words) / max(duration, 1e-6)
    energy_slice = energies[max(0, int(first["start"] / 0.5)):max(1, math.ceil(float(selected[-1]["end"]) / 0.5))]
    peak_slice = [float(x) for x in energy_slice] or [0.0]
    indices = range(max(0, int(first["start"] / 0.5)), min(len(energy_z), math.ceil(float(selected[-1]["end"]) / 0.5)))
    mean_z = float(np.mean([energy_z[i] for i in indices])) if indices else 0.0
    peak = max(peak_slice)
    text = " ".join(str(s.get("text", "")) for s in selected)
    first_words = " ".join(str(s.get("text", "")) for s in [first]).split()[:14]
    hook = "?" in str(first.get("text", "")) or any(
        phrase in " ".join(first_words).lower() for phrase in HOOK_WORDS
    )
    punctuation = min(1.0, (text.count("!") + text.count("?")) / 4)
    laughter_fraction = float(np.mean([
        laughter[i] > 0.35 for i in indices
    ])) if indices else 0.0
    last_third_start = float(selected[-1]["end"]) - duration / 3
    last_laugh = any(laughter[i] > 0.35 for i in range(
        max(0, int(last_third_start / 0.5)), min(len(laughter), math.ceil(float(selected[-1]["end"]) / 0.5))))
    speech_density = sum(max(0.0, float(s["end"]) - float(s["start"])) for s in selected) / max(duration, 1e-6)
    score = (mean_z + 0.7 * peak_z_value + 1.2 * min(rates / 3, 1.5)
             + (1.0 if hook else 0) + 0.6 * punctuation
             + (0.5 if str(selected[-1].get("text", "")).rstrip().endswith((".", "!", "?")) else 0)
             - (0.8 if FILLER_RE.search(str(first.get("text", ""))) else 0)
             + speech_density + 1.5 * min(laughter_fraction * 5, 1)
             + (0.7 if last_laugh else 0))
    return {
        "start": float(first["start"]), "end": float(selected[-1]["end"]),
        "score": score, "energy": float(np.mean(energy_slice)), "peak": peak,
        "words_per_sec": rates, "hook": bool(hook), "clean_end": str(selected[-1].get("text", "")).rstrip().endswith((".", "!", "?")),
        "laughter": laughter_fraction,
    }


def find_moments(
    segs: Sequence[dict[str, Any]], energies: np.ndarray, laughter: np.ndarray,
    minimum: float, maximum: float, count: int,
) -> list[dict[str, Any]]:
    """Build sentence-boundary candidates and greedily choose non-overlapping clips."""
    if not segs:
        raise RuntimeError("No speech found in the source video.")
    energy_z = zscore(energies)
    raw_candidates: list[tuple[int, int, float]] = []
    for start in range(len(segs)):
        for end in range(start, len(segs)):
            duration = float(segs[end]["end"]) - float(segs[start]["start"])
            if duration > maximum:
                break
            if minimum <= duration <= maximum:
                left = max(0, int(float(segs[start]["start"]) / 0.5))
                right = max(1, math.ceil(float(segs[end]["end"]) / 0.5))
                raw_candidates.append((start, end, float(np.percentile(energies[left:right], 95))))
    peak_z = zscore(item[2] for item in raw_candidates)
    candidates: list[dict[str, Any]] = []
    for (start, end, _), peak_score in zip(raw_candidates, peak_z):
        candidates.append(score_window(start, end, segs, energies, laughter, energy_z, peak_score))
    if not candidates:
        raise RuntimeError("No transcript windows match the requested clip length.")
    chosen: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: item["score"], reverse=True):
        if all(candidate["end"] + 3 <= old["start"] or candidate["start"] >= old["end"] + 3 for old in chosen):
            chosen.append(candidate)
            if len(chosen) == count:
                break
    return sorted(chosen, key=lambda item: item["start"])


def ass_time(seconds: float) -> str:
    """Format seconds for ASS timestamps."""
    centiseconds = max(0, round(seconds * 100))
    h, rem = divmod(centiseconds, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_escape(text: str) -> str:
    """Escape text for ASS dialogue lines."""
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def build_ass(
    segments: Sequence[dict[str, Any]], start: float, end: float, path: Path,
    font_style: str = "HORMOZI",
) -> None:
    """Write timed captions using one of the Studio subtitle styles."""
    styles = {
        "HORMOZI": ("Arial", 84, -1, 8),
        "DEFAULT": ("Montserrat", 72, 0, 4),
        "STORYTELLER": ("Inter", 68, 0, 3),
        "CINEMATIC": ("Bebas Neue", 86, 0, 5),
    }
    font, size, bold, outline = styles.get(font_style.upper(), styles["HORMOZI"])
    words = [w for s in segments for w in s.get("words", [])
             if float(w["end"]) > start and float(w["start"]) < end]
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,{bold},0,0,0,100,100,0,0,1,{outline},2,2,80,80,560,1",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text",
    ]
    for index in range(0, len(words), 3):
        group = words[index:index + 3]
        if not group:
            continue
        group_start = max(start, float(group[0]["start"]))
        group_end = min(end, float(group[-1]["end"]) + 0.35)
        text = ass_escape(" ".join(str(w["word"]).strip().upper() for w in group))
        lines.append(f"Dialogue: 0,{ass_time(group_start - start)},{ass_time(group_end - start)},Default,,0,0,,{text}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def slug(text: str) -> str:
    """Make a short filesystem-safe slug."""
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (value[:60] or "clip")


def cut_clips(
    video: Path, out: Path, moments: list[dict[str, Any]], segments: Sequence[dict[str, Any]],
    aspect_ratio: str, captions: bool, crf: int, laughter: np.ndarray,
    font_style: str, bgm: Path | None = None,
) -> list[dict[str, Any]]:
    """Render selected clips and return JSON metadata."""
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for number, moment in enumerate(moments, 1):
        start, end = moment["start"], moment["end"]
        while end < moment["end"] + 4 and int(end / 0.5) < len(laughter) and laughter[int(end / 0.5)] > 0.35:
            end += 0.5
        end = min(end, moment["end"] + 4)
        if number < len(moments):
            end = min(end, float(moments[number]["start"]))
        first_text = str(next((s.get("text", "") for s in segments if s["start"] == moment["start"]), "clip"))
        filename = f"clip_{number:02d}_{slug(first_text)}.mp4"
        target = out / filename
        ass_path = out / f".clip_{number:02d}.ass"
        filter_parts: list[str] = []
        dimensions = {
            "9:16": (1080, 1920),
            "16:9": (1920, 1080),
            "1:1": (1080, 1080),
            "3:4": (1080, 1440),
            "4:5": (1080, 1350),
        }.get(aspect_ratio)
        if dimensions:
            width, height = dimensions
            filter_parts.append(
                f"[0:v]split=2[bg][fg];[bg]scale={width}:{height}:"
                f"force_original_aspect_ratio=increase,crop={width}:{height},"
                f"boxblur=20:10[blur];[fg]scale={width}:{height}:"
                f"force_original_aspect_ratio=decrease[sharp];"
                "[blur][sharp]overlay=(W-w)/2:(H-h)/2"
            )
        if captions:
            build_ass(segments, start, end, ass_path, font_style)
            filter_parts.append(f"ass={ass_path.name}")
        command = ["ffmpeg", "-y", "-ss", str(start), "-i", str(video), "-t", str(end - start)]
        if bgm:
            command.extend(["-stream_loop", "-1", "-i", str(bgm)])
        if filter_parts:
            command += ["-vf", ",".join(filter_parts), "-c:v", "libx264"]
        else:
            command += ["-c:v", "libx264"]
        command += ["-crf", str(crf), "-preset", "medium", "-pix_fmt", "yuv420p"]
        if bgm:
            command += [
                "-filter_complex",
                "[1:a]volume=0.12[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[audio]",
                "-map", "0:v", "-map", "[audio]",
            ]
        command += ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(target)]
        run(command, cwd=out)
        thumbnail = out / f"{target.stem}.jpg"
        run([
            "ffmpeg", "-y", "-ss", "0", "-i", str(target), "-frames:v", "1",
            "-q:v", "3", str(thumbnail),
        ], cwd=out)
        if ass_path.exists():
            ass_path.unlink()
        item = dict(moment)
        item.update({"file": str(target), "title_suggestion": first_text[:100],
                     "end": end, "duration": end - start,
                     "thumbnail": str(thumbnail)})
        results.append(item)
    return results


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Create viral short clips from a video.")
    parser.add_argument("source")
    parser.add_argument("--out", default="clips_output", type=Path)
    parser.add_argument("--num", type=int, default=8)
    parser.add_argument("--min", dest="minimum", type=float, default=20)
    parser.add_argument("--max", dest="maximum", type=float, default=55)
    parser.add_argument("--format", choices=("vertical", "original"), default="vertical")
    parser.add_argument("--aspect-ratio", choices=("9:16", "16:9", "1:1", "3:4", "4:5"))
    parser.add_argument("--font-style", choices=("HORMOZI", "DEFAULT", "STORYTELLER", "CINEMATIC"), default="HORMOZI")
    parser.add_argument("--bgm", type=Path)
    parser.add_argument("--no-captions", action="store_true")
    parser.add_argument("--model", default="small")
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--cookies-from-browser")
    args = parser.parse_args(argv)
    if shutil.which("ffmpeg") is None:
        print("Error: ffmpeg is not installed or not on PATH. Install it and try again.", file=sys.stderr)
        return 2
    if args.minimum <= 0 or args.maximum < args.minimum or args.num <= 0:
        print("Error: --min/--max/--num values are invalid.", file=sys.stderr)
        return 2
    out = args.out.resolve()
    work = out / "_work"
    work.mkdir(parents=True, exist_ok=True)
    try:
        print("[1/4] Downloading source...")
        video = download(args.source, work, args.cookies_from_browser)
        print("[2/4] Transcribing...")
        wav = work / "audio.wav"
        extract_wav(video, wav)
        segments = transcribe(video, work, args.model)
        energies, _ = energy_track(wav)
        laughter = laughter_track(wav, segments)
        print("[3/4] Finding viral moments...")
        moments = find_moments(segments, energies, laughter, args.minimum, args.maximum, args.num)
        print("[4/4] Rendering clips...")
        aspect_ratio = args.aspect_ratio or ("9:16" if args.format == "vertical" else "")
        results = cut_clips(
            video, out, moments, segments, aspect_ratio, not args.no_captions,
            args.crf, laughter, args.font_style, args.bgm,
        )
        (out / "clips.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Done: rendered {len(results)} clip(s) to {out}")
        return 0
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
