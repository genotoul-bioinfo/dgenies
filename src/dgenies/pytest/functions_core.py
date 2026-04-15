"""Function-level regression tests split from the monolithic API suite."""

import gzip
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import List

import pytest

import dgenies.lib.functions as functions_module
from dgenies.allowed_extensions import AllowedExtensions
from dgenies.lib.functions import Functions

# This file was split out from src/dgenies/test_dgenies_api.py.


@pytest.mark.parametrize("length", list(range(1, 51)))
def test_random_string_length_and_charset(length: int) -> None:
    """Verify that Functions.random_string produces the correct length and
    only uses alphanumeric characters.

    This parameterised test runs 50 times, once for each length from 1
    through 50.  It asserts that the returned string has the expected
    length and consists solely of ASCII letters or digits.
    """
    s = Functions.random_string(length)
    assert len(s) == length, f"unexpected length for {s!r}"
    assert s.isalnum(), f"string contains non‑alphanumeric characters: {s!r}"


@pytest.mark.parametrize(
    "basename",
    [
        "data.txt",
        "data.fa",
        "sample.txt",
        "sample.fa",
        "abc.ext",
        "file.dat",
        "report.md",
        "image.png",
        "video.mp4",
        "doc.pdf",
        "notes.txt",
        "script.py",
        "index.html",
        "archive.tar",
        "archive.tar",  # duplicate
        "dup.csv",
        "duplicate.fa",
        "duplicate.fa",  # duplicate
        "subject.fasta",
        "subject.fasta",  # duplicate
    ],
)
def test_get_valid_uploaded_filename(tmp_path, basename: str) -> None:
    """Ensure that duplicate filenames are renamed to a unique name.

    For each of the 20 basenames, a file with that name is created in a
    temporary directory.  Functions.get_valid_uploaded_filename is
    then called and the returned name is asserted to differ from the
    original basename and to be unused within the directory.
    """
    existing = tmp_path / basename
    existing.write_text("dummy")

    new_name = Functions.get_valid_uploaded_filename(basename, str(tmp_path))
    assert new_name != basename, f"expected a renamed file for {basename}"
    assert not (tmp_path / new_name).exists(), (
        f"returned name {new_name} already exists"
    )


@pytest.mark.parametrize("_", list(range(10)))
def test_random_job_id_format(_) -> None:
    """Validate the format of randomly generated job identifiers.

    The job identifier should consist of a five character prefix (letters
    and digits), an underscore and a timestamp suffix.  Only basic
    structural properties are asserted here: presence of an underscore
    separator and prefix length.
    """
    job_id = Functions.random_job_id()
    assert "_" in job_id, f"underscore missing in job id {job_id!r}"
    prefix, suffix = job_id.split("_", 1)
    assert len(prefix) == 5, f"unexpected prefix length in {job_id!r}"
    assert suffix.isdigit(), f"suffix should be numeric in {job_id!r}"


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("data.fa", True),
        ("sequence.fasta", True),
        ("reads.fa.gz", True),
        ("genome.fa", True),
        ("invalid.txt", False),
        ("bad.ext", False),
        (".fa", False),
        ("myseq.fa.bz2", False),
        ("fa", False),
        ("unknown.extension", False),
    ],
)
def test_functions_allowed_file(
    monkeypatch: pytest.MonkeyPatch, filename: str, expected: bool
) -> None:
    """Test Functions.allowed_file using a controlled extension mapping.

    Functions.allowed_file defers to AllowedExtensions.get_extensions
    to determine which suffixes are acceptable.  The test patches this
    method so that only fa, fasta and fa.gz are recognised.
    Ten filenames are exercised to cover valid and invalid cases.
    """

    def fake_get_extensions(file_format: str) -> List[str]:
        return ["fa", "fasta", "fa.gz"]

    assert fake_get_extensions("fasta") == ["fa", "fasta", "fa.gz"]
    monkeypatch.setattr(
        AllowedExtensions, "get_extensions", fake_get_extensions, raising=False
    )
    result = Functions.allowed_file(filename, ("fasta",))
    assert result is expected


