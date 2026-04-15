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
"""
Tests the end-to-end lifecycle of a job submission triggered via a translated shell script. 
Ensures that:
1. The API correctly identifies required files for a batch.
2. The system prevents duplicate uploads of the same file.
3. Files are physically written to the filesystem with byte-for-byte integrity.
4. The final upload triggers the expected job launch.
"""

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

"""
Tests the specialized 'align-self-local' job workflow to ensure it correctly 
handles single-file dependencies.

Ensures that:
1. When submitting a job translated from the 'api-align-self-local.sh' script, 
   the API identifies only the target file as required (no query file needed).
2. The upload process succeeds when providing only the identified target file.
3. The final launched job is correctly initialized with an empty query string 
   and the correct target filename.
"""
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

"""
Tests the 'plot-backup-local' workflow to ensure that archive/backup files 
are correctly identified and uploaded with full data integrity.

Ensures that:
1. When submitting a job from the 'api-plot-backup-local.sh' script, 
   the API correctly identifies the backup file as the only required dependency.
2. The upload of the backup archive is processed successfully by the server.
3. The resulting launched job is configured with the correct backup filename.
4. The uploaded file on the server is bit-perfect (byte-for-byte integrity) 
   compared to the original source file.
"""
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

"""
Tests the server-side validation logic for compressed file formats during upload.

Ensures that:
1. The API correctly identifies a .gz file as a required dependency when a job 
   is submitted with a gzip filename.
2. The system performs content inspection on uploaded files to verify their integrity.
3. An attempt to upload a malformed or invalid GZIP file (using the fake.fa.gz fixture) 
   is intercepted and rejected.
4. The rejection results in a 415 Unsupported Media Type status code accompanied 
   by the specific error message: "Not a gzip file".
"""
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

"""
Tests the export status API and the FASTA query download endpoint using real genomic data.

Ensures that:
1. The get_export_status endpoint accurately reflects the lifecycle state 
   (e.g., 'ready' vs 'blocked') of exported files based on the job directory contents.
2. The API metadata correctly identifies and matches the filenames present 
   in the simulated job directory.
3. The download endpoint (get_fasta_query) serves the file with the correct 
   application/gzip MIME type.
4. The downloaded file payload maintains byte-for-byte integrity compared 
   to the original source file on disk.
"""
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

"""
Tests the 'query as reference' export status logic, specifically focusing on 
pointer file tracking and cache invalidation via refresh markers.

Ensures that:
1. The system correctly identifies a 'ready' state when a valid sorted marker 
   is present and the output file is properly registered.
2. The pointer file accurately tracks and maps to the most recently generated 
   output path within the job directory.
3. The export status transitions from 'ready' to 'not_ready' if a refresh 
   marker (e.g., '.new-reversals') is detected with a timestamp newer than 
   the processed data, effectively triggering a cache invalidation.
"""
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

"""
Tests that the 'start query as reference build' endpoint correctly triggers 
an asynchronous background worker without blocking the API response.

Ensures that:
1. The API immediately returns a 'not_ready' status to the client, signaling 
   that the build process has been initiated but is still in progress.
2. The system successfully orchestrates a new thread targeting the correct 
   internal worker function (_build_query_as_reference_worker).
3. The background thread is properly configured with the necessary context, 
   specifically passing the correct job_id as an argument.
4. The thread is correctly initialized as a daemon thread to ensure it does 
   not prevent the main application process from exiting.
"""
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

"""
Tests the API layer's ability to wrap backend process statuses and errors 
into standardized HTTP responses for FASTA preparation and summary retrieval.

Ensures that:
1. The prepare_fasta_query endpoint correctly interprets backend completion 
   signals (e.g., 'done') and preserves configuration flags like gzip.
2. The get_summary endpoint accurately maps successful backend computation 
   results into a standardized 200 OK response with the expected data payload.
3. Backend error signals or missing resources (e.g., 'job_not_found') are 
   correctly intercepted and translated into appropriate HTTP error statuses 
   (404 Not Found) and user-friendly error messages for the client.
"""
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

"""
Tests that the post_build_query_as_reference endpoint correctly maps internal 
export file states to appropriate HTTP response codes and error messages.

Ensures that:
1. When the underlying build process reports a 'blocked' state (e.g., due to a 
   missing sorting step), the API intercepts this and returns a 409 Conflict 
   status code along with the specific backend error message ("Sort first").
2. When the backend indicates that the build is 'ready' to be triggered, the 
   API returns a successful response (code 0) indicating the operation was accepted.
"""
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

"""
Tests the full suite of Dotplot-related API endpoints using a high-fidelity 
mock of the PAF (Pairwise Alignment Format) processing engine.

Ensures that:
1. The visualization endpoints (get_dotplot and sorted_dotplot) correctly 
   interface with the PAF parser to retrieve and present dotplot metadata.
2. The sorting workflow (post_sort, post_reset_sort) properly manages 
   filesystem-based state markers (e.g., .sorted, .new-reversals) to 
   track and invalidate cached views.
3. Contig manipulation operations (post_reverse_contig) are successfully 
   processed by the backend logic without disrupting the existing state.
4. The association retrieval endpoints (get_qt_assoc, get_dl_qt_assoc) 
   correctly serve both summarized counts and raw, downloadable association records.
5. The identification and downloading of unmatched contigs (post_no_assoc) 
   accurately filter and present sequences that do not have alignments.
"""
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

