"""Stock-video provider helpers for optional B-roll rendering."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def download_pixabay_broll(
    query: str, destination: Path, api_key: str, *,
    orientation: str = "vertical",
) -> Path:
    """Download one Pixabay video matching a query and orientation."""
    if not api_key.strip():
        raise RuntimeError("PIXABAY_API_KEY is required for B-roll.")
    params = urlencode({
        "key": api_key,
        "q": query[:100],
        "video_type": "film",
        "safesearch": "true",
        "per_page": 20,
    })
    request = Request(
        f"https://pixabay.com/api/videos/?{params}",
        headers={"User-Agent": "ClipperStudio/1.0"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Pixabay B-roll search failed: {exc}") from exc
    hits = data.get("hits", [])
    if not hits:
        raise RuntimeError(f"Pixabay returned no B-roll for '{query}'.")
    candidates = [
        hit for hit in hits
        if _matches_orientation(hit, orientation)
    ] or hits
    files = candidates[0].get("videos", {})
    video = files.get("large") or files.get("medium") or files.get("small")
    if not video or not video.get("url"):
        raise RuntimeError("Pixabay returned no downloadable video file.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urlopen(
            Request(video["url"], headers={"User-Agent": "ClipperStudio/1.0"}),
            timeout=60,
        ) as response, temporary.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        temporary.replace(destination)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Pixabay B-roll download failed: {exc}") from exc
    return destination


def _matches_orientation(hit: dict[str, object], orientation: str) -> bool:
    videos = hit.get("videos")
    if not isinstance(videos, dict):
        return False
    first = next((item for item in videos.values() if isinstance(item, dict)), {})
    width = float(first.get("width", 0) or 0)
    height = float(first.get("height", 0) or 0)
    if not width or not height:
        return False
    return (height >= width) == (orientation == "vertical")
