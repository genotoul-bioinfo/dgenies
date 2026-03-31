"""Integration tests for Flask views and user-facing workflows."""

from __future__ import annotations

import importlib
import json
import os
import sys
import tarfile
from io import BytesIO
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

import pytest
from flask import Flask
from werkzeug.datastructures import ImmutableMultiDict
from werkzeug.exceptions import Forbidden, NotFound

from dgenies.lib.datafile import DataFile
from dgenies.lib.exceptions import (
    DGeniesDeleteGalleryJobForbidden,
    DGeniesExampleInvalid,
    DGeniesMissingJobError,
)
from dgenies.pytest.helpers import REPO_ROOT, TESTS_DATA_DIR, TESTS_ENSEMBL_DIR


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _setup_views_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str = "standalone") -> SimpleNamespace:
    import dgenies

    app = Flask(__name__)
    upload_root = tmp_path / "uploads"
    data_root = tmp_path / "jobs"
    config_dir = tmp_path / "config"
    upload_root.mkdir()
    data_root.mkdir()
    config_dir.mkdir()
    app.config["UPLOAD_FOLDER"] = str(upload_root)

    query_example = next(TESTS_ENSEMBL_DIR.glob("*.ASM584v2.dna.toplevel.fa.gz"))
    target_example = next(TESTS_ENSEMBL_DIR.glob("*.ASM886v2.dna.toplevel.fa.gz"))
    backup_example = TESTS_DATA_DIR / "backup.tar.gz"
    batch_example = TESTS_DATA_DIR / "batch_examples.txt"
    legal_page = config_dir / "terms.md"
    legal_page.write_text("# Terms\n\nExample legal page.\n")

    config_reader = SimpleNamespace(
        config_dir=str(config_dir),
        app_data=str(data_root),
        upload_folder=str(upload_root),
        max_upload_file_size=25 * 1024 * 1024,
        max_upload_size_ava=50 * 1024 * 1024,
        max_upload_size=75 * 1024 * 1024,
        cluster_walltime_prepare="00:30:00",
        cluster_walltime_align="04:00:00",
        example_target=str(target_example),
        example_query=str(query_example),
        example_backup=str(backup_example),
        example_batch=str(batch_example),
        max_nb_jobs_in_batch_mode=5,
        cookie_wall=False,
        legal={"terms": str(legal_page)},
        allowed_ip_tests=["127.0.0.1"],
    )

    monkeypatch.setattr(dgenies, "app", app, raising=False)
    monkeypatch.setattr(dgenies, "app_title", "D-Genies Tests", raising=False)
    monkeypatch.setattr(dgenies, "app_folder", str(REPO_ROOT / "src" / "dgenies"), raising=False)
    monkeypatch.setattr(dgenies, "config_reader", config_reader, raising=False)
    monkeypatch.setattr(dgenies, "mailer", SimpleNamespace(name="mailer"), raising=False)
    monkeypatch.setattr(dgenies, "APP_DATA", str(data_root), raising=False)
    monkeypatch.setattr(dgenies, "MODE", mode, raising=False)
    monkeypatch.setattr(dgenies, "DEBUG", False, raising=False)
    monkeypatch.setattr(dgenies, "VERSION", "1.5.0-test", raising=False)

    if mode == "webserver":
        fake_database = ModuleType("dgenies.database")
        fake_database.Session = type("Session", (), {"connect": classmethod(lambda cls: _NullContext())})
        fake_database.Gallery = type("Gallery", (), {})
        monkeypatch.setitem(sys.modules, "dgenies.database", fake_database)

    sys.modules.pop("dgenies.views", None)
    views = importlib.import_module("dgenies.views")

    render_calls: list[tuple[str, dict]] = []

    def fake_render(template: str, **context):
        render_calls.append((template, context))
        return {"template": template, "context": context}

    monkeypatch.setattr(views, "render_template", fake_render, raising=False)

    return SimpleNamespace(
        app=app,
        views=views,
        upload_root=upload_root,
        data_root=data_root,
        config=config_reader,
        render_calls=render_calls,
    )


def _install_dummy_tools(monkeypatch: pytest.MonkeyPatch, views_module) -> None:
    class DummyTool:
        def __init__(self, name: str, order: int, all_vs_all: str | None) -> None:
            self.name = name
            self.order = order
            self.all_vs_all = all_vs_all
            self.options = [
                {
                    "group": "repeat",
                    "type": "radio",
                    "entries": [
                        {"key": "few", "value": "--repeat:few", "default": True},
                        {"key": "many", "value": "--repeat:many"},
                    ],
                }
            ]

        def resolve_option_keys(self, chosen):
            valid = {f"repeat:{item['key']}": item["value"] for item in self.options[0]["entries"]}
            return [valid[key] for key in chosen]

    class DummyTools:
        def __init__(self, *_args, **_kwargs):
            self.tools = {
                "minimap2": DummyTool("minimap2", 1, "{exe}"),
                "mashmap": DummyTool("mashmap", 2, None),
            }

        def get_default(self):
            return "minimap2"

    monkeypatch.setattr(views_module, "Tools", DummyTools, raising=False)


def _make_launch_form(job_id: str, email: str = "user@example.org") -> list[tuple[str, str]]:
    return [
        ("s_id", "upload-session"),
        ("id_job", job_id),
        ("type", "align"),
        ("email", email),
        ("nb_jobs", "1"),
        ("jobs[0][type]", "align"),
        ("jobs[0][query]", "query.fa.gz"),
        ("jobs[0][query_type]", "local"),
        ("jobs[0][target]", "target.fa.gz"),
        ("jobs[0][target_type]", "local"),
        ("jobs[0][tool]", "minimap2"),
        ("jobs[0][alignfile]", ""),
        ("jobs[0][alignfile_type]", ""),
        ("jobs[0][backup]", ""),
        ("jobs[0][backup_type]", ""),
        ("jobs[0][batch]", ""),
        ("jobs[0][batch_type]", ""),
        ("jobs[0][tool_options][]", "repeat:few"),
    ]


