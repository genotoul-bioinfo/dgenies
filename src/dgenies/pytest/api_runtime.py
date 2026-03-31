"""Runtime and end-to-end API behavior tests."""

import json
import os
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from dgenies.api.datamodels import BatchSubmissionQuery, ExportFileState, Job, NoAssocInput, PrepareFastaInput
from dgenies.lib.exceptions import (
    DGeniesDeleteGalleryJobForbidden,
    DGeniesExampleInvalid,
    DGeniesMissingJobError,
    DGeniesValidationError,
)
from dgenies.pytest.helpers import (
    TESTS_DATA_DIR,
    TESTS_ENSEMBL_DIR,
    _build_align_job_from_script,
    _build_job_from_test_api_script,
    _build_plot_backup_job_from_script,
    _create_query_job_dir,
    _install_fake_launch,
    _make_job_model,
    _make_upload_form,
    _setup_api_runtime,
)

# This file was split out from src/dgenies/test_dgenies_api.py.

def test_translated_test_api_sh_submission_flow_uses_real_files(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    batch, uploads = _build_job_from_test_api_script()
    session_id = "session_from_test_api_sh"
    launched = _install_fake_launch(monkeypatch, api_module)
    monkeypatch.setattr(api_module.Functions, "create_session", staticmethod(lambda: session_id), raising=False)

    with runtime.app.app_context():
        response, status = api_module.post_jobs(batch)
        assert status == 200
        assert response["data"]["session_id"] == session_id
        assert set(response["data"]["needed_files"]) == {
            uploads["query"].name,
            uploads["target"].name,
        }

        jobs_file = runtime.upload_root / session_id / "jobs.json"
        assert jobs_file.exists()
        saved_jobs = json.loads(jobs_file.read_text())
        assert saved_jobs["batch_id"] == batch.batch_id
        assert saved_jobs["jobs"][0]["tool"] == "minimap2"

        response, status = api_module.upload_file(_make_upload_form(session_id, uploads["query"]))
        assert status == 200
        assert response["data"]["file"]["name"] == uploads["query"].name
        assert set(response["data"]["needed_files"]) == {uploads["target"].name}

        response, status = api_module.upload_file(_make_upload_form(session_id, uploads["query"]))
        assert status == 403
        assert response["message"] == "Unneeded file or already uploaded file"

        response, status = api_module.upload_file(_make_upload_form(session_id, uploads["target"]))
        assert status == 200
        assert response["data"]["batch_id"] == batch.batch_id
        assert response["data"]["job_ids"] == [batch.batch_id]
        assert launched["session_id"] == session_id
        assert launched["jobs"][0].job_id == batch.batch_id

        assert (runtime.upload_root / session_id / uploads["query"].name).read_bytes() == uploads["query"].read_bytes()
        assert (runtime.upload_root / session_id / uploads["target"].name).read_bytes() == uploads["target"].read_bytes()


def test_translated_api_align_self_local_sh_requires_only_target_upload(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job, uploads = _build_align_job_from_script("api-align-self-local.sh", "align_self_local")
    batch = BatchSubmissionQuery(batch_id="align_self_local", email="local@example.com", nb_jobs=1, jobs=[job])
    session_id = "align_self_local_session"
    launched = _install_fake_launch(monkeypatch, api_module)
    monkeypatch.setattr(api_module.Functions, "create_session", staticmethod(lambda: session_id), raising=False)

    with runtime.app.app_context():
        response, status = api_module.post_jobs(batch)
        assert status == 200
        assert response["data"]["needed_files"] == [uploads["target"].name]

        response, status = api_module.upload_file(_make_upload_form(session_id, uploads["target"]))
        assert status == 200
        assert response["data"]["job_ids"] == [job.job_id]
        assert launched["jobs"][0].query == ""
        assert launched["jobs"][0].target == uploads["target"].name


def test_translated_api_plot_backup_local_sh_uploads_real_archive(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job, backup_path = _build_plot_backup_job_from_script("api-plot-backup-local.sh", "plot_backup_local")
    batch = BatchSubmissionQuery(batch_id="plot_backup_local", email="plot@example.com", nb_jobs=1, jobs=[job])
    session_id = "plot_backup_local_session"
    launched = _install_fake_launch(monkeypatch, api_module)
    monkeypatch.setattr(api_module.Functions, "create_session", staticmethod(lambda: session_id), raising=False)

    with runtime.app.app_context():
        response, status = api_module.post_jobs(batch)
        assert status == 200
        assert response["data"]["needed_files"] == [backup_path.name]

        response, status = api_module.upload_file(_make_upload_form(session_id, backup_path))
        assert status == 200
        assert response["data"]["batch_id"] == job.job_id
        assert launched["jobs"][0].backup == backup_path.name
        assert (runtime.upload_root / session_id / backup_path.name).read_bytes() == backup_path.read_bytes()


def test_upload_rejects_invalid_gzip_fixture_from_tests_data(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    fake_gzip = TESTS_DATA_DIR / "fake.fa.gz"
    target_path = next(TESTS_ENSEMBL_DIR.glob("*.ASM584v2.dna.toplevel.fa.gz"))
    job = Job(
        job_id="invalid_gzip_job",
        type="align",
        query=fake_gzip.name,
        query_type="local",
        target=target_path.name,
        target_type="local",
        align="",
        align_type="local",
        backup="",
        backup_type="local",
        tool="minimap2",
        tool_options=["repeat:few"],
    )
    batch = BatchSubmissionQuery(batch_id="invalid_gzip_job", email="bad@example.com", nb_jobs=1, jobs=[job])
    session_id = "invalid_gzip_session"
    monkeypatch.setattr(api_module.Functions, "create_session", staticmethod(lambda: session_id), raising=False)

    with runtime.app.app_context():
        response, status = api_module.post_jobs(batch)
        assert status == 200
        assert fake_gzip.name in response["data"]["needed_files"]

        response, status = api_module.upload_file(_make_upload_form(session_id, fake_gzip))
        assert status == 415
        assert response["message"] == "Not a gzip file"


def test_export_status_and_download_use_real_query_fasta(monkeypatch, tmp_path):
    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "export_job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()
    source_query = next(TESTS_ENSEMBL_DIR.glob("*.ASM584v2.dna.toplevel.fa.gz"))
    copied_query = _create_query_job_dir(job_dir, source_query)

    response, status = runtime.api.get_export_status(SimpleNamespace(job_id=job_id))
    assert status == 200
    assert response["data"]["query_fasta"]["state"] == ExportFileState.ready
    assert response["data"]["query_fasta"]["filename"] == copied_query.name
    assert response["data"]["query_as_reference"]["state"] == ExportFileState.blocked

    with runtime.app.app_context():
        download = runtime.api.get_fasta_query(SimpleNamespace(job_id=job_id))
        assert download.status_code == 200
        assert download.mimetype == "application/gzip"
        assert download.get_data() == copied_query.read_bytes()


def test_query_as_reference_status_tracks_pointer_and_refresh_marker(monkeypatch, tmp_path):
    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "query_as_reference_job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()
    source_query = next(TESTS_ENSEMBL_DIR.glob("*.ASM584v2.dna.toplevel.fa.gz"))
    _create_query_job_dir(job_dir, source_query)
    (job_dir / ".sorted").touch()

    generated_name = f"20240324101010_as_reference_{source_query.name[:-3]}"
    generated_path = job_dir / generated_name
    generated_path.write_text(">chr1\nACGT\n")

    status = runtime.api.get_query_as_reference_export_status(job_id)
    assert status.state == ExportFileState.ready
    assert status.filename == generated_name
    pointer_file = job_dir / runtime.api.QUERY_AS_REFERENCE_POINTER
    assert pointer_file.read_text() == str(generated_path)

    refresh_marker = job_dir / ".new-reversals"
    refresh_marker.touch()
    os.utime(refresh_marker, (generated_path.stat().st_mtime + 10, generated_path.stat().st_mtime + 10))
    status = runtime.api.get_query_as_reference_export_status(job_id)
    assert status.state == ExportFileState.not_ready


def test_start_query_as_reference_build_starts_background_worker(monkeypatch, tmp_path):
    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "background_build_job"
    (runtime.data_root / job_id).mkdir()

    monkeypatch.setattr(
        runtime.api,
        "get_query_as_reference_export_status",
        lambda _job_id: runtime.api.create_export_file_status(ExportFileState.not_ready, message="Build pending"),
        raising=False,
    )
    monkeypatch.setattr(runtime.api.Functions, "acquire_file_lock", staticmethod(lambda _path: True), raising=False)

    thread_call = {}

    class DummyThread:
        def __init__(self, target, args, daemon, name):
            thread_call["target"] = target
            thread_call["args"] = args
            thread_call["daemon"] = daemon
            thread_call["name"] = name

        def start(self):
            thread_call["started"] = True

    monkeypatch.setattr(runtime.api.threading, "Thread", DummyThread, raising=False)

    status = runtime.api.start_query_as_reference_build(job_id)
    assert status.state == ExportFileState.not_ready
    assert thread_call["target"] is runtime.api._build_query_as_reference_worker
    assert thread_call["args"] == (job_id,)
    assert thread_call["daemon"] is True
    assert thread_call["started"] is True


def test_prepare_fasta_query_and_summary_wrap_backend_statuses(monkeypatch):
    import dgenies.api as api_module

    monkeypatch.setattr(api_module, "build_fasta", lambda job_id, gzip: (2, gzip), raising=False)
    response, status = api_module.prepare_fasta_query(SimpleNamespace(job_id="job"), PrepareFastaInput(gzip=True))
    assert status == 200
    assert str(response["data"]["status"]).lower() in {"preparefastaenum.done", "done"}
    assert response["data"]["gzip"] is True

    monkeypatch.setattr(api_module, "compute_summary", lambda job_id: ({0: 12.5}, "done"), raising=False)
    response, status = api_module.get_summary(SimpleNamespace(job_id="job"))
    assert status == 200
    assert response["message"] == "done"
    assert response["data"] == {0: 12.5}

    monkeypatch.setattr(api_module, "compute_summary", lambda job_id: (None, "job_not_found"), raising=False)
    response, status = api_module.get_summary(SimpleNamespace(job_id="missing"))
    assert status == 404
    assert response["message"] == "Job does not exists!"


def test_post_build_query_as_reference_maps_export_states(monkeypatch, tmp_path):
    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "build_reference_job"
    (runtime.data_root / job_id).mkdir()

    monkeypatch.setattr(
        runtime.api,
        "start_query_as_reference_build",
        lambda _job_id: runtime.api.create_export_file_status(ExportFileState.blocked, message="Sort first"),
        raising=False,
    )
    response, status = runtime.api.post_build_query_as_reference(SimpleNamespace(job_id=job_id))
    assert status == 409
    assert response["message"] == "Sort first"

    monkeypatch.setattr(
        runtime.api,
        "start_query_as_reference_build",
        lambda _job_id: runtime.api.create_export_file_status(ExportFileState.ready, message="Ready"),
        raising=False,
    )
    response = runtime.api.post_build_query_as_reference(SimpleNamespace(job_id=job_id))
    assert response["code"] == 0
    assert response["message"] == "ok"


def test_dotplot_sort_and_assoc_endpoints_with_fake_paf(monkeypatch, tmp_path):
    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "dotplot_job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()
    for filename in ("map.paf", "query.idx", "target.idx"):
        (job_dir / filename).write_text("placeholder\n")

    class DummyPaf:
        def __init__(self, paf_file, *_args, **_kwargs):
            self.paf_file = paf_file
            self.parsed = True
            self.sorted = True
            self.error = None

        def get_dotplot_data(self, sorted=False):
            return {
                "y_len": 10,
                "x_len": 20,
                "min_idy": 0.1,
                "max_idy": 0.9,
                "lines": {0: [(0, 0, 1, 1, 0.8, "q1", "t1")]},
                "y_contigs": {"q1": 10},
                "y_order": ["q1"],
                "x_contigs": {"t1": 20},
                "x_order": ["t1"],
                "name_y": "query",
                "name_x": "target",
                "limit_idy": [0.25, 0.5, 0.75],
                "sorted": sorted,
                "sampled": False,
                "max_nb_lines": 100,
            }

        def sort(self):
            output_dir = Path(self.paf_file).parent
            (output_dir / ".sorted").touch()
            (output_dir / "map.paf.sorted").touch()
            (output_dir / "query.idx.sorted").touch()
            self.parsed = True

        def parse_paf(self, *_args, **_kwargs):
            self.parsed = True

        def reverse_contig(self, _contig_name):
            self.parsed = True

        def build_query_on_target_association_records(self):
            return [("q1", "t1", "+", 10, 1, 10, 20, 2, 11)]

        def build_query_on_target_association_file(self):
            return "q1\tt1\t+\n"

        def build_list_no_assoc(self, _which):
            return ["chr_unmatched"]

    monkeypatch.setattr(runtime.api, "Paf", DummyPaf, raising=False)

    response = runtime.api.get_dotplot(SimpleNamespace(job_id=job_id))
    assert response["code"] == 0
    assert (job_dir / ".valid").exists()

    response, status = runtime.api.post_sort(SimpleNamespace(job_id=job_id))
    assert status == 200
    assert (job_dir / ".sorted").exists()

    response, status = runtime.api.sorted_dotplot(SimpleNamespace(job_id=job_id))
    assert status == 200
    assert response["data"]["sorted"] is True

    response, status = runtime.api.post_reset_sort(SimpleNamespace(job_id=job_id))
    assert status == 200
    assert (job_dir / ".new-reversals").exists()
    assert not (job_dir / ".sorted").exists()

    response = runtime.api.post_reverse_contig(SimpleNamespace(job_id=job_id), SimpleNamespace(contig="q1"))
    assert response["code"] == 0

    response = runtime.api.get_qt_assoc(SimpleNamespace(job_id=job_id))
    assert response["code"] == 0
    assert response["data"]["count"] == 1

    response, status = runtime.api.get_dl_qt_assoc(SimpleNamespace(job_id=job_id))
    assert status == 200
    assert "q1\tt1" in response

    response, status = runtime.api.post_no_assoc(SimpleNamespace(job_id=job_id), NoAssocInput(which="query"))
    assert status == 200
    assert response["data"]["contigs"] == ["chr_unmatched"]

    response, status = runtime.api.post_dl_no_assoc(SimpleNamespace(job_id=job_id), NoAssocInput(which="query"))
    assert status == 200
    assert response == "chr_unmatched\n"

def test_api_status_and_pointer_helpers(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "status_job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()

    pointer_path = job_dir / "pointer.txt"
    target_file = job_dir / "target.txt"
    target_file.write_text("content")
    api_module.write_path_pointer(str(pointer_path), str(target_file))
    assert api_module.read_path_pointer(str(pointer_path)) == str(target_file)
    missing_pointer = job_dir / "missing.txt"
    assert api_module.read_path_pointer(str(missing_pointer)) is None

    stale_marker = job_dir / "marker"
    stale_marker.write_text("")
    assert api_module.is_file_fresh(str(target_file), None) is True
    os.utime(stale_marker, (target_file.stat().st_mtime - 5, target_file.stat().st_mtime - 5))
    assert api_module.is_file_fresh(str(target_file), str(stale_marker)) is True
    os.utime(stale_marker, (target_file.stat().st_mtime + 5, target_file.stat().st_mtime + 5))
    assert api_module.is_file_fresh(str(target_file), str(stale_marker)) is False

    for name in (".sorted", "map.paf.sorted", "query.idx.sorted"):
        (job_dir / name).write_text("")
    assert api_module.has_sorted_output(job_id) is True
    assert api_module.get_job_dir(job_id) == str(job_dir)

    status = api_module.create_export_file_status(ExportFileState.ready, filename="file.fa", message="Ready")
    assert status.filename == "file.fa"
    assert api_module.build_state_progress(ExportFileState.ready) == 100
    assert api_module.build_state_progress(ExportFileState.blocked) == 0
    assert api_module.build_state_progress(ExportFileState.building) is None

    with runtime.app.test_request_context():
        response = api_module.send_download(str(target_file), "downloaded.txt")
        assert response.status_code == 200
        assert "downloaded.txt" in response.headers["Content-Disposition"]


def test_api_export_status_helpers_cover_remaining_states(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "export_states_job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()

    lock_file = job_dir / api_module.QUERY_FASTA_LOCK
    lock_file.write_text("")
    monkeypatch.setattr(api_module.Functions, "is_file_lock_active", staticmethod(lambda path: path == str(lock_file)), raising=False)
    status = api_module.get_query_fasta_export_status(job_id)
    assert status.state == ExportFileState.building

    lock_file.unlink()
    monkeypatch.setattr(api_module.Functions, "is_file_lock_active", staticmethod(lambda _path: False), raising=False)
    monkeypatch.setattr(api_module, "get_query_fasta_ready_file", lambda _job_id: None, raising=False)
    monkeypatch.setattr(api_module.Functions, "get_fasta_file", staticmethod(lambda *_args, **_kwargs: None), raising=False)
    status = api_module.get_query_fasta_export_status(job_id)
    assert status.state == ExportFileState.unavailable

    monkeypatch.setattr(api_module.Functions, "get_fasta_file", staticmethod(lambda *_args, **_kwargs: "query.fa.gz"), raising=False)
    status = api_module.get_query_fasta_export_status(job_id)
    assert status.state == ExportFileState.not_ready

    all_vs_all = job_dir / ".all-vs-all"
    all_vs_all.write_text("")
    status = api_module.get_query_as_reference_export_status(job_id)
    assert status.state == ExportFileState.unavailable
    all_vs_all.unlink()

    status = api_module.get_query_as_reference_export_status(job_id)
    assert status.state == ExportFileState.blocked
    (job_dir / ".sorted").write_text("")

    build_lock = job_dir / api_module.QUERY_AS_REFERENCE_LOCK
    build_lock.write_text("")
    monkeypatch.setattr(api_module.Functions, "is_file_lock_active", staticmethod(lambda path: path == str(build_lock)), raising=False)
    status = api_module.get_query_as_reference_export_status(job_id)
    assert status.state == ExportFileState.building
    build_lock.unlink()

    monkeypatch.setattr(api_module.Functions, "is_file_lock_active", staticmethod(lambda _path: False), raising=False)
    error_file = job_dir / api_module.QUERY_AS_REFERENCE_ERROR
    error_file.write_text("previous failure")
    monkeypatch.setattr(api_module, "find_query_as_reference", lambda _job_id: None, raising=False)
    status = api_module.get_query_as_reference_export_status(job_id)
    assert status.state == ExportFileState.not_ready
    assert status.message == "previous failure"


def test_build_query_as_reference_helpers(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "build_query_reference"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()
    for filename in ("map.paf", "query.idx", "target.idx"):
        (job_dir / filename).write_text("placeholder\n")
    original_build_query_as_reference_file = api_module.build_query_as_reference_file

    class DummyPaf:
        def __init__(self, *_args, **_kwargs):
            self.sorted = False

        def parse_paf(self, *_args):
            return None

        def build_query_chr_as_reference(self, compress=False):
            return "_._"

    assert DummyPaf().build_query_chr_as_reference() == "_._"
    monkeypatch.setattr(api_module, "Paf", DummyPaf, raising=False)
    with pytest.raises(ValueError):
        api_module.build_query_as_reference_file(job_id)

    (job_dir / ".all-vs-all").write_text("")
    with pytest.raises(ValueError):
        api_module.build_query_as_reference_file(job_id)
    (job_dir / ".all-vs-all").unlink()

    calls = {}
    monkeypatch.setattr(api_module, "build_query_as_reference_file", lambda _job_id: str(job_dir / "generated.fa"), raising=False)
    monkeypatch.setattr(api_module, "write_path_pointer", lambda pointer, file_path: calls.update(pointer=pointer, file_path=file_path), raising=False)
    monkeypatch.setattr(api_module.Functions, "release_file_lock", staticmethod(lambda path: calls.update(lock=path)), raising=False)
    api_module._build_query_as_reference_worker(job_id)
    assert calls["file_path"].endswith("generated.fa")
    assert calls["lock"].endswith(api_module.QUERY_AS_REFERENCE_LOCK)

    calls.clear()
    monkeypatch.setattr(api_module, "build_query_as_reference_file", lambda _job_id: (_ for _ in ()).throw(RuntimeError("boom")), raising=False)
    api_module._build_query_as_reference_worker(job_id)
    assert (job_dir / api_module.QUERY_AS_REFERENCE_ERROR).read_text() == "boom"
    assert calls["lock"].endswith(api_module.QUERY_AS_REFERENCE_LOCK)

    monkeypatch.setattr(
        api_module,
        "get_query_as_reference_export_status",
        lambda _job_id: api_module.create_export_file_status(ExportFileState.ready, filename="existing.fa"),
        raising=False,
    )
    assert api_module.start_query_as_reference_build(job_id).state == ExportFileState.ready

    monkeypatch.setattr(
        api_module,
        "get_query_as_reference_export_status",
        lambda _job_id: api_module.create_export_file_status(ExportFileState.not_ready, message="not built"),
        raising=False,
    )
    monkeypatch.setattr(api_module.Functions, "acquire_file_lock", staticmethod(lambda _path: False), raising=False)
    assert api_module.start_query_as_reference_build(job_id).state == ExportFileState.not_ready

    class MissingOutputPaf:
        def __init__(self, *_args, **_kwargs):
            self.sorted = True

        def parse_paf(self, *_args):
            return None

        def build_query_chr_as_reference(self, compress=False):
            return str(job_dir / "missing.fa")

    monkeypatch.setattr(api_module, "build_query_as_reference_file", original_build_query_as_reference_file, raising=False)
    monkeypatch.setattr(api_module, "Paf", MissingOutputPaf, raising=False)
    with pytest.raises(FileNotFoundError):
        api_module.build_query_as_reference_file(job_id)

    built_output = job_dir / "built.fa"
    built_output.write_text(">query\nACGT\n")

    class SuccessfulPaf:
        def __init__(self, *_args, **_kwargs):
            self.sorted = True

        def parse_paf(self, *_args):
            return None

        def build_query_chr_as_reference(self, compress=False):
            return str(built_output)

    monkeypatch.setattr(api_module, "Paf", SuccessfulPaf, raising=False)
    assert api_module.build_query_as_reference_file(job_id) == str(built_output)


def test_api_wrappers_cover_status_summary_and_download_errors(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "wrapper_job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()

    response, status = api_module.get_export_status(SimpleNamespace(job_id="missing"))
    assert status == 404

    monkeypatch.setattr(api_module.Functions, "get_status", staticmethod(lambda job: {"status": "unknown"}), raising=False)
    response, status = api_module.get_status(SimpleNamespace(job_id="missing"))
    assert status == 404

    monkeypatch.setattr(api_module.Functions, "get_status", staticmethod(lambda job: {}), raising=False)
    response, status = api_module.get_status(SimpleNamespace(job_id="broken"))
    assert status == 500

    monkeypatch.setattr(api_module, "compute_summary", lambda _job_id: (None, "file_not_found"), raising=False)
    response, status = api_module.get_summary(SimpleNamespace(job_id=job_id))
    assert status == 404
    monkeypatch.setattr(api_module, "compute_summary", lambda _job_id: (None, "fail"), raising=False)
    response, status = api_module.get_summary(SimpleNamespace(job_id=job_id))
    assert status == 500

    monkeypatch.setattr(api_module, "build_fasta", lambda *_args, **_kwargs: (_ for _ in ()).throw(DGeniesMissingJobError()), raising=False)
    response, status = api_module.prepare_fasta_query(SimpleNamespace(job_id=job_id), PrepareFastaInput(gzip=False))
    assert status == 404
    monkeypatch.setattr(api_module, "build_fasta", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("oops")), raising=False)
    response, status = api_module.prepare_fasta_query(SimpleNamespace(job_id=job_id), PrepareFastaInput(gzip=False))
    assert status == 500

    response, status = api_module.get_fasta_query(SimpleNamespace(job_id="missing"))
    assert status == 404
    monkeypatch.setattr(api_module.Functions, "is_file_lock_active", staticmethod(lambda _path: True), raising=False)
    response, status = api_module.get_fasta_query(SimpleNamespace(job_id=job_id))
    assert status == 409
    monkeypatch.setattr(api_module.Functions, "is_file_lock_active", staticmethod(lambda _path: False), raising=False)
    monkeypatch.setattr(api_module, "get_query_fasta_ready_file", lambda _job_id: None, raising=False)
    response, status = api_module.get_fasta_query(SimpleNamespace(job_id=job_id))
    assert status == 404

    query_file = job_dir / "query.fa"
    query_file.write_text(">q\nACGT\n")
    monkeypatch.setattr(api_module, "get_query_fasta_ready_file", lambda _job_id: str(query_file), raising=False)
    monkeypatch.setattr(api_module, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(IOError("broken")), raising=False)
    response, status = api_module.get_fasta_query(SimpleNamespace(job_id=job_id))
    assert status == 500


def test_api_download_endpoints_and_terminal_branches(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "download_job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()
    for filename, content in (("map.paf", "map"), ("query.idx", "query"), ("target.idx", "target")):
        (job_dir / filename).write_text(content)

    with runtime.app.test_request_context():
        backup_response = api_module.get_backup(SimpleNamespace(job_id=job_id))
        assert backup_response.status_code == 200
        backup_path = job_dir / f"{job_id}.tar.gz"
        with tarfile.open(backup_path, "r:gz") as archive:
            assert sorted(archive.getnames()) == ["map.paf", "query.idx", "target.idx"]

        response, status = api_module.get_backup(SimpleNamespace(job_id="missing"))
        assert status == 404

        (job_dir / "logs.txt").write_text("log output")
        backup_with_logs = api_module.get_backup(SimpleNamespace(job_id=job_id))
        assert backup_with_logs.status_code == 200
        with tarfile.open(backup_path, "r:gz") as archive:
            assert sorted(archive.getnames()) == ["logs.txt", "map.paf", "query.idx", "target.idx"]
        logs_response = api_module.get_logs(SimpleNamespace(job_id=job_id))
        assert logs_response.status_code == 200
        response, status = api_module.get_logs(SimpleNamespace(job_id="missing"))
        assert status == 404

        monkeypatch.setattr(
            api_module,
            "get_query_as_reference_export_status",
            lambda _job_id: api_module.create_export_file_status(ExportFileState.blocked, message="Sort first"),
            raising=False,
        )
        response, status = api_module.get_query_as_reference(SimpleNamespace(job_id=job_id))
        assert status == 409

        query_ref = job_dir / "query_as_reference.fa"
        query_ref.write_text(">chr1\nACGT\n")
        monkeypatch.setattr(
            api_module,
            "get_query_as_reference_export_status",
            lambda _job_id: api_module.create_export_file_status(ExportFileState.ready, filename=query_ref.name),
            raising=False,
        )
        monkeypatch.setattr(api_module, "find_query_as_reference", lambda _job_id: str(query_ref), raising=False)
        response = api_module.get_query_as_reference(SimpleNamespace(job_id=job_id))
        assert response.status_code == 200

        monkeypatch.setattr(
            api_module,
            "get_query_fasta_export_status",
            lambda _job_id: api_module.create_export_file_status(ExportFileState.ready, filename="query.fa.gz"),
            raising=False,
        )
        monkeypatch.setattr(api_module, "get_query_fasta_ready_file", lambda _job_id: str(query_ref), raising=False)
        response = api_module.get_dl_fasta_query(SimpleNamespace(job_id=job_id))
        assert response.status_code == 200

        monkeypatch.setattr(
            api_module,
            "get_query_fasta_export_status",
            lambda _job_id: api_module.create_export_file_status(ExportFileState.building, message="In progress"),
            raising=False,
        )
        response, status = api_module.get_dl_fasta_query(SimpleNamespace(job_id=job_id))
        assert status == 409

    monkeypatch.setattr(api_module, "start_query_as_reference_build", lambda _job_id: api_module.create_export_file_status(ExportFileState.unavailable, message="Disabled"), raising=False)
    response, status = api_module.post_build_query_as_reference(SimpleNamespace(job_id=job_id))
    assert status == 409
    monkeypatch.setattr(api_module, "start_query_as_reference_build", lambda _job_id: api_module.create_export_file_status(ExportFileState.building, message="running"), raising=False)
    response = api_module.post_build_query_as_reference(SimpleNamespace(job_id=job_id))
    assert response["code"] == 0
    response, status = api_module.post_build_query_as_reference(SimpleNamespace(job_id="missing"))
    assert status == 404

    assert api_module.get_build_query_as_reference(SimpleNamespace(job_id=job_id))[1] == 501
    assert api_module.get_file(SimpleNamespace(job_id=job_id, filename="x"))[1] == 501
    assert api_module.get_paf(SimpleNamespace(job_id=job_id))[1] == 501
    assert api_module.get_filter_out_target(SimpleNamespace(job_id=job_id))[1] == 501
    assert api_module.get_filter_out_query(SimpleNamespace(job_id=job_id))[1] == 501
    assert api_module.get_viewer(SimpleNamespace(job_id=job_id))[1] == 501
    assert api_module.get_example_jobs()[1] == 501


def test_api_job_lifecycle_and_gallery_branches(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "lifecycle_job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()
    (job_dir / "map.paf").write_text("map")
    (job_dir / "query.idx").write_text("query")
    (job_dir / "target.idx").write_text("target")

    monkeypatch.setattr(api_module.Functions, "get_gallery_items", staticmethod(lambda: [{"id_job": "gallery_job", "name": "Gallery"}]), raising=False)
    monkeypatch.setattr(api_module, "MODE", "webserver", raising=False)
    response = api_module.get_gallery()
    assert response["code"] == 0
    assert response["data"][0]["job_id"] == "gallery_job"
    monkeypatch.setattr(api_module, "MODE", "standalone", raising=False)
    response, status = api_module.get_gallery()
    assert status == 404

    class DummyJob:
        def __init__(self, id_job):
            self.id_job = id_job

        def delete(self):
            return None

    monkeypatch.setattr(api_module, "JobManager", DummyJob, raising=False)
    response = api_module.delete_job(SimpleNamespace(job_id=job_id))
    assert response["code"] == 0

    class MissingJob(DummyJob):
        def delete(self):
            raise DGeniesMissingJobError()

    monkeypatch.setattr(api_module, "JobManager", MissingJob, raising=False)
    response = api_module.delete_job(SimpleNamespace(job_id=job_id))
    assert response["code"] == 0

    class ForbiddenJob(DummyJob):
        def delete(self):
            raise DGeniesDeleteGalleryJobForbidden()

    monkeypatch.setattr(api_module, "JobManager", ForbiddenJob, raising=False)
    response, status = api_module.delete_job(SimpleNamespace(job_id=job_id))
    assert status == 403


def test_api_session_and_sorted_dotplot_error_branches(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    session_calls = {}

    class DummySessionRecord:
        def delete_instance(self):
            session_calls["deleted"] = True

        def ask_for_upload(self, _flag):
            return False

        def ping(self):
            session_calls["pinged"] = True

    class DummySessionModel:
        @staticmethod
        def connect():
            class Ctx:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            return Ctx()

        @staticmethod
        def get(s_id):
            session_calls["session_id"] = s_id
            return DummySessionRecord()

    monkeypatch.setattr(api_module, "db", SimpleNamespace(Session=DummySessionModel), raising=False)
    monkeypatch.setattr(api_module, "MODE", "webserver", raising=False)

    api_module.delete_session("sess-delete")
    assert session_calls["deleted"] is True
    assert api_module.allow_upload("sess-allow") is False
    assert api_module.ping_upload(SimpleNamespace(session_id="sess-ping")) == ({"code": 0, "message": "ok"}, 200)

    class MissingSessionModel(DummySessionModel):
        @staticmethod
        def get(s_id):
            raise api_module.DoesNotExist()

    monkeypatch.setattr(api_module, "db", SimpleNamespace(Session=MissingSessionModel), raising=False)
    response, status = api_module.ping_upload(SimpleNamespace(session_id="unknown"))
    assert status == 404

    class ExplodingSessionModel(DummySessionModel):
        @staticmethod
        def get(s_id):
            raise RuntimeError("boom")

    monkeypatch.setattr(api_module, "db", SimpleNamespace(Session=ExplodingSessionModel), raising=False)
    response, status = api_module.ping_upload(SimpleNamespace(session_id="boom"))
    assert status == 500

    monkeypatch.setattr(api_module, "MODE", "standalone", raising=False)
    response, status = api_module.sorted_dotplot(SimpleNamespace(job_id="missing"))
    assert status == 404

    job_id = "sorted_error_job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir(exist_ok=True)
    (job_dir / ".all-vs-all").write_text("")
    response, status = api_module.sorted_dotplot(SimpleNamespace(job_id=job_id))
    assert status == 403
    (job_dir / ".all-vs-all").unlink()

    class FailingPaf:
        def __init__(self, *_args, **_kwargs):
            self.parsed = False
            self.error = "sort failed"

        def sort(self):
            return None

    monkeypatch.setattr(api_module, "Paf", FailingPaf, raising=False)
    response, status = api_module.sorted_dotplot(SimpleNamespace(job_id=job_id))
    assert status == 500


def test_api_post_jobs_immediate_launch_and_error_branches(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    url_job = _make_job_model(
        job_id="url_job",
        query="https://example.org/query.fa.gz",
        query_type="url",
        target="https://example.org/target.fa.gz",
        target_type="url",
    )
    batch = BatchSubmissionQuery(batch_id="url_batch", email="url@example.org", nb_jobs=1, jobs=[url_job])
    launched = _install_fake_launch(monkeypatch, api_module)
    monkeypatch.setattr(api_module.Functions, "create_session", staticmethod(lambda: "url_session"), raising=False)
    monkeypatch.setattr(api_module, "allow_upload", lambda _session_id: False, raising=False)

    with runtime.app.app_context():
        response, status = api_module.post_jobs(batch)
        assert status == 200
        assert response["data"]["session_id"] is None
        assert response["data"]["batch_id"] == "url_job"
        assert launched["session_id"] == "url_session"

        monkeypatch.setattr(api_module, "valid_form", lambda _form: (_ for _ in ()).throw(DGeniesValidationError("bad form")), raising=False)
        response, status = api_module.post_jobs(batch)
        assert status == 400

        monkeypatch.setattr(api_module, "valid_form", lambda _form: None, raising=False)
        monkeypatch.setattr(api_module.Functions, "create_session", staticmethod(lambda: (_ for _ in ()).throw(DGeniesExampleInvalid("missing.fa.gz"))), raising=False)
        response, status = api_module.post_jobs(batch)
        assert status == 404

        monkeypatch.setattr(api_module.Functions, "create_session", staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("boom"))), raising=False)
        response, status = api_module.post_jobs(batch)
        assert status == 500


def test_launch_batch_sanitizes_colliding_job_ids(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    (runtime.upload_root / "upload-session").mkdir()
    (runtime.data_root / "dup_job").mkdir()
    launched = []

    class DummyLaunchJob(SimpleNamespace):
        def launch_standalone(self):
            launched.append(("standalone", self.id_job))

        def launch(self):
            launched.append(("web", self.id_job))

    monkeypatch.setattr(api_module, "get_upload_folder", lambda _session_id: "upload-session", raising=False)
    monkeypatch.setattr(api_module, "prepare_jobs", lambda _email, _jobs: [{"type": "align"}], raising=False)
    monkeypatch.setattr(api_module, "update_files", lambda jobs, upload_folder: launched.append(("files", upload_folder, len(jobs))), raising=False)
    monkeypatch.setattr(api_module, "delete_session", lambda session_id: launched.append(("delete", session_id)), raising=False)
    monkeypatch.setattr(api_module, "MODE", "standalone", raising=False)
    monkeypatch.setattr(
        api_module,
        "JobManager",
        SimpleNamespace(create=lambda id_job, job_type, jobs, email=None, mailer=None: DummyLaunchJob(id_job=id_job, job_type=job_type)),
        raising=False,
    )
    with runtime.app.app_context():
        job = api_module.launch_batch(
            "session-1",
            "dup job",
            "user@example.org",
            1,
            [_make_job_model(job_id="dup job")],
        )
    assert job.id_job == "dup_job_2"
    assert Path(runtime.data_root / "dup_job_2").is_dir()
    assert launched[0][0] == "files"
    assert launched[-1] == ("standalone", "dup_job_2")

    launched.clear()
    monkeypatch.setattr(api_module, "MODE", "webserver", raising=False)
    with runtime.app.app_context():
        job = api_module.launch_batch(
            "session-1",
            "web job",
            "user@example.org",
            1,
            [_make_job_model(job_id="web job")],
        )
    assert job.id_job == "web_job"
    assert Path(runtime.data_root / "web_job").is_dir()
    assert launched[-1] == ("web", "web_job")


def test_script_translation_helper_covers_query_branch():
    job, uploads = _build_align_job_from_script("api-align-local.sh", "align_local")
    assert job.query == uploads["query"].name
    assert job.target == uploads["target"].name


def test_api_helper_functions_cover_additional_edge_cases(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "helper_edges"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()

    class DummySessionModel:
        @staticmethod
        def connect():
            class Ctx:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            return Ctx()

        @staticmethod
        def get(s_id):
            return SimpleNamespace(upload_folder="upload-folder")

    monkeypatch.setattr(api_module, "MODE", "webserver", raising=False)
    monkeypatch.setattr(api_module, "db", SimpleNamespace(Session=DummySessionModel), raising=False)
    assert api_module.get_upload_folder("session-1") == "upload-folder"
    monkeypatch.setattr(api_module, "MODE", "standalone", raising=False)
    assert api_module.get_upload_folder("session-1") == "session-1"

    empty_pointer = job_dir / "pointer.txt"
    empty_pointer.write_text("")
    assert api_module.read_path_pointer(str(empty_pointer)) is None

    generated = job_dir / "generated.fa"
    generated.write_text(">q\nACGT\n")
    marker = job_dir / "marker"
    marker.write_text("marker")
    real_getmtime = api_module.os.path.getmtime
    calls = {"count": 0}

    def flaky_getmtime(path):
        calls["count"] += 1
        if calls["count"] == 2:
            raise FileNotFoundError("gone")
        return real_getmtime(path)

    monkeypatch.setattr(api_module.os.path, "getmtime", flaky_getmtime, raising=False)
    assert api_module.is_file_fresh(str(generated), str(marker)) is False
    monkeypatch.setattr(api_module.os.path, "getmtime", real_getmtime, raising=False)

    monkeypatch.setattr(api_module.Functions, "get_fasta_file", staticmethod(lambda *_args, **_kwargs: None), raising=False)
    assert api_module.find_query_as_reference(job_id) is None

    ghost_query = tmp_path / "ghost" / "query.fa.gz"
    monkeypatch.setattr(api_module.Functions, "get_fasta_file", staticmethod(lambda *_args, **_kwargs: str(ghost_query)), raising=False)
    assert api_module.find_query_as_reference(job_id) is None

    base_query = job_dir / "query.fa"
    base_query.write_text(">q\nACGT\n")
    (job_dir / ".sorted").write_text("")

    sorted_only = job_dir / "query_only_sorted.fa"
    sorted_only.write_text(">q\nTGCA\n")
    monkeypatch.setattr(
        api_module.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(sorted_only) if is_sorted else None),
        raising=False,
    )
    monkeypatch.setattr(api_module, "has_fresh_sorted_query_fasta", lambda _res_dir: True, raising=False)
    assert api_module.get_query_fasta_ready_file(job_id) == str(sorted_only)

    missing_base = job_dir / "missing_base.fa"
    monkeypatch.setattr(
        api_module.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(missing_base) if not is_sorted else None),
        raising=False,
    )
    assert api_module.get_query_fasta_ready_file(job_id) is None

    monkeypatch.setattr(
        api_module.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(base_query) if not is_sorted else None),
        raising=False,
    )
    monkeypatch.setattr(api_module, "has_fresh_sorted_query_fasta", lambda _res_dir: False, raising=False)
    assert api_module.get_query_fasta_ready_file(job_id) is None

    missing_sorted = job_dir / "query.fa.sorted"
    monkeypatch.setattr(api_module, "has_fresh_sorted_query_fasta", lambda _res_dir: True, raising=False)
    monkeypatch.setattr(
        api_module.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(base_query) if not is_sorted else str(missing_sorted)),
        raising=False,
    )
    assert api_module.get_query_fasta_ready_file(job_id) is None

    ready_sorted = job_dir / "query.ready.sorted.fa"
    ready_sorted.write_text(">q\nTGCA\n")
    monkeypatch.setattr(
        api_module.Functions,
        "get_fasta_file",
        staticmethod(lambda _res_dir, _type_f, is_sorted: str(base_query) if not is_sorted else str(ready_sorted)),
        raising=False,
    )
    assert api_module.get_query_fasta_ready_file(job_id) == str(ready_sorted)

    error_file = job_dir / api_module.QUERY_AS_REFERENCE_ERROR
    error_file.write_text("previous failure")
    monkeypatch.setattr(api_module.Functions, "is_file_lock_active", staticmethod(lambda _path: False), raising=False)
    monkeypatch.setattr(api_module, "find_query_as_reference", lambda _job_id: None, raising=False)
    real_open = open

    def broken_open(path, *args, **kwargs):
        if path == str(error_file):
            raise OSError("denied")
        return real_open(path, *args, **kwargs)

    with broken_open(str(base_query), "r") as handle:
        assert handle.readline().startswith(">q")
    monkeypatch.setattr(api_module, "open", broken_open, raising=False)
    status = api_module.get_query_as_reference_export_status(job_id)
    assert status.state == ExportFileState.not_ready
    assert status.message == "Previous build failed. Try again."
    monkeypatch.setattr(api_module, "open", real_open, raising=False)

    pointer_calls = {}
    monkeypatch.setattr(api_module, "build_query_as_reference_file", lambda _job_id: str(job_dir / "query_as_reference.fa"), raising=False)
    monkeypatch.setattr(api_module, "write_path_pointer", lambda pointer, file_path: pointer_calls.update(pointer=pointer, file_path=file_path), raising=False)
    monkeypatch.setattr(api_module.Functions, "release_file_lock", staticmethod(lambda path: pointer_calls.update(lock=path)), raising=False)
    api_module._build_query_as_reference_worker(job_id)
    assert not error_file.exists()
    assert pointer_calls["file_path"].endswith("query_as_reference.fa")
    assert pointer_calls["lock"].endswith(api_module.QUERY_AS_REFERENCE_LOCK)

    monkeypatch.setattr(
        api_module.Functions,
        "get_status",
        staticmethod(
            lambda _job: {
                "id_job": job_id,
                "status": "started",
                "error": "",
                "has_logs": True,
                "mem_peak": "10",
                "time_elapsed": "20",
            }
        ),
        raising=False,
    )
    response = api_module.get_status(SimpleNamespace(job_id=job_id))
    assert response["code"] == 0
    assert response["data"]["job_id"] == job_id


def test_api_dotplot_sort_assoc_and_prepare_error_branches(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "api-errors"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()
    for filename in ("map.paf", "query.idx", "target.idx"):
        (job_dir / filename).write_text("placeholder\n")

    class BrokenPaf:
        def __init__(self, *_args, **_kwargs):
            self.parsed = False
            self.error = "Broken dotplot"

        def sort(self):
            return None

        def reverse_contig(self, *_args):
            return None

        def parse_paf(self, *_args, **_kwargs):
            return None

    broken = BrokenPaf()
    assert broken.sort() is None
    assert broken.reverse_contig("q1") is None
    assert broken.parse_paf() is None

    class MissingPaf:
        def __init__(self, *_args, **_kwargs):
            raise FileNotFoundError("missing")

    monkeypatch.setattr(api_module, "Paf", BrokenPaf, raising=False)
    response = api_module.get_dotplot(SimpleNamespace(job_id=job_id))
    assert response["code"] == 500
    assert response["message"] == "Broken dotplot"

    monkeypatch.setattr(api_module, "Paf", MissingPaf, raising=False)
    response, status = api_module.get_dotplot(SimpleNamespace(job_id=job_id))
    assert status == 404
    assert response["message"] == "Job not found"

    response, status = api_module.sorted_dotplot(SimpleNamespace(job_id=job_id))
    assert status == 500
    assert response["message"] == "Server error"

    (job_dir / ".all-vs-all").write_text("")
    response, status = api_module.post_sort(SimpleNamespace(job_id=job_id))
    assert status == 404
    assert "All-vs-All" in response["message"]
    (job_dir / ".all-vs-all").unlink()

    for filename in (".sorted", "map.paf.sorted", "query.idx.sorted"):
        (job_dir / filename).write_text("")
    response, status = api_module.post_sort(SimpleNamespace(job_id=job_id))
    assert status == 200
    for filename in (".sorted", "map.paf.sorted", "query.idx.sorted"):
        (job_dir / filename).unlink()

    class NoOutputPaf:
        def __init__(self, *_args, **_kwargs):
            self.parsed = True
            self.error = None

        def sort(self):
            return None

    monkeypatch.setattr(api_module, "Paf", NoOutputPaf, raising=False)
    response, status = api_module.post_sort(SimpleNamespace(job_id=job_id))
    assert status == 500
    assert response["message"] == "Sort output was not produced"

    class ErrorPaf(NoOutputPaf):
        def __init__(self, *_args, **_kwargs):
            super().__init__()
            self.parsed = False
            self.error = "Sort failed"

    monkeypatch.setattr(api_module, "Paf", ErrorPaf, raising=False)
    response, status = api_module.post_sort(SimpleNamespace(job_id=job_id))
    assert status == 500
    assert response["message"] == "Sort failed"

    class ResetFailPaf:
        def __init__(self, *_args, **_kwargs):
            self.parsed = False
            self.error = "Reset failed"

    monkeypatch.setattr(api_module, "Paf", ResetFailPaf, raising=False)
    response, status = api_module.post_reset_sort(SimpleNamespace(job_id=job_id))
    assert status == 404
    assert response["message"] == "Reset failed"

    monkeypatch.setattr(api_module, "Paf", MissingPaf, raising=False)
    response, status = api_module.post_reset_sort(SimpleNamespace(job_id=job_id))
    assert status == 404
    assert "doesn't exists" in response["message"]

    (job_dir / ".all-vs-all").write_text("")
    response, status = api_module.post_reverse_contig(SimpleNamespace(job_id=job_id), SimpleNamespace(contig="q1"))
    assert status == 404
    assert "All-vs-All" in response["message"]
    (job_dir / ".all-vs-all").unlink()

    class ReverseFailPaf:
        def __init__(self, *_args, **_kwargs):
            self.parsed = False
            self.error = "Reverse failed"

        def reverse_contig(self, *_args):
            return None

    monkeypatch.setattr(api_module, "Paf", ReverseFailPaf, raising=False)
    response, status = api_module.post_reverse_contig(SimpleNamespace(job_id=job_id), SimpleNamespace(contig="q1"))
    assert status == 404
    assert response["message"] == "Reverse failed"

    monkeypatch.setattr(api_module, "Paf", MissingPaf, raising=False)
    response, status = api_module.post_reverse_contig(SimpleNamespace(job_id=job_id), SimpleNamespace(contig="q1"))
    assert status == 404
    assert "doesn't exists" in response["message"]

    assert api_module.post_free_noise(SimpleNamespace(job_id=job_id), SimpleNamespace())[1] == 501

    response, status = api_module.get_qt_assoc(SimpleNamespace(job_id="missing"))
    assert status == 404
    monkeypatch.setattr(api_module, "Paf", MissingPaf, raising=False)
    response, status = api_module.get_qt_assoc(SimpleNamespace(job_id=job_id))
    assert status == 404
    response, status = api_module.get_dl_qt_assoc(SimpleNamespace(job_id=job_id))
    assert status == 404
    response, status = api_module.post_no_assoc(SimpleNamespace(job_id=job_id), NoAssocInput(which="query"))
    assert status == 404
    response, status = api_module.post_dl_no_assoc(SimpleNamespace(job_id=job_id), NoAssocInput(which="query"))
    assert status == 404
    assert api_module.get_dl_qt_assoc(SimpleNamespace(job_id="missing"))[1] == 404
    assert api_module.post_no_assoc(SimpleNamespace(job_id="missing"), NoAssocInput(which="query"))[1] == 404
    assert api_module.post_dl_no_assoc(SimpleNamespace(job_id="missing"), NoAssocInput(which="query"))[1] == 404

    monkeypatch.setattr(api_module, "build_fasta", lambda *_args, **_kwargs: (1, False), raising=False)
    response, status = api_module.prepare_fasta_query(SimpleNamespace(job_id=job_id), PrepareFastaInput(gzip=False))
    assert status == 200
    assert str(response["data"]["status"]).lower() in {"preparefastaenum.in_progress", "in_progress"}

    monkeypatch.setattr(api_module, "build_fasta", lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("missing query")), raising=False)
    response, status = api_module.prepare_fasta_query(SimpleNamespace(job_id=job_id), PrepareFastaInput(gzip=False))
    assert status == 404
    assert response["code"] == 2


def test_api_download_and_example_remaining_branches(monkeypatch, tmp_path):
    import dgenies.api as api_module

    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    job_id = "download_edges"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()
    (job_dir / "map.paf").write_text("map")
    (job_dir / "query.idx").write_text("query")

    response, status = api_module.get_backup(SimpleNamespace(job_id=job_id))
    assert status == 404
    assert "target.idx" in response["message"]

    (job_dir / "target.idx").write_text("target")
    monkeypatch.setattr(api_module, "send_download", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")), raising=False)
    response, status = api_module.get_backup(SimpleNamespace(job_id=job_id))
    assert status == 500

    monkeypatch.setattr(
        api_module,
        "get_query_as_reference_export_status",
        lambda _job_id: api_module.create_export_file_status(ExportFileState.building, message="running"),
        raising=False,
    )
    response, status = api_module.get_query_as_reference(SimpleNamespace(job_id=job_id))
    assert status == 409
    assert response["message"] == "running"

    monkeypatch.setattr(
        api_module,
        "get_query_as_reference_export_status",
        lambda _job_id: api_module.create_export_file_status(ExportFileState.not_ready, message="Build first"),
        raising=False,
    )
    response, status = api_module.get_query_as_reference(SimpleNamespace(job_id=job_id))
    assert status == 404
    assert response["message"] == "Build first"

    monkeypatch.setattr(
        api_module,
        "get_query_as_reference_export_status",
        lambda _job_id: api_module.create_export_file_status(ExportFileState.ready, filename="query_as_reference.fa"),
        raising=False,
    )
    monkeypatch.setattr(api_module, "find_query_as_reference", lambda _job_id: None, raising=False)
    response, status = api_module.get_query_as_reference(SimpleNamespace(job_id=job_id))
    assert status == 404
    assert "not available" in response["message"]
    assert api_module.get_query_as_reference(SimpleNamespace(job_id="missing"))[1] == 404

    response, status = api_module.get_dl_fasta_query(SimpleNamespace(job_id="missing"))
    assert status == 404

    monkeypatch.setattr(
        api_module,
        "get_query_fasta_export_status",
        lambda _job_id: api_module.create_export_file_status(ExportFileState.not_ready, message="Prepare first"),
        raising=False,
    )
    response, status = api_module.get_dl_fasta_query(SimpleNamespace(job_id=job_id))
    assert status == 404
    assert response["message"] == "Prepare first"

    monkeypatch.setattr(
        api_module,
        "get_query_fasta_export_status",
        lambda _job_id: api_module.create_export_file_status(ExportFileState.ready, filename="query.fa.gz"),
        raising=False,
    )
    monkeypatch.setattr(api_module, "get_query_fasta_ready_file", lambda _job_id: None, raising=False)
    response, status = api_module.get_dl_fasta_query(SimpleNamespace(job_id=job_id))
    assert status == 404
    assert "not available" in response["message"]

    monkeypatch.setattr(api_module.Functions, "is_file_lock_active", staticmethod(lambda _path: False), raising=False)
    monkeypatch.setattr(api_module, "get_query_fasta_ready_file", lambda _job_id: str(job_dir / "missing.fa"), raising=False)
    response, status = api_module.get_fasta_query(SimpleNamespace(job_id=job_id))
    assert status == 404

    monkeypatch.setattr(
        api_module,
        "start_query_as_reference_build",
        lambda _job_id: SimpleNamespace(state="unexpected", message="worker failed"),
        raising=False,
    )
    response, status = api_module.post_build_query_as_reference(SimpleNamespace(job_id=job_id))
    assert status == 500
    assert response["message"] == "worker failed"

    monkeypatch.setattr(
        api_module,
        "config_reader",
        SimpleNamespace(example_backup="/tmp/backup.tar.gz", example_query="/tmp/query.fa.gz", example_target=""),
        raising=False,
    )
    response, status = api_module.get_example_files()
    assert status == 200
    assert response["data"] == ["example://backup.tar.gz", "example://query.fa.gz"]
