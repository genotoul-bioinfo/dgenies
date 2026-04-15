"""Tests for job helper functions and workflows."""

import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from dgenies.lib.datafile import DataFile
from dgenies.lib.exceptions import DGeniesExampleInvalid, DGeniesExampleNotAvailable, DGeniesMissingJobError
from dgenies.pytest.helpers import TESTS_DATA_DIR, TESTS_ENSEMBL_DIR, _setup_api_runtime

# This file was split out from src/dgenies/test_dgenies_api.py.

"""
Tests the job_helpers logic for DataFile instantiation and job configuration transformation using real file system fixtures.

Ensure that:
1. create_datafile correctly handles local files by sanitizing filenames (e.g., removing spaces) and placing them within the appropriate session directory.
2. The utility properly distinguishes between "example" URIs (mapping them to known fixture paths) and "url" types, while raising specific exceptions for invalid or missing example references.
3. update_files accurately transforms job dictionaries by converting string-based identifiers into structured DataFile objects.
4. Redundant metadata keys (like query_type or target_type) are cleaned up after the transformation process is complete.
"""
def test_job_helpers_create_datafile_and_update_files_use_real_fixtures(monkeypatch, tmp_path):
    import dgenies
    import dgenies.job_helpers as job_helpers

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    session_id = "job_helpers_upload"
    session_dir = runtime.upload_root / session_id
    session_dir.mkdir()

    query_fixture = TESTS_ENSEMBL_DIR / "Escherichia_coli_str_k_12_substr_mg1655_gca_000005845.ASM584v2.dna.toplevel.fa.gz"
    target_fixture = TESTS_ENSEMBL_DIR / "Escherichia_coli_o157_h7_str_sakai_gca_000008865.ASM886v2.dna.toplevel.fa.gz"
    backup_fixture = TESTS_DATA_DIR / "backup.tar.gz"

    local_with_spaces = session_dir / "target file.fa.gz"
    shutil.copy(target_fixture, local_with_spaces)
    shared_target = session_dir / "shared_target.fa.gz"
    shutil.copy(target_fixture, shared_target)

    monkeypatch.setattr(dgenies, "app", runtime.app, raising=False)
    monkeypatch.setattr(
        dgenies,
        "config_reader",
        SimpleNamespace(
            example_query=str(query_fixture),
            example_target=str(target_fixture),
            example_backup=str(backup_fixture),
        ),
        raising=False,
    )

    local_df = job_helpers.create_datafile(local_with_spaces.name, "local", session_id, [])
    assert local_df.get_name() == "target file"
    assert os.path.basename(local_df.get_path()) == "target_file.fa.gz"
    assert local_df.get_type() == "local"
    assert local_df.is_example() is False
    assert not local_with_spaces.exists()
    assert Path(local_df.get_path()).exists()

    example_df = job_helpers.create_datafile(
        f"example://{query_fixture.name}",
        "local",
        session_id,
        [str(query_fixture), str(target_fixture)],
    )
    assert example_df.get_name() == query_fixture.name
    assert example_df.get_path() == str(query_fixture)
    assert example_df.is_example() is True

    with pytest.raises(DGeniesExampleInvalid):
        job_helpers.create_datafile("example://missing.fa.gz", "local", session_id, [str(query_fixture)])
    with pytest.raises(DGeniesExampleNotAvailable):
        job_helpers.create_datafile(f"example://{query_fixture.name}", "local", session_id, [])
    with pytest.raises(FileNotFoundError):
        job_helpers.create_datafile("missing.fa.gz", "local", session_id, [])

    url_df = job_helpers.create_datafile("https://example.org/query.fa.gz", "url", session_id, [])
    assert url_df.get_path() == "https://example.org/query.fa.gz"
    assert url_df.get_type() == "url"

    jobs = [
        {
            "query": f"example://{query_fixture.name}",
            "query_type": "local",
            "target": shared_target.name,
            "target_type": "local",
            "backup": f"example://{backup_fixture.name}",
            "backup_type": "local",
        },
        {
            "query": f"example://{query_fixture.name}",
            "query_type": "local",
            "target": shared_target.name,
            "target_type": "local",
            "align": "https://example.org/map.paf",
            "align_type": "url",
        },
    ]
    job_helpers.update_files(jobs, session_id)

    assert isinstance(jobs[0]["query"], DataFile)
    assert jobs[0]["query"] is jobs[1]["query"]
    assert jobs[0]["target"] is jobs[1]["target"]
    assert jobs[0]["query"].get_path() == str(query_fixture)
    assert jobs[0]["target"].get_path().endswith(shared_target.name)
    assert jobs[0]["backup"].is_example() is True
    assert jobs[1]["align"].get_path() == "https://example.org/map.paf"
    assert "query_type" not in jobs[0]
    assert "target_type" not in jobs[0]
    assert "backup_type" not in jobs[0]
    assert "align_type" not in jobs[1]