def test_views_pages_and_documentation_routes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = _setup_views_runtime(monkeypatch, tmp_path)
    views = runtime.views

    _install_dummy_tools(monkeypatch, views)
    monkeypatch.setattr(views.Functions, "get_list_all_jobs", staticmethod(lambda _mode: ["jobA", "jobB"]), raising=False)
    monkeypatch.setattr(views.Functions, "create_session", staticmethod(lambda: "session-1"), raising=False)
    monkeypatch.setattr(views.Functions, "random_job_id", staticmethod(lambda: "rand-job"), raising=False)
    monkeypatch.setattr(views.Functions, "get_readable_size", staticmethod(lambda size, *_args: f"{size} B"), raising=False)
    monkeypatch.setattr(views, "Latest", lambda: SimpleNamespace(latest="2.1.0", win32="https://example.org/win32"), raising=False)

    (Path(runtime.config.config_dir) / ".inforun").write_text(json.dumps({"message": "Scheduled maintenance"}))

    context = views.global_templates_variables()
    assert context["title"] == "D-Genies Tests"
    assert context["all_jobs"] == ["jobA", "jobB"]
    assert context["legal_pages"] == {"terms": runtime.config.legal["terms"]}

    with runtime.app.test_request_context("/"):
        response = views.main()
    assert response["template"] == "index.html"
    assert response["context"]["pict"] is None

    with runtime.app.test_request_context("/run?id_job=custom-job&email=test@example.org"):
        response = views.run()
    assert response["template"] == "run.html"
    assert response["context"]["id_job"] == "custom-job"
    assert response["context"]["email"] == "test@example.org"
    assert response["context"]["s_id"] == "session-1"
    assert response["context"]["inforun"] == {"message": "Scheduled maintenance"}
    assert response["context"]["tools_names"] == ["minimap2", "mashmap"]

    with runtime.app.test_request_context("/documentation/run"):
        response = views.documentation_run()
    assert response["template"] == "documentation.html"
    assert "2.1.0" in str(response["context"]["content"])

    for route in (
        views.documentation_definitions,
        views.documentation_result,
        views.documentation_formats,
        views.documentation_dotplot,
        views.install,
        views.contact,
    ):
        with runtime.app.test_request_context("/"):
            response = route()
        assert response["template"] in {"documentation.html", "contact.html"}

    with runtime.app.test_request_context("/legal/terms"):
        response = views.legal("terms")
    assert response["template"] == "simple.html"
    assert "Example legal page" in str(response["context"]["content"])

    with runtime.app.test_request_context("/legal/missing"):
        with pytest.raises(NotFound):
            views.legal("missing")

    with runtime.app.test_request_context("/gallery"):
        with pytest.raises(NotFound):
            views.gallery()