@pytest.mark.parametrize(
    "fasta,is_sorted,expected",
    [
        ("file1", False, False),
        ("file2.fasta", False, False),
        ("file2.fasta.sorted", False, False),
        ("file3", True, True),
        ("file3.sorted", True, False),
        ("file4.fasta", True, True),
        ("file5.fasta.sorted", True, False),
        ("file6.fa", True, True),
        ("file7.fa.sorted", True, False),
        ("file8.txt", True, True),
    ],
)
def test_do_sort_private(fasta: str, is_sorted: bool, expected: bool) -> None:
    """Exercise the private helper Functions.__get_do_sort.

    The mangled method name _Functions__get_do_sort is invoked
    directly.  Ten combinations of filename and is_sorted flag are
    used to verify that sorting is requested only for sorted jobs and
    suppressed when the filename already ends in .sorted.
    """
    result = Functions._Functions__get_do_sort(fasta, is_sorted)
    assert result is expected


@pytest.mark.parametrize(
    "is_gz", [True, False, True, False, True, False, True, False, True, False]
)
def test_is_gz_file_detection(is_gz: bool) -> None:
    """Check Functions.is_gz_file on gzipped and plain files.

    Ten files are generated on the fly.  When is_gz is True, the
    file is compressed using the gzip module; otherwise it contains
    plain text.  The helper must correctly detect gzipped content based
    on the magic number.
    """
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name
    try:
        if is_gz:
            with gzip.open(tmp_path, "wb") as gz:
                gz.write(b"hello")
        else:
            with open(tmp_path, "wb") as f:
                f.write(b"hello")
        result = Functions.is_gz_file(tmp_path)
        assert result is is_gz
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ---------------------------------------------------------------------------
# API tests
#
# Thirty additional tests drive the high level API functions.  Rather than
# running the full Flask application, each test calls the view functions
# directly.  External dependencies such as allow_upload and
# Functions.random_job_id are patched out to give deterministic
# behaviour.  All API tests return a tuple (response dict, status code)
# where appropriate.


def test_get_readable_size_units():
    # Basic unit conversions for bytes to KiB, MiB and GiB.
    assert Functions.get_readable_size(500) == "500.0 B"
    assert Functions.get_readable_size(1024) == "1.0 KiB"
    assert Functions.get_readable_size(1024**2) == "1.0 MiB"
    assert Functions.get_readable_size(1024**3) == "1.0 GiB"


def test_get_readable_size_kib_base():
    # When using a starting unit of KiB the conversion should scale accordingly.
    assert Functions.get_readable_size(1024, base="KiB") == "1.0 MiB"
    assert Functions.get_readable_size(2048, base="KiB", nb_after_coma=0) == "2 MiB"


def test_get_readable_time_formats():
    # Durations less than one minute remain in seconds.
    assert Functions.get_readable_time(30) == "30 s"
    # Exactly one minute yields minutes and seconds.
    assert Functions.get_readable_time(60) == "1 min 0 s"
    # Complex durations convert to hours, minutes and seconds.
    assert Functions.get_readable_time(3661) == "1 h 1 min 1 s"


def test_get_jobs_and_list_all_jobs(monkeypatch, tmp_path):
    # Prepare a dummy config object exposing an app_data attribute.
    dummy_conf = type("Dummy", (), {})()
    dummy_conf.app_data = str(tmp_path)
    monkeypatch.setattr(Functions, "config", dummy_conf, raising=False)

    # Build a valid job directory containing all required marker files.
    valid = tmp_path / "job1"
    valid.mkdir()
    for fname in ["map.paf", "target.idx", "query.idx", ".valid"]:
        (valid / fname).touch()

    # Build an invalid job missing at least one of the required files.
    invalid = tmp_path / "job2"
    invalid.mkdir()
    for fname in ["map.paf", "target.idx", "query.idx"]:
        (invalid / fname).touch()

    # Only the valid job should be returned.
    assert Functions._get_jobs_list() == ["job1"]

    # Test sorting and gallery removal in standalone mode.
    monkeypatch.setattr(
        Functions, "_get_jobs_list", lambda: ["jobb", "JobA", "gallery"]
    )
    jobs_all = Functions.get_list_all_jobs(mode="standalone")
    assert jobs_all == ["JobA", "jobb"]
    # In webserver mode no jobs are disclosed.
    assert Functions.get_list_all_jobs(mode="webserver") == []