"""
Verifies the execution branches of the build_fasta helper, including error states, lock management, and file format variations.

Ensure that:
1. Appropriate exceptions are raised when a job is missing or the required FASTA file cannot be found.
2. File locks prevent concurrent builds and are reliably released if a sorting operation fails.
3. The logic correctly handles different build requirements, such as triggering sorts based on refresh markers (e.g., .new-reversals) and processing both compressed (.gz) and uncompressed files.
4. Asynchronous post-processing tasks, such as compression and email notifications, are scheduled correctly during the build lifecycle.
"""
def test_job_helpers_build_fasta_branches(monkeypatch, tmp_path):
    import dgenies
    import dgenies.job_helpers as job_helpers

    data_root = tmp_path / "jobs"
    data_root.mkdir()
    monkeypatch.setattr(dgenies, "APP_DATA", str(data_root), raising=False)
    monkeypatch.setattr(job_helpers.dgenies, "APP_DATA", str(data_root), raising=False)
    monkeypatch.setattr(dgenies, "MODE", "standalone", raising=False)
    monkeypatch.setattr(job_helpers.dgenies, "MODE", "standalone", raising=False)
    monkeypatch.setattr(dgenies, "mailer", None, raising=False)
    monkeypatch.setattr(job_helpers.dgenies, "mailer", None, raising=False)

    with pytest.raises(DGeniesMissingJobError):
        job_helpers.build_fasta("missing_job", False)

    job_id = "build_job"
    job_dir = data_root / job_id
    job_dir.mkdir()

    monkeypatch.setattr(job_helpers.Functions, "get_fasta_file", staticmethod(lambda *_args, **_kwargs: None), raising=False)
    with pytest.raises(FileNotFoundError):
        job_helpers.build_fasta(job_id, False)

    (job_dir / ".sorted").write_text("")
    lock_file = job_dir / ".query-fasta-build"

    monkeypatch.setattr(
        job_helpers.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(job_dir / ("query.sorted.fa" if is_sorted else "query.fa"))),
        raising=False,
    )
    monkeypatch.setattr(job_helpers, "has_fresh_sorted_query_fasta", lambda _res_dir: False, raising=False)
    monkeypatch.setattr(job_helpers.Functions, "is_file_lock_active", staticmethod(lambda _path: True), raising=False)
    assert job_helpers.build_fasta(job_id, False) == (1, False)

    refresh_marker = job_dir / ".new-reversals"
    refresh_marker.write_text("")
    sort_calls = []
    monkeypatch.setattr(job_helpers.Functions, "is_file_lock_active", staticmethod(lambda _path: False), raising=False)
    monkeypatch.setattr(job_helpers.Functions, "acquire_file_lock", staticmethod(lambda _path: True), raising=False)
    monkeypatch.setattr(
        job_helpers.Functions,
        "sort_fasta",
        staticmethod(lambda **kwargs: sort_calls.append(kwargs)),
        raising=False,
    )
    assert job_helpers.build_fasta(job_id, False) == (2, False)
    assert sort_calls[0]["job_name"] == job_id
    assert sort_calls[0]["with_date"] is False
    assert sort_calls[0]["overwrite"] is True
    assert not refresh_marker.exists()
    assert not (Path(str(lock_file) + ".pending")).exists()

    refresh_marker.write_text("")
    released = []
    monkeypatch.setattr(
        job_helpers.Functions,
        "sort_fasta",
        staticmethod(lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("sort failed"))),
        raising=False,
    )
    monkeypatch.setattr(
        job_helpers.Functions,
        "release_file_lock",
        staticmethod(lambda path: released.append(path)),
        raising=False,
    )
    with pytest.raises(RuntimeError, match="sort failed"):
        job_helpers.build_fasta(job_id, False)
    assert released == [str(lock_file)]

    monkeypatch.setattr(job_helpers, "has_fresh_sorted_query_fasta", lambda _res_dir: True, raising=False)
    monkeypatch.setattr(job_helpers.Functions, "is_file_lock_active", staticmethod(lambda _path: True), raising=False)
    assert job_helpers.build_fasta(job_id, False) == (1, False)

    timers = []

    class FakeTimer:
        def __init__(self, interval, func, kwargs=None):
            self.interval = interval
            self.func = func
            self.kwargs = kwargs or {}
            timers.append(self)

        def start(self):
            return None

    monkeypatch.setattr(job_helpers.threading, "Timer", FakeTimer, raising=False)
    monkeypatch.setattr(job_helpers.Functions, "is_file_lock_active", staticmethod(lambda _path: False), raising=False)
    monkeypatch.setattr(job_helpers.Functions, "acquire_file_lock", staticmethod(lambda _path: True), raising=False)
    monkeypatch.setattr(
        job_helpers.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(job_dir / ("query.sorted.fasta" if is_sorted else "query.fasta"))),
        raising=False,
    )
    assert job_helpers.build_fasta(job_id, True) == (1, False)
    assert timers[0].func == job_helpers.Functions.compress_and_send_mail
    assert timers[0].kwargs["lock_file"] == str(lock_file)

    monkeypatch.setattr(
        job_helpers.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(job_dir / ("query.fa.gz.sorted" if is_sorted else "query.fa.gz"))),
        raising=False,
    )
    assert job_helpers.build_fasta(job_id, True) == (2, True)