def test_views_webserver_gallery_and_run_test(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = _setup_views_runtime(monkeypatch, tmp_path, mode="webserver")
    views = runtime.views

    class DummyGallery:
        class _Query(list):
            def order_by(self, *_args, **_kwargs):
                return self

        @classmethod
        def select(cls):
            return cls._Query([SimpleNamespace(picture="gallery.png")])

    class DummySession:
        @classmethod
        def connect(cls):
            return _NullContext()

        @classmethod
        def new(cls):
            return "new-session"

    gallery_dir = runtime.data_root / "gallery"
    gallery_dir.mkdir()
    (gallery_dir / "gallery.png").write_bytes(b"png")

    monkeypatch.setattr(views, "Gallery", DummyGallery, raising=False)
    monkeypatch.setattr(views, "Session", DummySession, raising=False)
    monkeypatch.setattr(views.Functions, "get_gallery_items", staticmethod(lambda: [{"job": "gallery-job"}]), raising=False)

    with runtime.app.test_request_context("/"):
        response = views.main()
    assert response["context"]["pict"] == "gallery.png"

    with runtime.app.test_request_context("/gallery"):
        response = views.gallery()
    assert response["template"] == "gallery.html"
    assert response["context"]["items"] == [{"job": "gallery-job"}]

    with runtime.app.test_request_context("/gallery/gallery.png"):
        response = views.gallery_file("gallery.png")
    assert response.status_code == 200

    with runtime.app.test_request_context("/gallery/missing.png"):
        with pytest.raises(NotFound):
            views.gallery_file("missing.png")

    with runtime.app.test_request_context("/run-test", environ_base={"REMOTE_ADDR": "10.0.0.5"}):
        with pytest.raises(NotFound):
            views.run_test()

    with runtime.app.test_request_context("/run-test", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        assert views.run_test() == "new-session"


def test_views_form_helpers_and_launch_analysis_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = _setup_views_runtime(monkeypatch, tmp_path)
    views = runtime.views

    _install_dummy_tools(monkeypatch, views)
    monkeypatch.setattr(views.Functions, "is_email_mandatory", staticmethod(lambda: True), raising=False)

    parsed = views.parse_form(ImmutableMultiDict(_make_launch_form("batch job")))
    assert parsed[0] == "batch job"
    assert parsed[1] == "align"
    assert parsed[2] == "user@example.org"
    assert parsed[3] == 1
    assert parsed[4][0]["options"] == ["repeat:few"]

    assert views.check_file_type({"query": "query.fa.gz", "query_type": None}, "query") == [
        "Server error: no query_type in form. Please contact the support"
    ]
    assert views.check_file_type({"target": "target.fa.gz", "target_type": "local"}, "target") == []

    job = {
        "type": "align",
        "query": "query.fa.gz",
        "query_type": "local",
        "target": "target.fa.gz",
        "target_type": "local",
        "tool": None,
        "options": ["repeat:few"],
    }
    views.check_file_type_and_resolv_options(job)
    assert job["tool"] == "minimap2"
    assert job["options"] == "--repeat:few"

    with pytest.raises(Exception):
        views.check_file_type_and_resolv_options(
            {
                "type": "align",
                "query": "query.fa.gz",
                "query_type": "local",
                "target": "",
                "target_type": "local",
                "tool": "missing",
                "options": [],
            }
        )

    batch_file = runtime.data_root / "batch.txt"
    jobs = [
        {
            "type": "align",
            "id_job": "job1",
            "query": DataFile("query", "/tmp/query.fa.gz", "local"),
            "target": DataFile("target", "/tmp/target.fa.gz", "local"),
            "tool_options": "--repeat:few",
        }
    ]
    batch_data = views.create_batch_file(str(batch_file), jobs)
    assert batch_data.get_name() == "batch"
    assert "query=/tmp/query.fa.gz" in batch_file.read_text()

    launched = {}

    class DummyJob:
        def launch_standalone(self):
            launched["mode"] = "standalone"

    monkeypatch.setattr(views, "update_files", lambda jobs_list, folder: launched.update(folder=folder, count=len(jobs_list)), raising=False)
    monkeypatch.setattr(views.JobManager, "create", staticmethod(lambda **_kwargs: DummyJob()), raising=False)
    (runtime.data_root / "My_Job").mkdir()

    with runtime.app.test_request_context(
        "/launch_analysis", method="POST", data=ImmutableMultiDict(_make_launch_form("My Job"))
    ):
        payload = views.launch_analysis().get_json()
    assert payload["success"] is True
    assert payload["redirect"].endswith("/status/My_Job_2")
    assert launched == {"folder": "upload-session", "count": 1, "mode": "standalone"}

    invalid_form = ImmutableMultiDict(_make_launch_form("", email="invalid-email"))
    with runtime.app.test_request_context("/launch_analysis", method="POST", data=invalid_form):
        payload = views.launch_analysis().get_json()
    assert payload["success"] is False
    assert "Id of job not given" in payload["errors"]
    assert "Email is invalid" in payload["errors"]

    monkeypatch.setattr(views, "update_files", lambda *_args: (_ for _ in ()).throw(DGeniesExampleInvalid("missing.fa.gz")), raising=False)
    with runtime.app.test_request_context(
        "/launch_analysis", method="POST", data=ImmutableMultiDict(_make_launch_form("example job"))
    ):
        payload = views.launch_analysis().get_json()
    assert payload["success"] is False
    assert payload["errors"] == ["Invalid example: example://missing.fa.gz"]

    monkeypatch.setattr(views, "update_files", lambda *_args: None, raising=False)
    monkeypatch.setattr(views.JobManager, "create", staticmethod(lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))), raising=False)
    with runtime.app.test_request_context(
        "/launch_analysis", method="POST", data=ImmutableMultiDict(_make_launch_form("broken job"))
    ):
        payload = views.launch_analysis().get_json()
    assert payload["success"] is False
    assert payload["errors"] == ["Something went wrong during job creation!"]


def test_views_additional_page_and_launch_error_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = _setup_views_runtime(monkeypatch, tmp_path, mode="webserver")
    views = runtime.views
    _install_dummy_tools(monkeypatch, views)

    class EmptyGallery:
        class _Query(list):
            def order_by(self, *_args, **_kwargs):
                return self

        @classmethod
        def select(cls):
            return cls._Query([])

    deleted = {}

    class DummySession:
        def __init__(self):
            self.upload_folder = "session-upload"

        def delete_instance(self):
            deleted["session"] = True

        @classmethod
        def connect(cls):
            return _NullContext()

        @classmethod
        def get(cls, s_id):
            if s_id == "missing":
                raise views.DoesNotExist()
            return cls()

    class DummyJob:
        def launch(self):
            deleted["launched"] = "webserver"

    monkeypatch.setattr(views, "Gallery", EmptyGallery, raising=False)
    monkeypatch.setattr(views, "Session", DummySession, raising=False)
    monkeypatch.setattr(views, "DoesNotExist", KeyError, raising=False)
    monkeypatch.setattr(views.Functions, "is_email_mandatory", staticmethod(lambda: True), raising=False)
    monkeypatch.setattr(views.Functions, "create_session", staticmethod(lambda: "session-2"), raising=False)
    monkeypatch.setattr(views.Functions, "random_job_id", staticmethod(lambda: "rand-job"), raising=False)
    monkeypatch.setattr(views.Functions, "get_readable_size", staticmethod(lambda size, *_args: f"{size} B"), raising=False)
    monkeypatch.setattr(views, "Latest", lambda: SimpleNamespace(latest="2.1.0"), raising=False)

    inforun_file = Path(runtime.config.config_dir) / ".inforun"
    inforun_file.write_text("{invalid json")
    monkeypatch.setattr(runtime.config, "max_upload_file_size", -1, raising=False)
    monkeypatch.setattr(runtime.config, "max_upload_size", -1, raising=False)
    monkeypatch.setattr(runtime.config, "max_upload_size_ava", -1, raising=False)

    with runtime.app.test_request_context("/"):
        response = views.main()
    assert response["context"]["pict"] is None

    with runtime.app.test_request_context("/run"):
        response = views.run()
    assert response["context"]["inforun"] is None

    with runtime.app.test_request_context("/documentation/run"):
        response = views.documentation_run()
    assert "no limit" in str(response["context"]["content"])

    with pytest.raises(views.DGeniesUnknownToolError, match="None"):
        views.get_tools_options(None, [])

    plot_job = {
        "type": "plot",
        "target": "target.fa.gz",
        "target_type": "local",
        "query": "query.fa.gz",
        "query_type": "local",
        "align": "map.paf",
        "align_type": None,
        "backup": "backup.tar.gz",
        "backup_type": "local",
    }
    with pytest.raises(views.DGeniesJobCheckError, match="align_type"):
        views.check_file_type_and_resolv_options(plot_job)

    with runtime.app.test_request_context("/launch_analysis", method="POST", data=ImmutableMultiDict(_make_launch_form("job", ""))):
        payload = views.launch_analysis().get_json()
    assert payload["success"] is False
    assert payload["errors"] == ["Email not given"]

    missing_form = ImmutableMultiDict([("s_id", "missing"), *_make_launch_form("job-2")[1:]])
    with runtime.app.test_request_context("/launch_analysis", method="POST", data=missing_form):
        payload = views.launch_analysis().get_json()
    assert payload["success"] is False
    assert "Session has expired" in payload["errors"][0]

    original_check = views.check_file_type_and_resolv_options
    monkeypatch.setattr(
        views,
        "check_file_type_and_resolv_options",
        lambda *_args: (_ for _ in ()).throw(views.DGeniesJobCheckError(["query_type missing"])),
        raising=False,
    )
    with runtime.app.test_request_context("/launch_analysis", method="POST", data=ImmutableMultiDict(_make_launch_form("job-3"))):
        payload = views.launch_analysis().get_json()
    assert payload["success"] is False
    assert payload["errors"] == ["Server error: query_type missing. Please contact the support."]

    monkeypatch.setattr(views, "check_file_type_and_resolv_options", original_check, raising=False)
    monkeypatch.setattr(views, "update_files", lambda jobs, folder: deleted.update(updated=(len(jobs), folder)), raising=False)
    monkeypatch.setattr(views.JobManager, "create", staticmethod(lambda **_kwargs: DummyJob()), raising=False)
    with runtime.app.test_request_context("/launch_analysis", method="POST", data=ImmutableMultiDict(_make_launch_form("clean batch"))):
        payload = views.launch_analysis().get_json()
    assert payload["success"] is True
    assert deleted["session"] is True
    assert deleted["updated"] == (1, "session-upload")
    assert deleted["launched"] == "webserver"

    standalone_root = tmp_path / "standalone"
    standalone_root.mkdir()
    standalone = _setup_views_runtime(monkeypatch, standalone_root, mode="standalone")
    with standalone.app.test_request_context("/run-test"):
        with pytest.raises(Exception) as error:
            standalone.views.run_test()
    assert getattr(error.value, "code", None) == 500