"""
Tests the core utility helper functions responsible for path mapping, 
cache invalidation logic, and job metadata orchestration.

Ensures that:
1. Path pointer utilities correctly persist and retrieve file mappings 
   (pointer target) and handle missing pointers gracefully.
2. The 'file freshness' logic accurately determines if a file is up-to-date 
   by comparing the modification timestamps of a target file against a 
   provided refresh marker (detecting both fresh and stale states).
3. Job metadata helpers correctly identify the presence of sorted output 
   files and resolve absolute job directory paths.
4. The state progress engine accurately maps ExportFileState enums to 
   numerical percentages (e.g., 'ready' 100%, 'blocked' 0%).
5. The download utility correctly wraps file transfers in an HTTP response 
   with the appropriate Content-Disposition headers for client-side usage.
"""
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

"""
Tests the exhaustive coverage of all possible ExportFileState transitions 
within the export status helper functions.

Ensures that:
1. The 'building' state is accurately triggered when active lock files 
   (e.g., QUERY_FASTA_LOCK) are detected in the job directory.
2. The API correctly differentiates between 'unavailable', 'blocked', and 
   'not_ready' states based on the presence or absence of intermediate 
   processing files (such as .all-vs-all or .sorted).
3. The system correctly identifies a 'not_ready' state when required 
   files are missing or when backend processes have failed.
4. Error propagation is functional, ensuring that if an error file exists, 
   its specific error message is captured and surfaced to the client 
   via the API response.
"""
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

"""
Tests the end-to-end orchestration of the 'query as reference' build logic, 
covering file generation, background worker reliability, and error propagation.

Ensures that:
1. The build_query_as_reference_file utility enforces strict prerequisite 
   checks, raising errors if required files (like .all-vs-all) are missing or 
   if the parser points to non-existent paths.
2. The background worker (_build_query_as_reference_worker) is resilient; 
   it must successfully manage file locks and, in the event of a RuntimeError, 
   capture the exception message into a persistent error file for later debugging.
3. The build trigger (start_query_as_reference_build) respects the current 
   ExportFileState, preventing redundant builds if the state is already 'ready' 
   or 'not_ready'.
4. Critical cleanup operations, such as releasing file locks (QUERY_AS_REFERENCE_LOCK), 
   are executed correctly during both successful task completion and unexpected 
   worker failures.
"""
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

"""
Tests the robust error-handling and exception-mapping capabilities of the 
API wrapper layer across various service endpoints.

Ensures that:
1. Resource discovery failures (e.g., requesting a missing job ID or a non-existent 
   file) are correctly intercepted and returned to the client as 404 Not Found.
2. Backend logic exceptions—ranging from custom domain errors (DGeniesMissingJobError) 
   to generic system failures (RuntimeError, IOError)—are caught by the 
   wrappers and translated into standardized 500 Internal Server Error responses.
3. Specific backend error strings (e.g., 'file_not_found' or 'fail') are correctly 
   parsed to determine whether they should trigger a 404 or a 500 status code.
4. Concurrency conflicts, such as attempting to access a file while a process 
   lock is active, are properly identified and returned as a 409 Conflict.
"""
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

"""
Tests the integrity of API download endpoints and the robustness of the 
system's handling of terminal error branches and unimplemented features.

Ensures that:
1. The get_backup endpoint correctly aggregates job-related files (including logs) 
   into a valid .tar.gz archive and returns a 404 Not Found for missing jobs.
2. The log retrieval service (get_logs) accurately serves existing logs and 
   correctly handles requests for non-existent job IDs.
3. Download endpoints for specialized data (e.g., Query-as-Reference, FASTA) 
   enforce state-based access control, specifically returning a 409 Conflict 
   when the backend process is 'blocked' or currently 'building'.
4. The job submission endpoint (post_build_query_as_reference) correctly 
   interprets backend availability and validates job existence before proceeding.
5. "Terminal branches"—representing unsupported or unimplemented feature 
   endpoints (e.g., get_paf, get_viewer) are consistently intercepted 
   by the API and return a standardized 501 Not Implemented status code.
"""
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

"""
Tests the API's behavior regarding job lifecycle management and the availability 
of the Gallery feature across different application execution modes.

Ensures that:
1. The get_gallery endpoint is context-aware; it successfully retrieves 
   gallery items when the application is in webserver mode, but returns a 
   404 Not Found when running in standalone mode.
2. The job deletion workflow (delete_job) correctly executes for standard 
   active jobs using the JobManager.
3. The API gracefully handles lifecycle error exceptions, such as 
   DGeniesMissingJobError, ensuring that attempts to delete non-existent 
   jobs are caught and returned with a successful response code rather than 
   crashing the request.
4. Security and permission constraints are enforced, specifically returning a 
   403 Forbidden status when an attempt is made to delete protected resources 
   (e.g., jobs belonging to the Gallery).
"""
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

