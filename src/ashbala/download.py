"""Download playlist tracks and write manifests.

The streaming download / skip-existing / manifest logic is adapted from the
original ``download_playlist.py`` script.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from loguru import logger
from rich.console import Console, Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from ashbala.models import Track
from ashbala.scraper import _session

_console: Console = Console()

def safe_filename(name: str, ext: str) -> str:
    """Return ``name`` sanitized for use as a filename, with ``ext`` appended.

    Characters illegal on common filesystems (``\\ / : * ? " < > |``) are
    replaced with underscores.

    Args:
        name: The desired base name (e.g. a track title).
        ext: The file extension to append, including the leading dot.

    Returns:
        A filesystem-safe filename.
    """
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return f"{cleaned}{ext}"


def _audio_ext(url: str) -> str:
    """Infer an audio file extension from ``url``, defaulting to ``.mp3``."""
    return Path(unquote(urlparse(url).path)).suffix or ".mp3"


def download_tracks(
    tracks: list[Track],
    out_dir: Path,
    session: requests.Session | None = None,
) -> list[Path]:
    """Stream each track to ``out_dir``, skipping files already downloaded.

    A track is skipped when a non-empty file already exists at its destination.
    Failed downloads are logged and their partial file removed, but do not stop
    the remaining tracks.

    Progress is rendered live on the console: an overall tracks bar plus a
    per-file bar with byte counts and transfer speed (transient — it clears
    when the run finishes).

    Args:
        tracks: The tracks to download.
        out_dir: Directory to write audio files into; created if missing.
        session: Session to reuse; a new one is created when ``None``.

    Returns:
        The paths of all files present after the run (newly saved and skipped).
    """
    session = session or _session()
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(tracks)
    saved: list[Path] = []

    overall = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=_console,
    )
    current = Progress(
        TextColumn("  [progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=_console,
    )
    overall_task = overall.add_task("Downloading tracks", total=total)

    with Live(Group(overall, current), console=_console, transient=True):
        for track in tracks:
            dest = out_dir / safe_filename(track.title, _audio_ext(track.audio_url))
            if dest.exists() and dest.stat().st_size > 0:
                logger.info("[{}/{}] skip (already downloaded): {}", track.index, total, dest.name)
                saved.append(dest)
                overall.advance(overall_task)
                continue

            logger.info("[{}/{}] downloading: {}", track.index, total, dest.name)
            try:
                with session.get(track.audio_url, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    size = int(r.headers.get("Content-Length", 0)) or None
                    file_task = current.add_task(dest.name, total=size)
                    try:
                        with dest.open("wb") as fh:
                            for chunk in r.iter_content(chunk_size=1 << 16):
                                fh.write(chunk)
                                current.advance(file_task, len(chunk))
                    finally:
                        current.remove_task(file_task)
                saved.append(dest)
            except requests.RequestException as exc:
                logger.error("FAILED {}: {}", dest.name, exc)
                dest.unlink(missing_ok=True)
            finally:
                overall.advance(overall_task)

    return saved


def write_manifest(tracks: list[Track], out_dir: Path, book_url: str) -> tuple[Path, Path]:
    """Write ``manifest.csv`` and ``manifest.json`` describing the playlist.

    Args:
        tracks: The tracks to record.
        out_dir: Directory to write the manifests into; created if missing.
        book_url: Source book URL, stored in the JSON manifest.

    Returns:
        The ``(csv_path, json_path)`` of the two written manifests.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "manifest.csv"
    json_path = out_dir / "manifest.json"

    rows = [asdict(t) for t in tracks]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["index", "title", "audio_url", "cover_url"])
        writer.writeheader()
        writer.writerows(rows)

    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {"book_url": book_url, "track_count": len(tracks), "tracks": rows},
            fh,
            indent=2,
            ensure_ascii=False,
        )

    logger.info("Manifest written: {} / {}", csv_path.name, json_path.name)
    return csv_path, json_path