def test_views_status_result_and_example_downloads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = _setup_views_runtime(monkeypatch, tmp_path)
    views = runtime.views

    class DummyJobManager:
        def __init__(self, id_job, mailer=None):
            self.id_job = id_job

        def is_batch(self):
            return self.id_job == "batch-job"

        def get_subjob_ids(self):
            return ["sub-1"]

        def do_align(self):
            return True

        def is_query_filtered(self):
            return False

        def is_target_filtered(self):
            return True

    statuses = {
        "batch-job": {"status": "started-batch", "error": "", "mem_peak": 12, "time_elapsed": 34},
        "sub-1": {"status": "success", "error": "", "mem_peak": 1, "time_elapsed": 2},
        "job-1": {"status": "success", "error": "", "mem_peak": 7, "time_elapsed": 8},
    }
    monkeypatch.setattr(views, "JobManager", DummyJobManager, raising=False)
    monkeypatch.setattr(views.Functions, "get_status", lambda self, job: dict(statuses[job.id_job]), raising=False)
    monkeypatch.setattr(views.Functions, "is_in_gallery", staticmethod(lambda *_args: True), raising=False)
    monkeypatch.setattr(views.Functions, "query_fasta_file_exists", staticmethod(lambda _path: True), raising=False)
    monkeypatch.setattr(views.Functions, "has_logs", staticmethod(lambda _path: True), raising=False)

    with runtime.app.test_request_context("/status/batch-job?format=json"):
        payload = views.status("batch-job").get_json()
    assert payload["status"] == "started-batch"
    assert payload["batch"][0]["status"] == "success"

    with runtime.app.test_request_context("/status/job-1"):
        response = views.status("job-1")
    assert response["template"] == "status.html"
    assert response["context"]["target_filtered"] is True

    with runtime.app.test_request_context("/result/job-1"):
        response = views.result("job-1")
    assert response["template"] == "result.html"
    assert response["context"]["is_gallery"] is True
    assert response["context"]["fasta_file"] is True
    assert response["context"]["has_logs"] is True

    with runtime.app.test_request_context("/example/backup"):
        backup_response = views.download_example_backup()
    assert backup_response.status_code == 200

    with runtime.app.test_request_context("/example/batch"):
        batch_response = views.download_example_batch()
    assert batch_response.status_code == 200
    assert "example_align" in batch_response.get_data(as_text=True)

    monkeypatch.setattr(runtime.config, "example_backup", str(runtime.data_root / "missing.tar.gz"), raising=False)
    with runtime.app.test_request_context("/example/backup"):
        with pytest.raises(NotFound):
            views.download_example_backup()