def test_query_fasta_file_exists(tmp_path):
    # Without a .query file nothing is detected.
    assert not Functions.query_fasta_file_exists(str(tmp_path))
    # Create an empty .query pointer and detection should succeed.
    (tmp_path / ".query").write_text("dummy")
    assert Functions.query_fasta_file_exists(str(tmp_path))


def test_has_logs(tmp_path):
    # Initially no logs exist.
    assert not Functions.has_logs(str(tmp_path))
    # After creating logs.txt the helper must return True.
    (tmp_path / "logs.txt").write_text("log data")
    assert Functions.has_logs(str(tmp_path))


def test_is_email_mandatory(monkeypatch):
    import dgenies

    # Running in webserver mode makes email mandatory.
    monkeypatch.setattr(dgenies, "MODE", "webserver")
    assert Functions.is_email_mandatory() is True
    # Standalone mode relaxes the requirement.
    monkeypatch.setattr(dgenies, "MODE", "standalone")
    assert Functions.is_email_mandatory() is False


def test_get_status(monkeypatch, tmp_path):
    # Create a dummy job class exposing id_job, logs and a status() method.
    class DummyJob:
        def __init__(self, id_job, status_dict, logs_path):
            self.id_job = id_job
            self._status = status_dict
            self.logs = logs_path

        def status(self):
            return self._status

    # Prepare a logs file so has_logs evaluates to True.
    logs_path = tmp_path / "jobX" / "logs"
    logs_path.parent.mkdir()
    logs_path.write_text("log")

    # Case: mem_peak present and time less than a minute.
    job1 = DummyJob(
        "job1",
        {
            "status": "running",
            "error": "Err#ID#",
            "mem_peak": 2 * 1024 * 1024,
            "time_elapsed": 45,
        },
        str(logs_path),
    )
    res1 = Functions.get_status(job1)
    assert res1["status"] == "running"
    assert res1["error"] == "Err"
    assert res1["has_logs"] is True
    assert res1["mem_peak"] == "2.0 G"
    assert res1["time_elapsed"] == "45 secs"

    # Case: no mem_peak provided and elapsed time spans minutes.
    job2 = DummyJob(
        "job2",
        {"status": "done", "error": "NoError#ID#", "time_elapsed": 125},
        str(logs_path),
    )
    res2 = Functions.get_status(job2)
    assert res2["mem_peak"] is None
    assert res2["time_elapsed"] == "2 min 5 secs"


def test_is_gz_file(tmp_path):
    # A regular text file must not be identified as gzipped.
    normal = tmp_path / "plain.txt"
    normal.write_text("content")
    assert Functions.is_gz_file(str(normal)) is False

    # Gzipped files are recognised based on their magic header.
    gz = tmp_path / "compressed.gz"
    with gzip.open(gz, "wb") as f:
        f.write(b"data")
    assert Functions.is_gz_file(str(gz)) is True


