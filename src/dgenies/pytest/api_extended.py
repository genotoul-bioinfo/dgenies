"""Additional API tests covering upload, form, and launch edge cases."""
from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from dgenies.api.datamodels import BatchSubmissionQuery, Job
from dgenies.lib.exceptions import (
    DGeniesExampleInvalid,
    DGeniesUnknownToolError,
    DGeniesValidationError,
)
from dgenies.pytest.helpers import (
    TESTS_DATA_DIR,
    _install_fake_tools,
    _make_job_model,
    _make_upload_form,
    _setup_api_runtime,
)

def _write_jobs_json(folder: Path, batch: BatchSubmissionQuery) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "jobs.json").write_text(json.dumps(batch.model_dump()))

# Verifies that the file upload API correctly handles edge cases such as empty uploads, 
# server-side errors due to missing directories, unsupported file extensions, and files exceeding size limits.
def test_api_upload_file_handles_missing_folder_invalid_type_size_and_no_file(monkeypatch, tmp_path):
    import dgenies.api as api_module
    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    target_fixture = TESTS_DATA_DIR / "backup.tar.gz"
    job = _make_job_model(query="", target=target_fixture.name, target_type="local", tool="minimap2")
    batch = BatchSubmissionQuery(batch_id="upload-branches", email="upload@example.org", nb_jobs=1, jobs=[job])
    with runtime.app.app_context():
        response, status = api_module.upload_file(SimpleNamespace(session_id="no-file", file=None))
        assert status == 404
        assert response["message"] == "No file provided"
        response, status = api_module.upload_file(_make_upload_form("missing-folder", target_fixture))
        assert status == 500
        assert "unexpected error" in response["message"].lower()
        session_dir = runtime.upload_root / "type-check"
        _write_jobs_json(session_dir, batch)
        monkeypatch.setattr(api_module, "allowed_file_ext", lambda *_args: False, raising=False)
        response, status = api_module.upload_file(_make_upload_form("type-check", target_fixture, "application/gzip"))
        assert status == 415
        assert response["message"] == "File type not allowed"
        session_dir = runtime.upload_root / "too-large"
        _write_jobs_json(session_dir, batch)
        monkeypatch.setattr(api_module, "allowed_file_ext", lambda *_args: True, raising=False)
        monkeypatch.setattr(api_module.Functions, "is_gz_file", staticmethod(lambda _path: True), raising=False)
        monkeypatch.setattr(api_module, "get_max_file_size", lambda *_args: 1, raising=False)
        response, status = api_module.upload_file(_make_upload_form("too-large", target_fixture, "application/gzip"))
        assert status == 413
        assert response["message"] == "File too large"