def test_views_paf_routes_and_viewer_workflows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = _setup_views_runtime(monkeypatch, tmp_path)
    views = runtime.views
    job_id = "view-job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()
    (job_dir / "map.paf").write_text("query\t5\t0\t5\t+\ttarget\t5\t0\t5\t5\t5\t60\n")
    (job_dir / "map.paf.sorted").write_text("sorted\n")
    (job_dir / "query.idx").write_text("Query\nq1\t5\n")
    (job_dir / "target.idx").write_text("Target\nt1\t5\n")
    (job_dir / "logs.txt").write_text("log line\n")
    (job_dir / ".filter-query").write_text(">q1\nAAAA\n")
    (job_dir / ".filter-target").write_text(">t1\nTTTT\n")
    query_fasta = job_dir / "query.fa"
    query_fasta.write_text(">q1\nAAAA\n")
    query_gz = job_dir / "query.fa.gz"
    query_gz.write_bytes(b"\x1f\x8btest")
    (job_dir / ".query").write_text(str(query_fasta))

    class DummyPaf:
        parsed_default = True

        def __init__(self, paf_file, *_args, **_kwargs):
            self.paf_file = paf_file
            self.parsed = self.parsed_default
            self.error = "paf error"

        def get_d3js_data(self):
            return {"lines": {"3": [[0, 5, 0, 5, 1.0, "q1", "t1"]]}, "sorted": False}

        def sort(self):
            output_dir = Path(self.paf_file).parent
            (output_dir / ".sorted").touch()
            (output_dir / "map.paf.sorted").touch()
            (output_dir / "query.idx.sorted").touch()
            self.parsed = True

        def reverse_contig(self, _contig_name):
            self.parsed = True

        def parse_paf(self, *_args, **_kwargs):
            self.parsed = self.parsed_default

        def build_query_on_target_association_file(self):
            return "q1\tt1\t+\n"

        def build_list_no_assoc(self, which):
            return ["q_unmatched"] if which == "query" else ["t_unmatched"]

        def get_summary_stats(self):
            return {100: 100.0}

        def build_query_chr_as_reference(self, compress=False):
            output = Path(self.paf_file).parent / ("query_as_reference.fa.gz" if compress else "query_as_reference.fa")
            output.write_text(">t1\nAAAA\n")
            return str(output)

    monkeypatch.setattr(views, "Paf", DummyPaf, raising=False)
    monkeypatch.setattr(views.Functions, "get_fasta_file", staticmethod(lambda _res_dir, _type_f, is_sorted: str(query_fasta if not is_sorted else query_gz)), raising=False)

    with runtime.app.test_request_context(f"/paf/{job_id}"):
        response = views.download_paf(job_id)
    assert response.get_data(as_text=True) == "sorted\n"

    with runtime.app.test_request_context("/get_graph", method="POST", data={"id": job_id}):
        payload = views.get_graph().get_json()
    assert payload["success"] is True
    assert (job_dir / ".valid").exists()

    with runtime.app.test_request_context(f"/sort/{job_id}", method="POST"):
        payload = views.sort_graph(job_id).get_json()
    assert payload["success"] is True
    assert (job_dir / ".sorted").exists()

    (job_dir / ".all-vs-all").touch()
    with runtime.app.test_request_context(f"/sort/{job_id}", method="POST"):
        payload = views.sort_graph(job_id).get_json()
    assert payload["success"] is False
    (job_dir / ".all-vs-all").unlink()

    with runtime.app.test_request_context(f"/reset-sort/{job_id}", method="POST"):
        payload = views.reset_sort(job_id).get_json()
    assert payload["success"] is True
    assert (job_dir / ".new-reversals").exists()

    with runtime.app.test_request_context(f"/reverse-contig/{job_id}", method="POST", data={"contig": "q1"}):
        payload = views.reverse_contig(job_id).get_json()
    assert payload["success"] is True

    with runtime.app.test_request_context(f"/freenoise/{job_id}", method="POST", data={"noise": "1"}):
        payload = views.free_noise(job_id).get_json()
    assert payload["success"] is True

    DummyPaf.parsed_default = False
    with runtime.app.test_request_context(f"/freenoise/{job_id}", method="POST", data={"noise": "0"}):
        payload = views.free_noise(job_id).get_json()
    assert payload["success"] is False
    DummyPaf.parsed_default = True

    monkeypatch.setattr(views, "build_fasta", lambda _job_id, _gzip: (1, False), raising=False)
    with runtime.app.test_request_context(f"/get-fasta-query/{job_id}", method="POST", data={"gzip": "false"}):
        payload = views.prepare_fasta(job_id).get_json()
    assert payload["status_message"] == "In progress"

    monkeypatch.setattr(views, "build_fasta", lambda _job_id, _gzip: (2, True), raising=False)
    with runtime.app.test_request_context(f"/get-fasta-query/{job_id}", method="POST", data={"gzip": "true"}):
        payload = views.prepare_fasta(job_id).get_json()
    assert payload["status_message"] == "Done"
    assert payload["gzip"] is True

    monkeypatch.setattr(views, "build_fasta", lambda _job_id, _gzip: (0, False), raising=False)
    with runtime.app.test_request_context(f"/get-fasta-query/{job_id}", method="POST", data={"gzip": "false"}):
        payload = views.prepare_fasta(job_id).get_json()
    assert payload["success"] is False
    assert payload["message"] == "Unknown state"

    monkeypatch.setattr(views, "build_fasta", lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")), raising=False)
    with runtime.app.test_request_context(f"/get-fasta-query/{job_id}", method="POST", data={"gzip": "false"}):
        payload = views.prepare_fasta(job_id).get_json()
    assert payload["success"] is False
    assert "Unable to get fasta file" in payload["message"]

    with runtime.app.test_request_context(f"/build-query-as-reference/{job_id}", method="POST"):
        payload = views.post_query_as_reference(job_id).get_json()
    assert payload["success"] is True

    monkeypatch.setattr(views, "send_file", lambda path, as_attachment=True: f"send:{os.path.basename(path)}", raising=False)
    with runtime.app.test_request_context(f"/get-query-as-reference/{job_id}"):
        assert views.get_query_as_reference(job_id) == "send:query_as_reference.fa"

    monkeypatch.setattr(views, "send_file", lambda path: f"download:{os.path.basename(path)}", raising=False)
    with runtime.app.test_request_context(f"/download/{job_id}/logs.txt"):
        assert views.download_file(job_id, "logs.txt") == "download:logs.txt"
    with runtime.app.test_request_context(f"/download/{job_id}/missing.txt"):
        with pytest.raises(NotFound):
            views.download_file(job_id, "missing.txt")

    with runtime.app.test_request_context(f"/fasta-query/{job_id}/query.fa.gz"):
        response = views.dl_fasta(job_id, "query.fa.gz")
    assert response.mimetype == "application/gzip"

    with runtime.app.test_request_context(f"/fasta-query/{job_id}"):
        response = views.dl_fasta(job_id, "")
    assert response.mimetype == "text/plain"

    (job_dir / ".sorted").touch()
    (job_dir / ".query-fasta-build").touch()
    with runtime.app.test_request_context(f"/fasta-query/{job_id}"):
        with pytest.raises(NotFound):
            views.dl_fasta(job_id, "")
    (job_dir / ".query-fasta-build").unlink()

    with runtime.app.test_request_context(f"/qt-assoc/{job_id}"):
        response = views.qt_assoc(job_id)
    assert "q1\tt1" in response.get_data(as_text=True)

    with runtime.app.test_request_context("/qt-assoc/missing"):
        with pytest.raises(NotFound):
            views.qt_assoc("missing")

    with runtime.app.test_request_context(f"/no-assoc/{job_id}", method="POST", data={"to": "query"}):
        payload = views.no_assoc(job_id).get_json()
    assert payload["file_content"] == "q_unmatched\n"
    assert payload["empty"] is False

    with runtime.app.test_request_context("/no-assoc/missing", method="POST", data={"to": "query"}):
        with pytest.raises(NotFound):
            views.no_assoc("missing")

    with runtime.app.test_request_context(f"/filter-out/{job_id}/query"):
        response = views.get_filter_out_query(job_id)
    assert ">q1" in response.get_data(as_text=True)

    with runtime.app.test_request_context(f"/filter-out/{job_id}/target"):
        response = views.get_filter_out_target(job_id)
    assert ">t1" in response.get_data(as_text=True)

    with runtime.app.test_request_context(f"/viewer/{job_id}"):
        response = views.get_viewer_html(job_id)
    assert response["template"] == "map_offline.html"
    assert response["context"]["percents"] == {100: 100.0}

    DummyPaf.parsed_default = False
    with runtime.app.test_request_context(f"/viewer/{job_id}"):
        with pytest.raises(Forbidden):
            views.get_viewer_html(job_id)


def test_views_additional_download_and_paf_error_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = _setup_views_runtime(monkeypatch, tmp_path)
    views = runtime.views
    job_id = "error-job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()
    (job_dir / "map.txt").write_text("plain text\n")
    (job_dir / "query.fa").write_text(">q1\nAAAA\n")
    (job_dir / "query.fa.gz").write_bytes(b"\x1f\x8btest")
    (job_dir / "map.paf").write_text("query\t5\t0\t5\t+\ttarget\t5\t0\t5\t5\t5\t60\n")
    (job_dir / "query.idx").write_text("Query\nq1\t5\n")
    (job_dir / "target.idx").write_text("Target\nt1\t5\n")
    (job_dir / ".query").write_text("query.fa")

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

    assert BrokenPaf().parse_paf() is None

    class MissingPaf:
        def __init__(self, *_args, **_kwargs):
            raise FileNotFoundError("missing paf")

    with runtime.app.test_request_context("/gallery/plain.txt"):
        with pytest.raises(NotFound):
            views.gallery_file("plain.txt")

    with runtime.app.test_request_context("/paf/missing-paf-job"):
        with pytest.raises(NotFound):
            views.download_paf("missing-paf-job")

    monkeypatch.setattr(views, "Paf", BrokenPaf, raising=False)
    with runtime.app.test_request_context("/get_graph", method="POST", data={"id": job_id}):
        payload = views.get_graph().get_json()
    assert payload == {"success": False, "message": "Broken dotplot"}

    with runtime.app.test_request_context(f"/sort/{job_id}", method="POST"):
        payload = views.sort_graph(job_id).get_json()
    assert payload == {"success": False, "message": "Broken dotplot"}

    with runtime.app.test_request_context(f"/reset-sort/{job_id}", method="POST"):
        payload = views.reset_sort(job_id).get_json()
    assert payload == {"success": False, "message": "Broken dotplot"}

    with runtime.app.test_request_context(f"/reverse-contig/{job_id}", method="POST", data={"contig": "q1"}):
        payload = views.reverse_contig(job_id).get_json()
    assert payload == {"success": False, "message": "Broken dotplot"}

    (job_dir / ".all-vs-all").touch()
    with runtime.app.test_request_context(f"/reverse-contig/{job_id}", method="POST", data={"contig": "q1"}):
        payload = views.reverse_contig(job_id).get_json()
    assert payload["success"] is False
    assert "All-vs-All" in payload["message"]
    (job_dir / ".all-vs-all").unlink()

    monkeypatch.setattr(views.Functions, "get_fasta_file", staticmethod(lambda *_args, **_kwargs: str(job_dir / "query.fa.gz")), raising=False)
    with runtime.app.test_request_context(f"/fasta-query/{job_id}"):
        response = views.dl_fasta(job_id, "")
    assert response.mimetype == "application/gzip"

    with runtime.app.test_request_context(f"/fasta-query/{job_id}/map.txt"):
        response = views.dl_fasta(job_id, "map.txt")
    assert response.mimetype == "text/plain"

    monkeypatch.setattr(views, "Paf", MissingPaf, raising=False)
    with runtime.app.test_request_context(f"/qt-assoc/{job_id}"):
        with pytest.raises(NotFound):
            views.qt_assoc(job_id)

    with runtime.app.test_request_context(f"/no-assoc/{job_id}", method="POST", data={"to": "query"}):
        with pytest.raises(NotFound):
            views.no_assoc(job_id)

    monkeypatch.setattr(views, "send_from_directory", lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("missing logs")), raising=False)
    with runtime.app.test_request_context(f"/logs/{job_id}"):
        with pytest.raises(NotFound):
            views.get_logs_file(job_id)

    web_root = tmp_path / "web"
    web_root.mkdir()
    web_runtime = _setup_views_runtime(monkeypatch, web_root, mode="webserver")
    web_views = web_runtime.views
    timers = {}

    class TimedPaf:
        def __init__(self, paf_file, *_args, **_kwargs):
            self.paf_file = paf_file
            self.parsed = True

        def parse_paf(self, *_args):
            return None

        def build_query_chr_as_reference(self, compress=False):
            output = Path(self.paf_file).with_name("query_as_reference.fa.gz" if compress else "query_as_reference.fa")
            output.write_text(">q\nAAAA\n")
            return str(output)

    class DummyTimer:
        def __init__(self, delay, func, kwargs=None):
            timers["delay"] = delay
            timers["func"] = func
            timers["kwargs"] = kwargs or {}

        def start(self):
            timers["started"] = True

    monkeypatch.setattr(web_views, "Paf", TimedPaf, raising=False)
    monkeypatch.setattr(web_views.threading, "Timer", DummyTimer, raising=False)
    web_job_dir = web_runtime.data_root / job_id
    web_job_dir.mkdir()
    for filename in ("map.paf", "query.idx", "target.idx"):
        (web_job_dir / filename).write_text("placeholder\n")

    direct_build = TimedPaf(str(web_job_dir / "map.paf")).build_query_chr_as_reference(compress=True)
    assert direct_build.endswith("query_as_reference.fa.gz")
    assert Path(direct_build).read_text() == ">q\nAAAA\n"

    assert web_views.build_query_as_reference(job_id) is True
    assert timers["delay"] == 0
    assert timers["kwargs"] == {"compress": True}
    assert timers["started"] is True

    with web_runtime.app.test_request_context(f"/get-query-as-reference/{job_id}"):
        with pytest.raises(NotFound):
            web_views.get_query_as_reference(job_id)


