from __future__ import annotations

import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


TRACKS_DIR_NAME = "annotation_tracks"
MANIFEST_FILENAME = "tracks.json"
VALID_AXES = {"target", "query"}
VALID_EXTENSIONS = {
    ".bed": "bed",
    ".wig": "wig",
    ".wiggle": "wig",
}


class AnnotationTrackError(ValueError):
    """Raised when an annotation track cannot be accepted."""


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


def _detect_format(filename: str) -> tuple[str, str]:
    lower_name = filename.lower()
    for suffix, track_format in sorted(VALID_EXTENSIONS.items(), key=lambda item: len(item[0]), reverse=True):
        if lower_name.endswith(suffix):
            return track_format, suffix.lstrip(".")
    raise AnnotationTrackError("Only BED3 (.bed) and Wiggle (.wig, .wiggle) files are supported.")


def _parse_int(value: str, line_no: int, field_name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise AnnotationTrackError(f"Line {line_no}: {field_name} must be an integer.") from exc


def _parse_float(value: str, line_no: int, field_name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise AnnotationTrackError(f"Line {line_no}: {field_name} must be numeric.") from exc
    if not math.isfinite(parsed):
        raise AnnotationTrackError(f"Line {line_no}: {field_name} must be finite.")
    return parsed


def _is_metadata_line(line: str) -> bool:
    lower_line = line.lower()
    return lower_line.startswith("#") or lower_line.startswith("track ") or lower_line.startswith("browser ")


def _validate_bed3(path: Path) -> None:
    data_lines = 0
    with path.open("r", encoding="utf-8", errors="replace") as infile:
        for line_no, raw_line in enumerate(infile, start=1):
            line = raw_line.strip()
            if not line or _is_metadata_line(line):
                continue

            columns = line.split()
            if len(columns) != 3:
                raise AnnotationTrackError(f"Line {line_no}: BED3 files must contain exactly 3 columns.")
            if not columns[0]:
                raise AnnotationTrackError(f"Line {line_no}: chromosome name is required.")

            start = _parse_int(columns[1], line_no, "start")
            end = _parse_int(columns[2], line_no, "end")
            if start < 0:
                raise AnnotationTrackError(f"Line {line_no}: start must be greater than or equal to 0.")
            if end <= start:
                raise AnnotationTrackError(f"Line {line_no}: end must be greater than start.")
            data_lines += 1

    if data_lines == 0:
        raise AnnotationTrackError("BED3 file does not contain any feature.")


def _parse_wig_header(line: str, line_no: int) -> str | None:
    columns = line.split()
    keyword = columns[0].lower()
    if keyword not in {"fixedstep", "variablestep"}:
        return None

    attributes: dict[str, str] = {}
    for column in columns[1:]:
        if "=" not in column:
            raise AnnotationTrackError(f"Line {line_no}: invalid Wiggle header attribute.")
        key, value = column.split("=", 1)
        attributes[key.lower()] = value

    if not attributes.get("chrom"):
        raise AnnotationTrackError(f"Line {line_no}: Wiggle header must define chrom.")

    if keyword == "fixedstep":
        start = _parse_int(attributes.get("start", ""), line_no, "start")
        step = _parse_int(attributes.get("step", ""), line_no, "step")
        if start < 1:
            raise AnnotationTrackError(f"Line {line_no}: fixedStep start must be greater than 0.")
        if step < 1:
            raise AnnotationTrackError(f"Line {line_no}: fixedStep step must be greater than 0.")

    if "span" in attributes and _parse_int(attributes["span"], line_no, "span") < 1:
        raise AnnotationTrackError(f"Line {line_no}: span must be greater than 0.")

    return keyword


def _validate_bedgraph_line(columns: list[str], line_no: int) -> bool:
    if len(columns) != 4:
        return False
    start = _parse_int(columns[1], line_no, "start")
    end = _parse_int(columns[2], line_no, "end")
    _parse_float(columns[3], line_no, "value")
    if start < 0:
        raise AnnotationTrackError(f"Line {line_no}: start must be greater than or equal to 0.")
    if end <= start:
        raise AnnotationTrackError(f"Line {line_no}: end must be greater than start.")
    return True


def _validate_wig(path: Path) -> str:
    data_lines = 0
    mode: str | None = None
    bedgraph = False

    with path.open("r", encoding="utf-8", errors="replace") as infile:
        for line_no, raw_line in enumerate(infile, start=1):
            line = raw_line.strip()
            if not line or _is_metadata_line(line):
                continue

            next_mode = _parse_wig_header(line, line_no)
            if next_mode:
                mode = next_mode
                continue

            columns = line.split()
            if mode == "fixedstep":
                if len(columns) != 1:
                    raise AnnotationTrackError(f"Line {line_no}: fixedStep data must contain exactly 1 value.")
                _parse_float(columns[0], line_no, "value")
            elif mode == "variablestep":
                if len(columns) != 2:
                    raise AnnotationTrackError(f"Line {line_no}: variableStep data must contain position and value.")
                position = _parse_int(columns[0], line_no, "position")
                if position < 1:
                    raise AnnotationTrackError(f"Line {line_no}: position must be greater than 0.")
                _parse_float(columns[1], line_no, "value")
            elif _validate_bedgraph_line(columns, line_no):
                bedgraph = True
            else:
                raise AnnotationTrackError(f"Line {line_no}: Wiggle data must follow a fixedStep or variableStep header.")
            data_lines += 1

    if data_lines == 0:
        raise AnnotationTrackError("Wiggle file does not contain any value.")
    return "bedgraph" if bedgraph and mode is None else "wig"


def _validate_track(path: Path, detected_format: str) -> str:
    if detected_format == "bed":
        _validate_bed3(path)
        return "bed"
    return _validate_wig(path)


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