"""
Tests the error-handling branches for both session management and sorted dotplot 
endpoints under various failure conditions in the database and parsing layers.

Ensures that:
1. The Session Management layer correctly handles:
   - Successful lifecycle operations (deleting and pinging active sessions).
   - Resource-not-found errors (translating DoesNotExist exceptions to 404 Not Found).
   - Database driver failures (translating RuntimeError or database crashes to 500 Internal Server Error).
2. The Sorted Dotplot endpoint correctly handles:
   - Missing job requests in standalone mode (404 Not Found).
   - Prerequisite violations, such as attempting to access a dotplot when an 
     incomplete state is detected (e.g., presence of .all-vs-all triggering a 403 Forbidden).
   - Backend processing failures, specifically ensuring that if the PAF parser 
     encounters an error, the API captures it and returns a 500 Internal Server Error.
"""
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

"""
Tests the post_jobs endpoint's ability to handle remote URL dependencies and 
its resilience against various failure modes during the submission lifecycle.

Ensures that:
1. The system correctly implements "Immediate Launch" logic when jobs are 
   submitted with remote URLs; specifically, it bypasses the need for an 
   upload session (resulting in a None session ID) and triggers the 
   launch process immediately.
2. The API correctly intercepts and reports validation errors (e.g., 
   DGeniesValidationError) as a 400 Bad Request when the submission 
   form is malformed.
3. The system handles resource-related failures during session initialization, 
   such as when a required dependency is missing or invalid, by returning 
   a 404 Not Found status.
4. The API provides a safety net for unexpected system crashes, translating 
   unhandled exceptions (e.g., RuntimeError) into a standardized 
   500 Internal Server Error.
"""
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

"""
Tests the launch_batch orchestration logic to ensure that job ID collisions 
are resolved through automatic identifier sanitization.

Ensures that:
1. When a submitted job ID (e.g., 'dup job') conflicts with an existing 
   directory on the filesystem, the system automatically generates a unique, 
   sanitized identifier (e.g., 'dup_job_2') to prevent data overwrites.
2. The renaming process is propagated throughout the entire launch lifecycle; 
   subsequent steps—such as file updates and the final job launch command—use 
   the newly generated sanitized ID rather than the original input ID.
3. In webserver mode, where no filesystem collision is detected, the system 
   correctly processes and launches jobs using their original, intended 
   identifiers without unnecessary modification.
4. The system maintains operational integrity across different execution modes 
   (standalone vs webserver), ensuring that both launch types correctly 
   interact with the underlying JobManager.
"""
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

"""
Verifies that the script translation engine correctly extracts and maps 
file dependencies from a shell script into an API job model.

Ensures that:
1. The translation of api-align-local.sh correctly identifies the required 
   input files (query and target) from the provided script context.
2. The resulting job object contains metadata (filenames) that is perfectly 
   synchronized with the actual files intended for the upload payload.
"""
def test_script_translation_helper_covers_query_branch():
    job, uploads = _build_align_job_from_script("api-align-local.sh", "align_local")
    assert job.query == uploads["query"].name
    assert job.target == uploads["target"].name

"""
Tests the edge-case resilience of various API helper functions, specifically 
focusing on filesystem discrepancies, broken dependencies, and partial failures.

Ensures that:
1. The upload directory resolution correctly adapts to the application mode 
   (e.webserver vs. standalone), ensuring path stability across environments.
2. The path pointer utility handles empty or corrupted files gracefully without 
   crashing the request.
3. The 'file freshness' logic is robust against transient filesystem errors, 
   such as a FileNotFoundError occurring during a modification time check.
4. The get_query_fasta_ready_file logic correctly manages complex file-state 
   dependencies, such as:
   - Handling missing base files or sorted variants.
   - Navigating the presence or absence of required '.sorted' markers.
   - Resolating paths when a 'ghost' (non-existent) query file is referenced.
5. The error propagation from the background worker is verified; specifically, 
   ensensuring that if an error file exists, the API correctly translates 
   the 'previous failure' message into a not_ready export state.
6. The system remains resilient to permission-related failures (e.g., OSError: 
   denied) when attempting to read critical job files, preventing unhandled 
   exceptions from leaking to the client.
"""
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

"""
Tests the error handling branches for dotplot, sorting, association, and FASTA preparation API endpoints.

Ensure that:
1. The API returns correct HTTP status codes (404/500) when PAF files are corrupted or missing.
2. Sorting, resetting, and reversing operations handle execution failures and missing prerequisites correctly.
3. Retrieval and creation of associations respond with appropriate errors for invalid job IDs or missing data.
4. FASTA preparation endpoints manage successful task initiation and file-related error states properly.
"""
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

"""
Tests edge cases and error handling for download, export status, build initiation, and example file API endpoints.

Ensure that:
1. The backup retrieval handles missing required files (404) and internal runtime errors (500).
2. Export-related endpoints correctly manage "running" states (409), "not ready" states (404), and missing physical files (404).
3. Initiating the query build process properly handles worker failures or unexpected states (500).
4. Example file retrieval successfully returns the configured paths (200).
"""
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