def test_views_summary_backup_logs_upload_and_session_routes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = _setup_views_runtime(monkeypatch, tmp_path, mode="webserver")
    views = runtime.views
    job_id = "session-job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()
    for filename, content in (
        ("map.paf", "query\t5\t0\t5\t+\ttarget\t5\t0\t5\t5\t5\t60\n"),
        ("query.idx", "Query\nq1\t5\n"),
        ("target.idx", "Target\nt1\t5\n"),
        ("logs.txt", "log line\n"),
    ):
        (job_dir / filename).write_text(content)

    monkeypatch.setattr(views, "compute_summary", lambda _id: ({100: 85.0}, "done"), raising=False)
    with runtime.app.test_request_context(f"/summary/{job_id}", method="POST"):
        payload = views.summary(job_id).get_json()
    assert payload["success"] is True
    assert payload["status"] == "done"

    monkeypatch.setattr(views, "compute_summary", lambda _id: (None, "file_not_found"), raising=False)
    with runtime.app.test_request_context(f"/summary/{job_id}", method="POST"):
        payload = views.summary(job_id).get_json()
    assert payload["success"] is False
    assert payload["message"] == "Unable to load data!"

    monkeypatch.setattr(views, "compute_summary", lambda _id: (None, "fail"), raising=False)
    with runtime.app.test_request_context(f"/summary/{job_id}", method="POST"):
        payload = views.summary(job_id).get_json()
    assert payload["success"] is False
    assert "Build of summary failed" in payload["message"]

    with runtime.app.test_request_context(f"/backup/{job_id}"):
        response = views.get_backup_file(job_id)
    assert response.status_code == 200
    archive_path = job_dir / f"{job_id}.tar.gz"
    with tarfile.open(archive_path, "r:gz") as tar_handle:
        assert sorted(tar_handle.getnames()) == ["logs.txt", "map.paf", "query.idx", "target.idx"]

    with runtime.app.test_request_context(f"/logs/{job_id}"):
        response = views.get_logs_file(job_id)
    assert response.status_code == 200

    with runtime.app.test_request_context("/logs/missing"):
        with pytest.raises(NotFound):
            views.get_logs_file("missing")

    class DummySession:
        pinged = False

        def __init__(self, upload_folder="session-upload", allowed=True):
            self.upload_folder = upload_folder
            self._allowed = allowed

        def ask_for_upload(self, _change_status):
            return self._allowed

        def ping(self):
            DummySession.pinged = True

        @classmethod
        def connect(cls):
            return _NullContext()

        @classmethod
        def get(cls, s_id):
            if s_id == "missing":
                raise views.DoesNotExist()
            if s_id == "blocked":
                return cls(allowed=False)
            return cls()

    monkeypatch.setattr(views, "Session", DummySession, raising=False)
    monkeypatch.setattr(views, "DoesNotExist", KeyError, raising=False)

    with runtime.app.test_request_context("/ask-upload", method="POST", data={"s_id": "ok"}):
        payload = views.ask_upload().get_json()
    assert payload == {"success": True, "allowed": True}

    with runtime.app.test_request_context("/ask-upload", method="POST", data={"s_id": "missing"}):
        payload = views.ask_upload().get_json()
    assert payload["success"] is False

    ask_standalone_root = tmp_path / "ask-standalone"
    ask_standalone_root.mkdir()
    standalone = _setup_views_runtime(monkeypatch, ask_standalone_root, mode="standalone")
    with standalone.app.test_request_context("/ask-upload", method="POST", data={"s_id": "ignored"}):
        assert standalone.views.ask_upload().get_json() == {"success": True, "allowed": True}

    with runtime.app.test_request_context("/ping-upload", method="POST", data={"s_id": "ok"}):
        assert views.ping_upload() == "OK"
    assert DummySession.pinged is True

    monkeypatch.setattr(views.Functions, "allowed_file", staticmethod(lambda *_args: True), raising=False)
    with runtime.app.test_request_context(
        "/upload",
        method="POST",
        data={
            "s_id": "ok",
            "formats": "fasta",
            "file": (BytesIO(b">q1\nAAAA\n"), "query.fa"),
        },
        content_type="multipart/form-data",
    ):
        payload = views.upload().get_json()
    assert payload["success"] == "OK"
    assert payload["files"][0]["name"].endswith("query.fa")

    with runtime.app.test_request_context(
        "/upload",
        method="POST",
        data={
            "s_id": "blocked",
            "formats": "fasta",
            "file": (BytesIO(b">q1\nAAAA\n"), "query.fa"),
        },
        content_type="multipart/form-data",
    ):
        payload = views.upload().get_json()
    assert payload["success"] == "ERR"
    assert payload["message"] == "Not allowed to upload!"

    monkeypatch.setattr(views.Functions, "allowed_file", staticmethod(lambda *_args: False), raising=False)
    with runtime.app.test_request_context(
        "/upload",
        method="POST",
        data={
            "s_id": "ok",
            "formats": "fasta",
            "file": (BytesIO(b"bad"), "query.txt"),
        },
        content_type="multipart/form-data",
    ):
        payload = views.upload().get_json()
    assert payload["success"] == "OK"
    assert payload["files"][0]["error"] == "File type not allowed"

    with runtime.app.test_request_context(
        "/upload",
        method="POST",
        data={"s_id": "ok", "formats": "fasta", "file": (BytesIO(b""), "")},
        content_type="multipart/form-data",
    ):
        payload = views.upload().get_json()
    assert payload["success"] == "404"

    with runtime.app.test_request_context(
        "/upload",
        method="POST",
        data={
            "s_id": "missing",
            "formats": "fasta",
            "file": (BytesIO(b">q1\nAAAA\n"), "query.fa"),
        },
        content_type="multipart/form-data",
    ):
        payload = views.upload().get_json()
    assert payload["success"] == "ERR"
    assert "Session not initialized" in payload["message"]

    upload_standalone_root = tmp_path / "upload-standalone"
    upload_standalone_root.mkdir()
    standalone_upload = _setup_views_runtime(monkeypatch, upload_standalone_root, mode="standalone")
    standalone_views = standalone_upload.views
    monkeypatch.setattr(standalone_views.Functions, "allowed_file", staticmethod(lambda *_args: True), raising=False)
    with standalone_upload.app.test_request_context(
        "/upload",
        method="POST",
        data={
            "s_id": "folder-1",
            "formats": "fasta",
            "file": (BytesIO(b">q1\nAAAA\n"), "query.fa"),
        },
        content_type="multipart/form-data",
    ):
        payload = standalone_views.upload().get_json()
    assert payload["success"] == "OK"
    assert payload["files"][0]["size"] > 0

    monkeypatch.setattr(
        standalone_views.Functions,
        "get_valid_uploaded_filename",
        staticmethod(lambda *_args: (_ for _ in ()).throw(RuntimeError("boom"))),
        raising=False,
    )
    with standalone_upload.app.test_request_context(
        "/upload",
        method="POST",
        data={
            "s_id": "folder-2",
            "formats": "fasta",
            "file": (BytesIO(b">q1\nAAAA\n"), "query.fa"),
        },
        content_type="multipart/form-data",
    ):
        payload = standalone_views.upload().get_json()
    assert payload["success"] == "ERR"


