from __future__ import annotations

import math
from pathlib import Path


VALID_EXTENSIONS = {
    ".bed": "bed",
    ".wig": "wig",
    ".wiggle": "wig",
}

class AnnotationTrackError(ValueError):
    """Raised when an annotation track cannot be accepted."""


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