def test_uncompress_and_compress(monkeypatch, tmp_path):
    # Substitute the xopen function with a simple passthrough to builtin open.
    def fake_xopen(filename, mode="rb", format=None):
        return open(filename, mode)

    monkeypatch.setattr(functions_module, "xopen", fake_xopen, raising=False)

    # Create a plain file to compress.
    src = tmp_path / "test.txt"
    src.write_text("hello world")

    # First compression produces a .gz file alongside the original.
    compressed = Functions.compress(str(src), overwrite=False, remove=False)
    assert os.path.exists(src)
    assert compressed.endswith(".gz")
    assert (tmp_path / os.path.basename(compressed)).exists()

    # Second compression without overwrite yields a prefixed filename.
    compressed2 = Functions.compress(str(src), overwrite=False, remove=False)
    assert compressed2 != compressed
    assert compressed2.endswith(".gz")
    assert (tmp_path / os.path.basename(compressed2)).exists()

    # Uncompress back to the original filename.
    dest = Functions.uncompress(compressed)
    assert os.path.exists(dest)
    assert open(dest).read() == open(str(src)).read()

    # When destination exists another decompression creates a numbered file.
    dest2 = Functions.uncompress(compressed)
    assert dest2 != dest
    assert os.path.exists(dest2)
    assert os.path.basename(dest2).startswith("2_")


def test_read_index(tmp_path):
    # Build a minimal index file with varying line formats.
    index_file = tmp_path / "sample.idx"
    content = """Sample Name!@#
chr1\t1000\t1
chr2\t2000\t0
chr3\t3000
"""  # end of multi-line string
    index_file.write_text(content)
    index, sample_name = Functions.read_index(str(index_file))
    # Spaces are replaced by underscores and invalid characters stripped.
    assert sample_name == "Sample_Name"
    assert index["chr1"]["length"] == 1000
    assert index["chr1"]["to_reverse"] is True
    assert index["chr2"]["length"] == 2000
    assert index["chr2"]["to_reverse"] is False
    assert index["chr3"]["length"] == 3000
    assert index["chr3"]["to_reverse"] is False


def test_functions_allowed_file_ext(monkeypatch):
    # Provide a custom AllowedExtensions with minimal mapping.
    class DummyAE:
        @staticmethod
        def get_formats():
            return {"jobtype": {"query": ["fasta"], "target": ["target-fasta"]}}

        @staticmethod
        def get_extensions(file_format):
            return {
                "fasta": ["fa", "fa.gz"],
                "target-fasta": ["fasta"],
            }[file_format]

    # Replace AllowedExtensions in the functions module with our dummy.
    monkeypatch.setattr(functions_module, "AllowedExtensions", DummyAE, raising=False)

    # Valid extensions for the query role.
    assert Functions.allowed_file_ext("jobtype", "query", "sample.fa") is True
    assert Functions.allowed_file_ext("jobtype", "query", "sample.fa.gz") is True
    # Invalid extensions for the query role.
    assert Functions.allowed_file_ext("jobtype", "query", "sample.fasta") is False
    # Valid extension for the target role.
    assert Functions.allowed_file_ext("jobtype", "target", "sample.fasta") is True
    # Invalid for target role.
    assert Functions.allowed_file_ext("jobtype", "target", "sample.fa") is False


def test_get_fasta_file(tmp_path):
    # Create an unsorted fasta and pointer.
    unsorted = tmp_path / "unsorted.fa"
    unsorted.write_text(">a\nATGC")
    (tmp_path / ".query").write_text("unsorted.fa")

    # With sorted flag false the unsorted file is returned.
    assert Functions.get_fasta_file(str(tmp_path), "query", False) == str(unsorted)

    # Prepare a sorted version and its pointer.
    sorted_fa = tmp_path / "unsorted.sorted"
    sorted_fa.write_text(">a\nATGC")
    (tmp_path / ".query.sorted").write_text("unsorted.fa")
    # Now sorted lookup returns the sorted file.
    assert Functions.get_fasta_file(str(tmp_path), "query", True) == str(sorted_fa)

    # Remove the sorted pointer and expect a fallback: unsorted pointer is read and .sorted file discovered.
    (tmp_path / ".query.sorted").unlink()
    assert Functions.get_fasta_file(str(tmp_path), "query", True) == str(sorted_fa)

    # If pointed file does not exist a FileNotFoundError should be raised.
    (tmp_path / ".query").write_text("missing.fa")
    import pytest as _pytest

    with _pytest.raises(FileNotFoundError):
        Functions.get_fasta_file(str(tmp_path), "query", False)


