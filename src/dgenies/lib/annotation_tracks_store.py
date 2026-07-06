from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .annotation_tracks_validation import AnnotationTrackError, _detect_format, _validate_track


TRACKS_DIR_NAME = "annotation_tracks"
MANIFEST_FILENAME = "tracks.json"
VALID_AXES = {"target", "query"}

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_job_dir(app_data: str, job_id: str) -> Path:
    if not re.match(r"^[A-Za-z0-9_.-]+$", job_id):
        raise FileNotFoundError(job_id)

    root = Path(app_data).resolve()
    job_dir = (root / job_id).resolve()
    if root not in job_dir.parents or not job_dir.is_dir():
        raise FileNotFoundError(job_id)
    return job_dir


def _tracks_dir(job_dir: Path) -> Path:
    path = job_dir / TRACKS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _manifest_path(job_dir: Path) -> Path:
    return _tracks_dir(job_dir) / MANIFEST_FILENAME


def _load_manifest(job_dir: Path) -> list[dict[str, Any]]:
    manifest = _manifest_path(job_dir)
    if not manifest.exists():
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)]


def _save_manifest(job_dir: Path, tracks: list[dict[str, Any]]) -> None:
    manifest = _manifest_path(job_dir)
    tmp_manifest = manifest.with_suffix(".json.tmp")
    tmp_manifest.write_text(json.dumps(tracks, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp_manifest, manifest)


def _public_track(job_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "job_id": job_id,
        "axis": entry["axis"],
        "format": entry["format"],
        "name": entry["name"],
        "filename": entry["filename"],
        "size": entry["size"],
        "created_at": entry["created_at"],
    }


class AnnotationTracks:
    """Persistent BED/Wiggle tracks associated with a D-Genies job."""

    def __init__(self, app_data: str):
        self.app_data = app_data

    def list_tracks(self, job_id: str) -> list[dict[str, Any]]:
        job_dir = _safe_job_dir(self.app_data, job_id)
        entries = _load_manifest(job_dir)
        tracks_dir = _tracks_dir(job_dir)
        return [
            _public_track(job_id, entry)
            for entry in entries
            if isinstance(entry.get("id"), str)
            and isinstance(entry.get("stored_filename"), str)
            and (tracks_dir / entry["stored_filename"]).is_file()
        ]

    def save_track(self, job_id: str, axis: str, uploaded_file: FileStorage, name: str | None = None) -> dict[str, Any]:
        if axis not in VALID_AXES:
            raise AnnotationTrackError("Track axis must be either target or query.")
        if not uploaded_file or not uploaded_file.filename:
            raise AnnotationTrackError("No annotation file was provided.")

        original_filename = Path(uploaded_file.filename).name
        detected_format, extension = _detect_format(original_filename)
        job_dir = _safe_job_dir(self.app_data, job_id)
        tracks_dir = _tracks_dir(job_dir)
        track_id = uuid.uuid4().hex
        safe_original = secure_filename(original_filename) or f"track.{extension}"
        stored_filename = f"{track_id}.{extension}"
        stored_path = tracks_dir / stored_filename

        uploaded_file.save(stored_path)
        try:
            if stored_path.stat().st_size == 0:
                raise AnnotationTrackError("Annotation file is empty.")
            actual_format = _validate_track(stored_path, detected_format)
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise

        display_name = (name or Path(original_filename).stem).strip() or safe_original
        entry = {
            "id": track_id,
            "axis": axis,
            "format": actual_format,
            "name": display_name[:120],
            "filename": safe_original,
            "stored_filename": stored_filename,
            "size": stored_path.stat().st_size,
            "created_at": _utc_now(),
        }

        entries = _load_manifest(job_dir)
        entries.append(entry)
        _save_manifest(job_dir, entries)
        return _public_track(job_id, entry)

    def get_track_file(self, job_id: str, track_id: str) -> tuple[Path, dict[str, Any]]:
        if not re.match(r"^[A-Fa-f0-9]{32}$", track_id):
            raise FileNotFoundError(track_id)

        job_dir = _safe_job_dir(self.app_data, job_id)
        tracks_dir = _tracks_dir(job_dir)
        for entry in _load_manifest(job_dir):
            if entry.get("id") != track_id or not isinstance(entry.get("stored_filename"), str):
                continue
            stored_path = tracks_dir / entry["stored_filename"]
            if not stored_path.is_file():
                raise FileNotFoundError(track_id)
            return stored_path, _public_track(job_id, entry)
        raise FileNotFoundError(track_id)
