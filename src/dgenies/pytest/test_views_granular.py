from pathlib import Path
from types import SimpleNamespace

import pytest


def test_global_template_variables_exposes_configured_values(launched_app, monkeypatch):
    import dgenies.views as views

    monkeypatch.setattr(views.Functions, "get_list_all_jobs", staticmethod(lambda mode: ["job1"]), raising=False)
    monkeypatch.setattr(views.config_reader, "cookie_wall", "cookies")
    monkeypatch.setattr(views.config_reader, "legal", {"cookies": "cookies.md"})

    values = views.global_templates_variables()

    assert values["all_jobs"] == ["job1"]
    assert values["cookie_wall"] == "cookies"
    assert values["legal_pages"] == {"cookies": "cookies.md"}


def test_main_renders_index_without_gallery_in_standalone(launched_app, monkeypatch):
    import dgenies.views as views

    monkeypatch.setattr(views, "MODE", "standalone", raising=False)
    monkeypatch.setattr(views, "render_template", lambda template, **kwargs: (template, kwargs))

    template, kwargs = views.main()

    assert template == "index.html"
    assert kwargs["pict"] is None


def test_check_file_type_reports_missing_type():
    import dgenies.views as views

    errors = views.check_file_type({"target": "target.fa", "target_type": None}, "target")

    assert errors == ["Server error: no target_type in form. Please contact the support"]


def test_check_file_type_ignores_absent_file():
    import dgenies.views as views

    assert views.check_file_type({"target": None, "target_type": None}, "target") == []


def test_update_files_deduplicates_reused_paths(launched_app, monkeypatch):
    import dgenies.views as views
    from dgenies.lib.datafile import DataFile

    created = {}

    def fake_create(path, file_type, upload_folder, example_files):
        created.setdefault(path, DataFile(path, f"/uploads/{path}", file_type))
        return created[path]

    jobs = [
        {"query": "shared.fa", "query_type": "local", "target": "target-a.fa", "target_type": "local"},
        {"query": "shared.fa", "query_type": "local", "target": "target-b.fa", "target_type": "local"},
    ]
    monkeypatch.setattr(views, "create_datafile", fake_create)

    views.update_files(jobs, "session")

    assert jobs[0]["query"] is jobs[1]["query"]
    assert "query_type" not in jobs[0]
    assert "target_type" not in jobs[1]


def test_get_tools_options_rejects_unknown_tool(launched_app):
    import dgenies.views as views
    from dgenies.lib.exceptions import DGeniesUnknownToolError

    with pytest.raises(DGeniesUnknownToolError):
        views.get_tools_options("missing-tool", [])


def test_get_file_reads_text_file(tmp_path):
    import dgenies.views as views

    text_file = tmp_path / "hello.txt"
    text_file.write_text("hello")

    assert views.get_file(str(text_file)) == "hello"


def test_get_file_reads_binary_file_when_gzip_flag_is_set(tmp_path):
    import dgenies.views as views

    binary = tmp_path / "data.gz"
    binary.write_bytes(b"\x1f\x8b")

    assert views.get_file(str(binary), gzip=True) == b"\x1f\x8b"


def test_download_paf_prefers_sorted_file(launched_app, tmp_path, monkeypatch):
    import dgenies.views as views

    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    (job_dir / "map.paf").write_text("unsorted")
    (job_dir / "map.paf.sorted").write_text("sorted")
    monkeypatch.setattr(views, "APP_DATA", str(tmp_path), raising=False)

    with launched_app.test_request_context("/paf/job1"):
        response = views.download_paf("job1")

    assert response.get_data(as_text=True) == "sorted"


def test_reset_sort_removes_sorted_outputs_and_touches_new_reversals(launched_app, tmp_path, monkeypatch):
    import dgenies.views as views

    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    for name in [".sorted", "map.paf.sorted", "query.idx.sorted"]:
        (job_dir / name).write_text("")
    monkeypatch.setattr(views, "APP_DATA", str(tmp_path), raising=False)

    class FakePaf:
        parsed = True

        def __init__(self, *args, **kwargs):
            pass

        def get_d3js_data(self):
            return {"lines": {}}

    monkeypatch.setattr(views, "Paf", FakePaf)

    with launched_app.test_request_context("/reset-sort/job1", method="POST"):
        response = views.reset_sort("job1").get_json()

    assert response["success"] is True
    assert (job_dir / ".new-reversals").exists()
    assert not (job_dir / ".sorted").exists()


def test_build_fasta_raises_missing_job_for_absent_directory(launched_app, tmp_path, monkeypatch):
    import dgenies.views as views
    from dgenies.lib.exceptions import DGeniesMissingJobError

    monkeypatch.setattr(views, "APP_DATA", str(tmp_path), raising=False)

    with pytest.raises(DGeniesMissingJobError):
        views.build_fasta("missing", False)