def test_functions_file_lock_copy_session_and_mail_helpers(monkeypatch, tmp_path):
    import dgenies

    source = tmp_path / "source.txt"
    source.write_text("payload")
    linked = tmp_path / "linked.txt"
    copied = tmp_path / "copied.txt"

    monkeypatch.setattr(
        functions_module.os,
        "link",
        lambda src, dest: shutil.copy(src, dest),
        raising=False,
    )
    Functions.hardlink_or_copy(str(source), str(linked))
    assert linked.read_text() == "payload"

    monkeypatch.setattr(
        functions_module.os,
        "link",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("link disabled")),
        raising=False,
    )
    Functions.hardlink_or_copy(str(source), str(copied))
    assert copied.read_text() == "payload"

    lock_file = tmp_path / "job.lock"
    assert Functions.acquire_file_lock(str(lock_file), stale_after=1) is True
    assert lock_file.exists()
    assert Functions.is_file_lock_active(str(lock_file), stale_after=60) is True
    assert Functions.acquire_file_lock(str(lock_file), stale_after=60) is False

    old_time = lock_file.stat().st_mtime - 3600
    os.utime(lock_file, (old_time, old_time))
    assert Functions.acquire_file_lock(str(lock_file), stale_after=1) is True

    old_time = lock_file.stat().st_mtime - 3600
    os.utime(lock_file, (old_time, old_time))
    assert Functions.is_file_lock_active(str(lock_file), stale_after=1) is False
    assert not lock_file.exists()
    Functions.release_file_lock(str(lock_file))
    Functions.release_file_lock(str(lock_file))

    monkeypatch.setattr(dgenies, "MODE", "standalone", raising=False)
    monkeypatch.setattr(
        dgenies,
        "config_reader",
        SimpleNamespace(upload_folder=str(tmp_path)),
        raising=False,
    )
    generated = iter(["duplicated_session", "fresh_session"])
    monkeypatch.setattr(
        Functions,
        "random_string",
        staticmethod(lambda _size: next(generated)),
        raising=False,
    )
    (tmp_path / "duplicated_session").mkdir()
    assert Functions.create_session() == "fresh_session"

    fake_db = ModuleType("dgenies.database")

    class DummyConnect:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeJobModel:
        id_job = object()

        @staticmethod
        def connect():
            return DummyConnect()

        @staticmethod
        def get(*_args, **_kwargs):
            return SimpleNamespace(email="db@example.org")

    class FakeSessionModel:
        @staticmethod
        def connect():
            return DummyConnect()

        @staticmethod
        def new():
            return "session-from-db"

    fake_db.Job = FakeJobModel
    fake_db.Session = FakeSessionModel
    monkeypatch.setitem(sys.modules, "dgenies.database", fake_db)

    monkeypatch.setattr(dgenies, "MODE", "webserver", raising=False)
    assert Functions.create_session() == "session-from-db"
    assert Functions.get_mail_for_job("job-db") == "db@example.org"


"""
Tests the error branches and edge cases for filesystem utility functions, including locking, extension validation, FASTA discovery, and compression.

Ensure that:
1. File locking mechanisms correctly identify stale locks and handle file access errors during acquisition gracefully.
2. Extension validation logic accurately verifies allowed file types based on job configurations.
3. FASTA file retrieval successfully locates files via pointer/metadata files or returns None when the target is missing.
4. Compression and decompression utilities manage successful operations, idempotency, and runtime failures (e.g., corrupted archives) by returning None.
"""