def test_views_send_mail_and_delete_job_routes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = _setup_views_runtime(monkeypatch, tmp_path)
    views = runtime.views
    job_id = "notify-job"
    job_dir = runtime.data_root / job_id
    job_dir.mkdir()
    (job_dir / ".key").write_text("secret-key\n")

    sent = {}

    class DummyJobManager:
        def __init__(self, id_job, mailer=None):
            self.id_job = id_job

        def set_inputs_from_res_dir(self):
            sent["loaded"] = self.id_job

        def send_mail_if_allowed(self):
            sent["sent"] = True

        def delete(self):
            outcome = sent.get("delete")
            if outcome == "gallery":
                raise DGeniesDeleteGalleryJobForbidden()
            if outcome == "missing":
                raise DGeniesMissingJobError()
            sent["deleted"] = self.id_job

    monkeypatch.setattr(views, "JobManager", DummyJobManager, raising=False)

    with runtime.app.test_request_context(f"/send-mail/{job_id}", method="POST", data={"key": "secret-key"}):
        assert views.send_mail(job_id) == "OK"
    assert sent == {"loaded": job_id, "sent": True}
    assert not (job_dir / ".key").exists()

    with runtime.app.test_request_context(f"/send-mail/{job_id}", method="POST", data={"key": "bad-key"}):
        with pytest.raises(Forbidden):
            views.send_mail(job_id)

    with runtime.app.test_request_context(f"/delete/{job_id}", method="POST"):
        payload = views.delete_job(job_id).get_json()
    assert payload == {"success": True, "error": ""}

    sent["delete"] = "gallery"
    with runtime.app.test_request_context(f"/delete/{job_id}", method="POST"):
        payload = views.delete_job(job_id).get_json()
    assert payload["success"] is False
    assert "gallery" in payload["error"].lower()

    sent["delete"] = "missing"
    with runtime.app.test_request_context(f"/delete/{job_id}", method="POST"):
        payload = views.delete_job(job_id).get_json()
    assert payload["success"] is False
    assert payload["error"] == "Job does not exists"


def test_views_example_batch_not_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = _setup_views_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime.config, "example_batch", str(runtime.data_root / "missing_batch.txt"), raising=False)

    with runtime.app.test_request_context("/example/batch"):
        with pytest.raises(NotFound):
            runtime.views.download_example_batch()
