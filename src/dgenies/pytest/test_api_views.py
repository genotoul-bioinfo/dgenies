from pathlib import Path

import pytest
from werkzeug.datastructures import ImmutableMultiDict


def test_api_pure_helpers_and_status_model(launched_app, tmp_path, monkeypatch):
    import dgenies.api as api_mod

    assert api_mod._fix_job_type("align") == "new"
    assert api_mod._fix_job_type("plot") == "plot"
    assert api_mod._fix_file_role("align") == "map"
    assert api_mod.get_percentage("getfiles") == 3.7
    assert api_mod.get_percentage("success") == 100
    assert api_mod.get_percentage("unknown") == 0

    status = api_mod.create_job_status({"id_job": "job1", "status": "succeed", "error": "", "has_logs": True})
    assert status.model_dump()["percent"] == 75.0
    assert status.error is None

    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    for name in (".sorted", "map.paf.sorted", "query.idx.sorted"):
        (job_dir / name).write_text("")
    monkeypatch.setattr(api_mod, "APP_DATA", str(tmp_path))
    assert api_mod.has_sorted_output("job1")

    assert api_mod.allowed_file_ext("query.fa", "new", "query")
    assert not api_mod.allowed_file_ext("query.exe", "new", "query")


def test_api_validation_prepare_jobs_and_gallery(launched_app, monkeypatch):
    import dgenies.api as api_mod
    from dgenies.api import datamodels as dm
    from dgenies.lib.exceptions import DGeniesValidationError

    job = dm.Job(
        job_id="job1",
        type=dm.JobType.align,
        target="target.fa",
        target_type=dm.FileType.local,
        query="query.fa",
        query_type=dm.FileType.local,
    )
    assert api_mod.valid_align(job).tool == "minimap2"
    assert list(api_mod.get_file_role(job, ["local"])) == [("query.fa", "query"), ("target.fa", "target")]

    missing = dm.Job(job_id="job2", type=dm.JobType.align)
    with pytest.raises(DGeniesValidationError, match="'target' is required"):
        api_mod.valid_align(missing)

    typed_job = dm.Job(
        job_id="job3",
        type=dm.JobType.align,
        target="target.fa",
        target_type=dm.FileType.local,
        tool=dm.ToolName.minimap2,
        tool_options=["repeat:many"],
    )
    prepared = api_mod.prepare_jobs("user@example.org", [typed_job])
    assert prepared[0]["options"] == "-f 0.02"
    assert prepared[0]["target_type"] == "local"

    form = dm.BatchSubmissionQuery(batch_id="", email="user@example.org", nb_jobs=1, jobs=[typed_job])
    api_mod.valid_form(form)

    monkeypatch.setattr(api_mod.config_reader, "example_backup", "/examples/demo.tar.gz")
    monkeypatch.setattr(api_mod.config_reader, "example_query", "/examples/query.fa")
    monkeypatch.setattr(api_mod.config_reader, "example_target", "")
    response, status = api_mod.get_example_files()
    assert status == 200
    assert response["data"] == ["example://demo.tar.gz", "example://query.fa"]


def test_view_inforun_parse_form_and_datafile_helpers(launched_app, tmp_path, monkeypatch):
    import dgenies.views as views
    from dgenies.lib.exceptions import DGeniesExampleInvalid

    monkeypatch.setattr(views.config_reader, "config_dir", str(tmp_path))
    (tmp_path / ".inforun").write_text('{"message": "Maintenance", "type": "warn"}')
    assert views.get_inforun() == {"message": "Maintenance", "type": "warn"}
    (tmp_path / ".inforun").write_text("{bad json")
    assert views.get_inforun() is None

    form = ImmutableMultiDict(
        [
            ("id_job", "job1"),
            ("type", "align"),
            ("email", "user@example.org"),
            ("nb_jobs", "1"),
            ("jobs[0][target]", "target.fa"),
            ("jobs[0][target_type]", "local"),
            ("jobs[0][query]", ""),
            ("jobs[0][tool_options][]", "repeat:many"),
        ]
    )
    id_job, job_type, email, nb_jobs, jobs = views.parse_form(form)
    assert (id_job, job_type, email, nb_jobs) == ("job1", "align", "user@example.org", 1)
    assert jobs[0]["target"] == "target.fa"
    assert jobs[0]["query"] is None
    assert jobs[0]["options"] == ["repeat:many"]

    upload_dir = tmp_path / "uploads" / "session1"
    upload_dir.mkdir(parents=True)
    (upload_dir / "query file.fa").write_text(">q\nAAAA\n")
    launched_app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    datafile = views.create_datafile("query file.fa", "local", "session1", [])
    assert datafile.get_type() == "local"
    assert Path(datafile.get_path()).name == "query_file.fa"

    example = tmp_path / "example.fa"
    example.write_text(">e\nAAAA\n")
    example_df = views.create_datafile("example://example.fa", "local", "unused", [str(example)])
    assert example_df.is_example()
    with pytest.raises(DGeniesExampleInvalid):
        views.create_datafile("example://missing.fa", "local", "unused", [str(example)])


def test_view_file_checks_batch_file_summary_and_build_fasta(launched_app, tmp_path, monkeypatch):
    import dgenies.views as views
    from dgenies.lib.datafile import DataFile
    from dgenies.lib.exceptions import DGeniesJobCheckError

    job = {
        "type": "align",
        "target": "target.fa",
        "target_type": "local",
        "query": None,
        "query_type": None,
        "tool": None,
        "options": ["repeat:many"],
    }
    views.check_file_type_and_resolv_options(job)
    assert job["tool"] == "minimap2"
    assert job["options"] == "-f 0.02"

    bad = dict(job, target="target.fa", target_type=None, options=["repeat:many"])
    with pytest.raises(DGeniesJobCheckError):
        views.check_file_type_and_resolv_options(bad)

    batch = tmp_path / "jobs.txt"
    batch_df = views.create_batch_file(
        str(batch),
        [
            {
                "type": "align",
                "id_job": "job1",
                "query": DataFile("Query", "/data/query.fa", "local"),
                "target": DataFile("Target", "/data/target.fa", "local"),
                "tool_options": "-x",
            }
        ],
    )
    assert batch_df.get_name() == "batch"
    assert "query=/data/query.fa" in batch.read_text()

    monkeypatch.setattr(views, "APP_DATA", str(tmp_path / "data"))
    assert views.compute_summary("missing") == (None, "job_not_found")

    job_dir = tmp_path / "data" / "job1"
    job_dir.mkdir(parents=True)
    query = job_dir / "query.fa"
    query.write_text(">q\nAAAA\n")
    (job_dir / ".query").write_text(str(query))
    assert views.build_fasta("job1", False) == (2, False)