# Tests the validation logic for various job types (align and plot) and batch submissions, 
# ensuring required fields are present, unsupported types are rejected, and job preparation utilities work correctly.
def test_api_validation_form_helpers_and_prepare_jobs_cover_remaining_branches(monkeypatch):
    import dgenies.api as api_module
    _install_fake_tools(monkeypatch, api_module)
    monkeypatch.setattr(api_module.Functions, "is_email_mandatory", staticmethod(lambda: True), raising=False)
    with pytest.raises(DGeniesValidationError, match="'target' is required"):
        api_module.valid_align(_make_job_model(target=""))
    no_target_type = _make_job_model()
    no_target_type.target_type = None
    with pytest.raises(DGeniesValidationError, match="'target_type' is required"):
        api_module.valid_align(no_target_type)
    no_query_type = _make_job_model()
    no_query_type.query_type = None
    with pytest.raises(DGeniesValidationError, match="'query_type' is required"):
        api_module.valid_align(no_query_type)
    backup_missing_target_type = _make_job_model(type="plot", backup="backup.tar.gz")
    backup_missing_target_type.target_type = None
    with pytest.raises(DGeniesValidationError, match="'target_type' is required"):
        api_module.valid_plot(backup_missing_target_type)
    backup_missing_query_type = _make_job_model(type="plot", backup="backup.tar.gz")
    backup_missing_query_type.query_type = None
    with pytest.raises(DGeniesValidationError, match="'query_type' is required"):
        api_module.valid_plot(backup_missing_query_type)
    with pytest.raises(DGeniesValidationError, match="'target' is required"):
        api_module.valid_plot(_make_job_model(type="plot", target="", query="", align="", backup=""))
    missing_plot_target_type = _make_job_model(type="plot", target="target.fa.gz", query="query.fa.gz", align="map.paf")
    missing_plot_target_type.target_type = None
    with pytest.raises(DGeniesValidationError, match="'target_type' is required"):
        api_module.valid_plot(missing_plot_target_type)
    with pytest.raises(DGeniesValidationError, match="'query' is required"):
        api_module.valid_plot(_make_job_model(type="plot", query="", align="map.paf"))
    missing_plot_query_type = _make_job_model(type="plot", target="target.fa.gz", query="query.fa.gz", align="map.paf")
    missing_plot_query_type.query_type = None
    with pytest.raises(DGeniesValidationError, match="'query_type' is required"):
        api_module.valid_plot(missing_plot_query_type)
    with pytest.raises(DGeniesValidationError, match="'align' is required"):
        api_module.valid_plot(_make_job_model(type="plot", align=""))
    missing_align_type = _make_job_model(type="plot", align="map.paf")
    missing_align_type.align_type = None
    with pytest.raises(DGeniesValidationError, match="'align_type' is required"):
        api_module.valid_plot(missing_align_type)
    unsupported = _make_job_model()
    unsupported.type = "analysis"
    with pytest.raises(DGeniesValidationError, match="not supported"):
        api_module.valid_job(unsupported)
    with pytest.raises(DGeniesValidationError, match="Incorrect number of jobs"):
        api_module.valid_form(BatchSubmissionQuery(batch_id="batch", email="ok@example.org", nb_jobs=2, jobs=[_make_job_model()]))
    with pytest.raises(DGeniesValidationError, match="No job provided"):
        api_module.valid_form(BatchSubmissionQuery(batch_id="batch", email="ok@example.org", nb_jobs=0, jobs=[]))
    with pytest.raises(DGeniesValidationError, match="Batch id is required"):
        api_module.valid_form(BatchSubmissionQuery(batch_id="", email="ok@example.org", nb_jobs=2, jobs=[_make_job_model(), _make_job_model(job_id="job-2")]))
    plot_job = Job(
        job_id="plot-backup",
        type="plot",
        query="",
        query_type="local",
        target="",
        target_type="local",
        align="",
        align_type="local",
        backup="backup.tar.gz",
        backup_type="url",
        tool=None,
        tool_options=[],
    )
    assert list(api_module.get_file_role(_make_job_model(), file_types=["local"])) == [
        ("query.fa.gz", "query"),
        ("target.fa.gz", "target"),
    ]
    assert list(api_module.get_file_role(plot_job, file_types=["url"])) == [("backup.tar.gz", "backup")]
    with pytest.raises(DGeniesUnknownToolError):
        api_module.get_tools_options(None, [])
    prepared_job = Job(
        job_id="prepared-job",
        type="align",
        query="query.fa.gz",
        query_type="local",
        target="target.fa.gz",
        target_type="local",
        align="",
        align_type="local",
        backup="",
        backup_type="local",
        tool="minimap2",
        tool_options=["repeat:few", "preset:default"],
    )
    prepared = api_module.prepare_jobs("batch@example.org", [prepared_job])
    assert prepared[0]["email"] == "batch@example.org"
    assert prepared[0]["query"] == "query.fa.gz"
    assert prepared[0]["options"] == "--repeat:few --preset:default"