"""
Tests the logic for computing job statistics summaries and verifying the freshness of sorted FASTA files.

Ensure that:
1. compute_summary correctly identifies and returns appropriate statuses (e.g., job_not_found, file_not_found, done, or fail) based on the presence of job directories, PAF files, and failure markers.
2. The summary generation process handles both immediate results and delayed/asynchronous statistics generation via polling or timers.
3. has_fresh_sorted_query_fasta accurately detects if a sorted FASTA file is stale by comparing its modification time against refresh marker files (e.g., .new-reversals).
"""
def test_job_helpers_compute_summary_and_freshness(monkeypatch, tmp_path):
    import dgenies
    import dgenies.job_helpers as job_helpers

    data_root = tmp_path / "jobs"
    data_root.mkdir()
    monkeypatch.setattr(dgenies, "APP_DATA", str(data_root), raising=False)
    monkeypatch.setattr(job_helpers.dgenies, "APP_DATA", str(data_root), raising=False)

    assert job_helpers.compute_summary("missing") == (None, "job_not_found")

    file_job = data_root / "file_not_found"
    file_job.mkdir()

    class MissingPaf:
        def __init__(self, *_args, **_kwargs):
            raise FileNotFoundError

    monkeypatch.setattr(job_helpers, "Paf", MissingPaf, raising=False)
    assert job_helpers.compute_summary("file_not_found") == (None, "file_not_found")

    done_job = data_root / "done_job"
    done_job.mkdir()

    class DonePaf:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_summary_stats(self):
            return {100: 75.0}

    monkeypatch.setattr(job_helpers, "Paf", DonePaf, raising=False)
    assert job_helpers.compute_summary("done_job") == ({100: 75.0}, "done")

    waiting_job = data_root / "waiting_job"
    waiting_job.mkdir()
    waiting_state = {"stats": None}

    class WaitingPaf:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_summary_stats(self):
            return waiting_state["stats"]

        def build_summary_stats(self, status_file):
            waiting_state["stats"] = {50: 12.5}
            Path(status_file).unlink()

    class ImmediateTimer:
        def __init__(self, _interval, func, kwargs=None):
            self.func = func
            self.kwargs = kwargs or {}

        def start(self):
            self.func(**self.kwargs)

    monkeypatch.setattr(job_helpers, "Paf", WaitingPaf, raising=False)
    monkeypatch.setattr(job_helpers.threading, "Timer", ImmediateTimer, raising=False)
    monkeypatch.setattr(job_helpers.time, "sleep", lambda _seconds: None, raising=False)
    assert job_helpers.compute_summary("waiting_job") == ({50: 12.5}, "done")

    fail_job = data_root / "fail_job"
    fail_job.mkdir()
    (fail_job / ".summarize.fail").write_text("")
    monkeypatch.setattr(job_helpers, "Paf", DonePaf, raising=False)
    assert job_helpers.compute_summary("fail_job") == (None, "fail")

    running_fail_job = data_root / "running_fail_job"
    running_fail_job.mkdir()
    status_file = running_fail_job / ".summarize"
    status_file.write_text("")

    class RunningFailPaf:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_summary_stats(self):
            return None

    calls = {"count": 0}

    def fake_sleep(_seconds):
        calls["count"] += 1
        if calls["count"] == 1 and status_file.exists():
            status_file.unlink()

    monkeypatch.setattr(job_helpers, "Paf", RunningFailPaf, raising=False)
    monkeypatch.setattr(job_helpers.time, "sleep", fake_sleep, raising=False)
    assert job_helpers.compute_summary("running_fail_job") == (None, "fail")

    fresh_dir = tmp_path / "fresh_sorted"
    fresh_dir.mkdir()
    assert job_helpers.has_fresh_sorted_query_fasta(str(fresh_dir)) is False

    (fresh_dir / ".sorted").write_text("")
    base_query = fresh_dir / "query.fa"
    sorted_query = fresh_dir / "query.fa.sorted"
    base_query.write_text(">q\nACGT\n")
    sorted_query.write_text(">q\nACGT\n")

    monkeypatch.setattr(
        job_helpers.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(sorted_query if is_sorted else base_query)),
        raising=False,
    )
    assert job_helpers.has_fresh_sorted_query_fasta(str(fresh_dir)) is True

    monkeypatch.setattr(
        job_helpers.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(base_query)),
        raising=False,
    )
    assert job_helpers.has_fresh_sorted_query_fasta(str(fresh_dir)) is False

    monkeypatch.setattr(
        job_helpers.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(sorted_query if is_sorted else base_query)),
        raising=False,
    )
    refresh_marker = fresh_dir / ".new-reversals"
    refresh_marker.write_text("")
    os.utime(refresh_marker, (sorted_query.stat().st_mtime + 5, sorted_query.stat().st_mtime + 5))
    assert job_helpers.has_fresh_sorted_query_fasta(str(fresh_dir)) is False
    os.utime(sorted_query, (refresh_marker.stat().st_mtime + 5, refresh_marker.stat().st_mtime + 5))
    assert job_helpers.has_fresh_sorted_query_fasta(str(fresh_dir)) is True