def test_functions_additional_lock_extension_and_compression_error_branches(
    monkeypatch, tmp_path
):
    lock_file = tmp_path / "stale.lock"
    lock_file.write_text("locked")
    assert Functions.is_file_lock_active(str(lock_file), stale_after=0) is True

    monkeypatch.setattr(
        functions_module.os.path,
        "getmtime",
        lambda _path: (_ for _ in ()).throw(FileNotFoundError("gone")),
        raising=False,
    )
    assert Functions.acquire_file_lock(str(lock_file), stale_after=1) is False
    assert Functions.is_file_lock_active(str(lock_file), stale_after=1) is False

    class LegacyAllowedExtensions:
        def get_formats(self, *_args):
            return ["fa"]

    monkeypatch.setattr(
        functions_module,
        "AllowedExtensions",
        lambda: LegacyAllowedExtensions(),
        raising=False,
    )
    assert Functions.allowed_file_ext("jobtype", "query", "sample.fa") is True

    no_pointer_dir = tmp_path / "no-pointer"
    no_pointer_dir.mkdir()
    assert Functions.get_fasta_file(str(no_pointer_dir), "query", False) is None

    sorted_pointer = tmp_path / "sorted-pointer"
    sorted_pointer.mkdir()
    sorted_ready = sorted_pointer / "query.fa.gz.sorted"
    sorted_ready.write_text(">q\nACGT\n")
    (sorted_pointer / ".query.sorted").write_text(str(sorted_ready))
    assert Functions.get_fasta_file(str(sorted_pointer), "query", True) == str(
        sorted_ready
    )

    source = tmp_path / "source.txt"
    source.write_text("payload")
    gz_path = Functions.compress(str(source), overwrite=True, remove=False)
    assert gz_path is not None
    assert (
        Functions.compress(str(Path(gz_path)), overwrite=True, remove=False) == gz_path
    )

    real_getmtime = functions_module.os.path.getmtime
    existing_output = tmp_path / "source.txt"
    existing_output.write_text("payload")
    monkeypatch.setattr(
        functions_module.os.path,
        "getmtime",
        lambda path: (
            (_ for _ in ()).throw(FileNotFoundError("gone"))
            if path == str(gz_path)
            else real_getmtime(path)
        ),
        raising=False,
    )
    uncompressed = Functions.uncompress(gz_path)
    assert uncompressed is not None
    assert Path(uncompressed).name.startswith("2_")

    monkeypatch.setattr(
        functions_module,
        "xopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("broken gzip")),
        raising=False,
    )
    assert Functions.uncompress(gz_path) is None

    monkeypatch.setattr(
        functions_module,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("broken open")),
        raising=False,
    )
    assert Functions.compress(str(source), overwrite=True, remove=False) is None


"""
Tests utility functions for email notifications, FASTA sorting, file compression workflows, and gallery membership logic.

Ensure that:
1. send_fasta_ready correctly constructs email subjects and bodies containing the appropriate download URLs.
2. sort_fasta accurately reorders sequences based on an index and generates timestamped output files while managing lock files.
3. compress_and_send_mail successfully compresses files and triggers the notification workflow.
4. Gallery retrieval functions correctly format metadata (e.g., memory usage, duration) and handle both existing and missing job records during membership checks.
"""