# Verifies the complete lifecycle of job submission and execution, including posting jobs 
# via API (handling URL inputs and errors), launching batches in standalone/webserver modes, 
# and the accuracy of status reporting and output file detection helpers.
def test_api_post_jobs_launch_batch_and_status_helpers(monkeypatch, tmp_path):
    import dgenies.api as api_module
    runtime = _setup_api_runtime(monkeypatch, tmp_path)
    _install_fake_tools(monkeypatch, api_module)
    monkeypatch.setattr(api_module.Functions, "is_email_mandatory", staticmethod(lambda: False), raising=False)
    launched = {}
    deleted_sessions = []
    class DummyManager:
        def __init__(self, job_id):
            self.id_job = job_id
        def get_subjob_ids(self):
            return []
        def launch_standalone(self):
            launched["mode"] = "standalone"
        def launch(self):
            launched["mode"] = "webserver"
    monkeypatch.setattr(api_module, "delete_session", lambda session_id: deleted_sessions.append(session_id), raising=False)
    monkeypatch.setattr(api_module, "update_files", lambda legacy_jobs, upload_folder: launched.update(legacy_jobs=legacy_jobs, upload_folder=upload_folder), raising=False)
    monkeypatch.setattr(api_module.JobManager, "create", staticmethod(lambda **kwargs: DummyManager(kwargs["id_job"])), raising=False)
    real_launch_batch = api_module.launch_batch
    url_job = Job(
        job_id="url-job",
        type="align",
        query="https://example.org/query.fa.gz",
        query_type="url",
        target="https://example.org/target.fa.gz",
        target_type="url",
        align="",
        align_type="local",
        backup="",
        backup_type="local",
        tool="minimap2",
        tool_options=["repeat:few"],
    )
    batch = BatchSubmissionQuery(batch_id="url-batch", email="url@example.org", nb_jobs=1, jobs=[url_job])
    monkeypatch.setattr(api_module.Functions, "create_session", staticmethod(lambda: "url-session"), raising=False)
    with runtime.app.app_context():
        response, status = api_module.post_jobs(batch)
    assert status == 200
    assert response["data"]["session_id"] is None
    assert response["data"]["job_ids"] == ["url-job"]
    assert deleted_sessions == ["url-session", "url-session"]
    assert launched["upload_folder"].endswith("url-session")
    bad_form = BatchSubmissionQuery(batch_id="bad", email="broken@example.org", nb_jobs=2, jobs=[url_job])
    with runtime.app.app_context():
        response, status = api_module.post_jobs(bad_form)
    assert status == 400
    assert response["message"].startswith("Incorrect form:")
    monkeypatch.setattr(api_module, "launch_batch", lambda *_args: (_ for _ in ()).throw(DGeniesExampleInvalid("missing.fa.gz")), raising=False)
    with runtime.app.app_context():
        response, status = api_module.post_jobs(batch)
    assert status == 404
    assert response["message"] == "Invalid example: example://missing.fa.gz"
    monkeypatch.setattr(api_module.Functions, "create_session", staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("boom"))), raising=False)
    with runtime.app.app_context():
        response, status = api_module.post_jobs(batch)
    assert status == 500
    assert "job creation" in response["message"].lower()
    launch_session = "launch-session"
    monkeypatch.setattr(api_module, "launch_batch", real_launch_batch, raising=False)
    monkeypatch.setattr(api_module.Functions, "create_session", staticmethod(lambda: launch_session), raising=False)
    job = Job(
        job_id="job",
        type="align",
        query="query.fa.gz",
        query_type="local",
        target="target.fa.gz",
        target_type="local",
        align="",
        align_type="local",
        backup="",
        backup_type="local",
        tool="minimap2",
        tool_options=["repeat:few", "preset:default"],
    )
    with runtime.app.app_context():
        manager = api_module.launch_batch(launch_session, "Batch Job", "launch@example.org", 1, [job])
    assert manager.id_job == "job"
    assert launched["mode"] == "standalone"
    monkeypatch.setattr(api_module, "MODE", "webserver", raising=False)
    monkeypatch.setattr(api_module, "get_upload_folder", lambda session_id: session_id, raising=False)
    with runtime.app.app_context():
        manager = api_module.launch_batch(launch_session, "Batch Job", "launch@example.org", 2, [job, job])
    assert manager.id_job.startswith("Batch_Job")
    assert launched["mode"] == "webserver"
    with runtime.app.app_context():
        with pytest.raises(BaseException, match="No job provided"):
            api_module.launch_batch("empty", "batch", "none@example.org", 0, [])
    percentages = {
        "getfiles": 3.7,
        "waiting": 7,
        "preparing": 10.7,
        "prepared": 20.4,
        "scheduled": 30.3,
        "starting": 35.2,
        "started": 40.3,
        "succeed": 75.0,
        "merging": 80.4,
        "success": 100,
        "unknown": 0,
    }
    for status_name, expected in percentages.items():
        assert api_module.get_percentage(status_name) == expected
    job_status = api_module.create_job_status(
        {
            "id_job": "status-job",
            "status": "started",
            "error": "",
            "has_logs": True,
            "mem_peak": "12",
            "time_elapsed": "34",
        }
    )
    assert job_status.percent == 40.3
    assert job_status.error is None
    job_dir = runtime.data_root / "sorted-job"
    job_dir.mkdir()
    for filename in (".sorted", "map.paf.sorted", "query.idx.sorted"):
        (job_dir / filename).write_text("")
    assert api_module.has_sorted_output("sorted-job") is True