"""
Tests build_fasta behavior in webserver mode, focusing on path resolution, file locking, and freshness detection edge cases.

Ensure that:
1. Path resolution for both standard and sorted FASTA files is accurate within the job directory.
2. File locking mechanisms prevent concurrent execution and correctly manage stale or pending lock states.
3. The system appropriately identifies out-of-date sorted files using refresh markers (e.g., .new-reversals).
4. Asynchronous tasks, such as compression and email notifications, are properly scheduled during the build lifecycle.
"""
def test_job_helpers_build_fasta_webserver_paths_and_freshness_edge_cases(monkeypatch, tmp_path):
    import dgenies
    import dgenies.job_helpers as job_helpers
    original_has_fresh = job_helpers.has_fresh_sorted_query_fasta

    data_root = tmp_path / "jobs_web"
    data_root.mkdir()
    monkeypatch.setattr(dgenies, "APP_DATA", str(data_root), raising=False)
    monkeypatch.setattr(job_helpers.dgenies, "APP_DATA", str(data_root), raising=False)
    monkeypatch.setattr(dgenies, "MODE", "webserver", raising=False)
    monkeypatch.setattr(job_helpers.dgenies, "MODE", "webserver", raising=False)
    monkeypatch.setattr(dgenies, "mailer", object(), raising=False)
    monkeypatch.setattr(job_helpers.dgenies, "mailer", object(), raising=False)

    job_id = "web_build"
    job_dir = data_root / job_id
    job_dir.mkdir()
    (job_dir / ".sorted").write_text("")
    (job_dir / "query.fa").write_text(">q\nACGT\n")
    (job_dir / "query.sorted.fa").write_text(">q\nTGCA\n")

    def fasta_lookup(_res_dir, _type_f, is_sorted):
        if is_sorted:
            return str(job_dir / "query.sorted.fa")
        return str(job_dir / "query.fa")

    assert fasta_lookup(None, None, True).endswith("query.sorted.fa")

    monkeypatch.setattr(job_helpers.Functions, "is_file_lock_active", staticmethod(lambda _path: False), raising=False)
    monkeypatch.setattr(job_helpers.Functions, "acquire_file_lock", staticmethod(lambda _path: True), raising=False)
    monkeypatch.setattr(job_helpers, "has_fresh_sorted_query_fasta", lambda _res_dir: True, raising=False)
    monkeypatch.setattr(
        job_helpers.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: None if is_sorted else str(job_dir / "query.fa")),
        raising=False,
    )
    with pytest.raises(BaseException):
        job_helpers.build_fasta(job_id, False)

    monkeypatch.setattr(job_helpers.Functions, "get_fasta_file", staticmethod(fasta_lookup), raising=False)
    monkeypatch.setattr(job_helpers, "has_fresh_sorted_query_fasta", lambda _res_dir: False, raising=False)
    refresh_marker = job_dir / ".new-reversals"
    refresh_marker.write_text("")
    lock_file = job_dir / ".query-fasta-build"
    timer_calls = []

    class FakeTimer:
        def __init__(self, interval, func, kwargs=None):
            timer_calls.append((interval, func, kwargs or {}))

        def start(self):
            return None

    def acquire_lock(path):
        Path(path).write_text("")
        return True

    sleep_calls = {"count": 0}

    def fake_sleep(_seconds):
        sleep_calls["count"] += 1
        if sleep_calls["count"] == 1 and lock_file.exists():
            lock_file.unlink()

    monkeypatch.setattr(job_helpers.threading, "Timer", FakeTimer, raising=False)
    monkeypatch.setattr(job_helpers.Functions, "acquire_file_lock", staticmethod(acquire_lock), raising=False)
    monkeypatch.setattr(job_helpers.time, "sleep", fake_sleep, raising=False)
    result = job_helpers.build_fasta(job_id, False)
    assert result == (2, False)
    assert timer_calls[0][2]["with_date"] is True
    assert timer_calls[0][2]["overwrite"] is True
    assert not refresh_marker.exists()
    assert not Path(str(lock_file) + ".pending").exists()

    refresh_marker.write_text("")
    timer_calls.clear()
    monkeypatch.setattr(job_helpers.Functions, "acquire_file_lock", staticmethod(acquire_lock), raising=False)
    result = job_helpers.build_fasta(job_id, True)
    assert result == (1, False)
    assert timer_calls[0][2]["compress"] is True

    refresh_marker.write_text("")
    Path(lock_file).write_text("")
    Path(str(lock_file) + ".pending").write_text("")
    sleep_calls["count"] = 0

    def sleep_without_unlock(_seconds):
        sleep_calls["count"] += 1

    monkeypatch.setattr(job_helpers.time, "sleep", sleep_without_unlock, raising=False)
    monkeypatch.setattr(job_helpers.Functions, "acquire_file_lock", staticmethod(lambda _path: True), raising=False)
    assert job_helpers.build_fasta(job_id, False) == (1, False)
    assert sleep_calls["count"] >= 3
    Path(lock_file).unlink()

    monkeypatch.setattr(job_helpers, "has_fresh_sorted_query_fasta", lambda _res_dir: True, raising=False)
    monkeypatch.setattr(job_helpers.Functions, "is_file_lock_active", staticmethod(lambda _path: False), raising=False)
    monkeypatch.setattr(job_helpers.Functions, "acquire_file_lock", staticmethod(lambda _path: False), raising=False)
    monkeypatch.setattr(job_helpers.Functions, "get_fasta_file", staticmethod(fasta_lookup), raising=False)
    assert job_helpers.build_fasta(job_id, True) == (1, False)

    fresh_dir = tmp_path / "freshness_failures"
    fresh_dir.mkdir()
    (fresh_dir / ".sorted").write_text("")
    base_query = fresh_dir / "query.fa"
    sorted_query = fresh_dir / "query.fa.sorted"
    base_query.write_text(">q\nACGT\n")
    sorted_query.write_text(">q\nACGT\n")
    monkeypatch.setattr(
        job_helpers.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(sorted_query if is_sorted else base_query)),
        raising=False,
    )
    monkeypatch.setattr(job_helpers, "has_fresh_sorted_query_fasta", original_has_fresh, raising=False)
    monkeypatch.setattr(job_helpers.Functions, "get_fasta_file", staticmethod(lambda _res_dir, _type_f, is_sorted: None if is_sorted else str(base_query)), raising=False)
    assert job_helpers.has_fresh_sorted_query_fasta(str(fresh_dir)) is False
    monkeypatch.setattr(
        job_helpers.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(sorted_query if is_sorted else base_query)),
        raising=False,
    )
    monkeypatch.setattr(job_helpers.os.path, "realpath", lambda _path: (_ for _ in ()).throw(FileNotFoundError("gone")), raising=False)
    assert job_helpers.has_fresh_sorted_query_fasta(str(fresh_dir)) is False