def test_functions_send_sort_compress_gallery_and_membership_helpers(
    monkeypatch, tmp_path
):
    from peewee import DoesNotExist

    monkeypatch.setattr(
        Functions,
        "config",
        SimpleNamespace(web_url="https://dgenies.example"),
        raising=False,
    )
    monkeypatch.setattr(
        Functions,
        "get_mail_for_job",
        staticmethod(lambda _job_id: "user@example.org"),
        raising=False,
    )

    sent_messages = []

    class DummyMailer:
        def send_mail(self, recipients, subject, message, message_html):
            sent_messages.append((recipients, subject, message, message_html))

    mailer = DummyMailer()
    Functions.send_fasta_ready(mailer, "job-42", "sample", compressed=True)
    assert sent_messages[0][0] == ["user@example.org"]
    assert sent_messages[0][1] == "Job job-42 - Download fasta"
    assert "sample.fasta.gz" in sent_messages[0][2]
    assert "https://dgenies.example" in sent_messages[0][3]

    fasta_file = tmp_path / "input.fasta"
    fasta_file.write_text(">chr1\nAAAA\n>chr2\nATGC\n")
    gz_fasta = Functions.compress(str(fasta_file), overwrite=True, remove=False)
    index_file = tmp_path / "query.idx.sorted"
    index_file.write_text("Sample Name\nchr2\t4\t1\nchr1\t4\t0\n")
    lock_file = tmp_path / "sort.lock"
    lock_file.write_text("")
    dot_file = tmp_path / ".query.sorted"
    send_ready_calls = []

    class FakeNow:
        def strftime(self, _fmt):
            return "20260324010101"

    class FakeDatetime:
        @staticmethod
        def utcnow():
            return FakeNow()

    monkeypatch.setattr(functions_module, "datetime", FakeDatetime, raising=False)
    monkeypatch.setattr(
        Functions,
        "send_fasta_ready",
        staticmethod(
            lambda _mailer, job_name, sample_name, compressed, *_args, **_kwargs: (
                send_ready_calls.append((job_name, sample_name, compressed))
            )
        ),
        raising=False,
    )

    Functions.sort_fasta(
        job_name="job-sort",
        fasta_file=gz_fasta,
        index_file=str(index_file),
        lock_file=str(lock_file),
        compress=True,
        with_date=True,
        dot_file=str(dot_file),
        mailer=mailer,
        mode="webserver",
        overwrite=True,
    )

    output_file = Path(dot_file.read_text())
    assert output_file.name == "20260324010101_Sample_Name.fasta.gz"
    assert not lock_file.exists()
    assert send_ready_calls == [("job-sort", "20260324010101_Sample_Name", True)]
    with gzip.open(output_file, "rt") as handle:
        output = handle.read()
    assert output.index(">chr2") < output.index(">chr1")
    assert "GCAT" in output

    second_lock = tmp_path / "compress.lock"
    second_lock.write_text("")
    second_dot = tmp_path / ".query.gz"
    second_fasta = tmp_path / "sorted-query.fasta"
    second_fasta.write_text(">q\nACGT\n")
    sent_ready_calls = []
    monkeypatch.setattr(
        Functions,
        "send_fasta_ready",
        staticmethod(
            lambda _mailer, job_name, sample_name, compressed, *_args, **_kwargs: (
                sent_ready_calls.append((job_name, sample_name, compressed))
            )
        ),
        raising=False,
    )
    Functions.compress_and_send_mail(
        "job-mail",
        str(second_fasta),
        str(second_lock),
        mailer,
        dot_file=str(second_dot),
        overwrite=True,
    )
    assert not second_lock.exists()
    assert Path(second_dot.read_text()).name == "sorted-query.fasta.gz"
    assert sent_ready_calls == [("job-mail", "sorted-query", True)]

    fake_db = ModuleType("dgenies.database")

    class FakeGalleryQuery(list):
        def where(self, *_args, **_kwargs):
            return self

    class FakeGallery:
        job = object()

        @staticmethod
        def select():
            return FakeGalleryQuery(
                [
                    SimpleNamespace(
                        name="Gallery Item",
                        job=SimpleNamespace(
                            id_job="gallery-job", mem_peak=2048, time_elapsed=65
                        ),
                        picture="gallery.png",
                        query="Query",
                        target="Target",
                    )
                ]
            )

    class FakeJob:
        id_job = object()
        raise_missing = False

        @classmethod
        def get(cls, **_kwargs):
            if cls.raise_missing:
                raise DoesNotExist()
            return SimpleNamespace(id_job="gallery-job")

    fake_db.Gallery = FakeGallery
    fake_db.Job = FakeJob
    monkeypatch.setitem(sys.modules, "dgenies.database", fake_db)

    gallery_items = Functions.get_gallery_items()
    assert gallery_items == [
        {
            "name": "Gallery Item",
            "id_job": "gallery-job",
            "picture": "gallery.png",
            "query": "Query",
            "target": "Target",
            "mem_peak": "2.0 MiB",
            "time_elapsed": "1 min 5 s",
        }
    ]
    assert Functions.is_in_gallery("gallery-job", mode="webserver") is True
    FakeJob.raise_missing = True
    assert Functions.is_in_gallery("missing", mode="webserver") is False
    assert Functions.is_in_gallery("missing", mode="standalone") is False