def test_build_fasta_raises_when_query_pointer_is_missing(launched_app, tmp_path, monkeypatch):
    import dgenies.views as views

    (tmp_path / "job1").mkdir()
    monkeypatch.setattr(views, "APP_DATA", str(tmp_path), raising=False)

    with pytest.raises(FileNotFoundError):
        views.build_fasta("job1", False)


def test_build_fasta_returns_done_for_existing_unsorted_query(launched_app, tmp_path, monkeypatch):
    import dgenies.views as views

    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    query = job_dir / "query.fa"
    query.write_text(">q\nAAAA\n")
    (job_dir / ".query").write_text(str(query))
    monkeypatch.setattr(views, "APP_DATA", str(tmp_path), raising=False)

    assert views.build_fasta("job1", False) == (2, False)


def test_build_fasta_starts_compression_when_gzip_requested(launched_app, tmp_path, monkeypatch):
    import dgenies.views as views

    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    query = job_dir / "query.fa"
    query.write_text(">q\nAAAA\n")
    (job_dir / ".query").write_text(str(query))
    monkeypatch.setattr(views, "APP_DATA", str(tmp_path), raising=False)
    starts = []

    class FakeTimer:
        def __init__(self, delay, fn, kwargs=None):
            self.delay = delay
            self.fn = fn
            self.kwargs = kwargs or {}

        def start(self):
            starts.append((self.delay, self.fn.__name__, self.kwargs["fasta_file"]))

    monkeypatch.setattr(views.threading, "Timer", FakeTimer)

    assert views.build_fasta("job1", True) == (1, False)
    assert starts == [(1, "compress_and_send_mail", str(query))]


def test_compute_summary_returns_file_not_found_when_paf_inputs_missing(launched_app, tmp_path, monkeypatch):
    import dgenies.views as views

    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    monkeypatch.setattr(views, "APP_DATA", str(tmp_path), raising=False)

    class MissingPaf:
        def __init__(self, *args, **kwargs):
            raise FileNotFoundError

    monkeypatch.setattr(views, "Paf", MissingPaf)

    assert views.compute_summary("job1") == (None, "file_not_found")


def test_compute_summary_returns_done_when_summary_already_exists(launched_app, tmp_path, monkeypatch):
    import dgenies.views as views

    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    monkeypatch.setattr(views, "APP_DATA", str(tmp_path), raising=False)

    class DonePaf:
        def __init__(self, *args, **kwargs):
            pass

        def get_summary_stats(self):
            return {"3": 100.0}

    monkeypatch.setattr(views, "Paf", DonePaf)

    assert views.compute_summary("job1") == ({"3": 100.0}, "done")


def test_summary_route_maps_done_summary_to_json(launched_app, monkeypatch):
    import dgenies.views as views

    monkeypatch.setattr(views, "compute_summary", lambda job_id: ({"3": 100.0}, "done"))

    with launched_app.test_request_context("/summary/job1", method="POST"):
        response = views.summary("job1").get_json()

    assert response == {"success": True, "status": "done", "percents": {"3": 100.0}}


def test_no_assoc_route_returns_file_content(launched_app, tmp_path, monkeypatch):
    import dgenies.views as views

    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    monkeypatch.setattr(views, "APP_DATA", str(tmp_path), raising=False)

    class FakePaf:
        def __init__(self, *args, **kwargs):
            pass

        def build_list_no_assoc(self, which):
            return ["q1", "q2"]

    monkeypatch.setattr(views, "Paf", FakePaf)

    with launched_app.test_request_context("/no-assoc/job1", method="POST", data={"to": "query"}):
        response = views.no_assoc("job1").get_json()

    assert response == {"file_content": "q1\nq2\n", "empty": False}


def test_prepare_fasta_route_reports_done(launched_app, monkeypatch):
    import dgenies.views as views

    monkeypatch.setattr(views, "build_fasta", lambda job_id, gzip: (2, True))

    with launched_app.test_request_context("/get-fasta-query/job1", method="POST", data={"gzip": "true"}):
        response = views.prepare_fasta("job1").get_json()

    assert response["success"] is True
    assert response["status"] == 2
    assert response["gzip"] is True


def test_post_query_as_reference_invokes_builder(launched_app, monkeypatch):
    import dgenies.views as views

    calls = []
    monkeypatch.setattr(views, "build_query_as_reference", lambda job_id: calls.append(job_id) or "/tmp/out.fa")

    with launched_app.test_request_context("/build-query-as-reference/job1", method="POST"):
        response = views.post_query_as_reference("job1").get_json()

    assert response == {"success": True}
    assert calls == ["job1"]