"""
Tests that the freshness check for sorted FASTA files fails gracefully when metadata access is interrupted by filesystem errors.

Ensure that:
1. The function returns False if the modification time of a sorted file cannot be retrieved due to a FileNotFoundError.
2. Metadata retrieval failures do not cause the application to crash during the freshness verification process.
"""
def test_has_fresh_sorted_query_fasta_returns_false_when_sorted_mtime_is_missing(monkeypatch, tmp_path):
    import dgenies.job_helpers as job_helpers

    res_dir = tmp_path / "missing-sorted-mtime"
    res_dir.mkdir()
    (res_dir / ".sorted").write_text("")
    refresh_marker = res_dir / ".new-reversals"
    refresh_marker.write_text("")
    base_query = res_dir / "query.fa"
    sorted_query = res_dir / "query.fa.sorted"
    base_query.write_text(">q\nACGT\n")
    sorted_query.write_text(">q\nACGT\n")

    monkeypatch.setattr(
        job_helpers.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(sorted_query if is_sorted else base_query)),
        raising=False,
    )
    monkeypatch.setattr(job_helpers.os.path, "realpath", os.path.realpath, raising=False)

    def missing_sorted_mtime(path):
        assert path == str(sorted_query)
        raise FileNotFoundError("missing sorted")

    monkeypatch.setattr(job_helpers.os.path, "getmtime", missing_sorted_mtime, raising=False)
    assert job_helpers.has_fresh_sorted_query_fasta(str(res_dir)) is False
