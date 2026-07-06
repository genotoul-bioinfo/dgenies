from types import SimpleNamespace

import pytest


def make_align_job(dm, **overrides):
    payload = {
        "job_id": "job1",
        "type": dm.JobType.align,
        "query": "query.fa",
        "query_type": dm.FileType.local,
        "target": "target.fa",
        "target_type": dm.FileType.local,
        "tool": dm.ToolName.minimap2,
        "tool_options": ["repeat:many"],
    }
    payload.update(overrides)
    return dm.Job(**payload)


def make_plot_job(dm, **overrides):
    payload = {
        "job_id": "plot1",
        "type": dm.JobType.plot,
        "query": "query.fa",
        "query_type": dm.FileType.local,
        "target": "target.fa",
        "target_type": dm.FileType.local,
        "align": "map.paf",
        "align_type": dm.FileType.local,
        "tool": None,
        "tool_options": [],
    }
    payload.update(overrides)
    return dm.Job(**payload)


def test_get_max_file_size_uses_ava_limit_for_align_target(launched_app):
    import dgenies.api as api

    assert api.get_max_file_size("align", "target") == api.config_reader.max_upload_size_ava


def test_get_max_file_size_uses_default_limit_for_other_roles(launched_app):
    import dgenies.api as api

    assert api.get_max_file_size("align", "query") == api.config_reader.max_upload_size
    assert api.get_max_file_size("plot", "target") == api.config_reader.max_upload_size


def test_valid_email_rejects_missing_when_mandatory(launched_app, monkeypatch):
    import dgenies.api as api
    from dgenies.lib.exceptions import DGeniesValidationError

    monkeypatch.setattr(api.Functions, "is_email_mandatory", staticmethod(lambda: True), raising=False)

    with pytest.raises(DGeniesValidationError, match="Email not given"):
        api.valid_email("")


def test_valid_email_rejects_invalid_when_mandatory(launched_app, monkeypatch):
    import dgenies.api as api
    from dgenies.lib.exceptions import DGeniesValidationError

    monkeypatch.setattr(api.Functions, "is_email_mandatory", staticmethod(lambda: True), raising=False)

    with pytest.raises(DGeniesValidationError, match="Email is invalid"):
        api.valid_email("invalid")


def test_valid_email_allows_empty_when_not_mandatory(launched_app, monkeypatch):
    import dgenies.api as api

    monkeypatch.setattr(api.Functions, "is_email_mandatory", staticmethod(lambda: False), raising=False)

    assert api.valid_email(None) is None


def test_valid_align_requires_target(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm
    from dgenies.lib.exceptions import DGeniesValidationError

    with pytest.raises(DGeniesValidationError, match="'target' is required"):
        api.valid_align(make_align_job(dm, target=None))


def test_valid_align_requires_target_type(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm
    from dgenies.lib.exceptions import DGeniesValidationError

    with pytest.raises(DGeniesValidationError, match="'target_type' is required"):
        api.valid_align(make_align_job(dm, target_type=None))


def test_valid_align_adds_default_tool_when_missing(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm

    job = api.valid_align(make_align_job(dm, tool=None, tool_options=[]))

    assert job.tool == "minimap2"


def test_valid_align_rejects_unknown_option(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm
    from dgenies.lib.exceptions import DGeniesUnknownOptionError

    with pytest.raises(DGeniesUnknownOptionError):
        api.valid_align(make_align_job(dm, tool_options=["bad:option"]))


def test_valid_plot_requires_standard_triplet_without_backup(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm
    from dgenies.lib.exceptions import DGeniesValidationError

    with pytest.raises(DGeniesValidationError, match="'align' is required"):
        api.valid_plot(make_plot_job(dm, align=None))


def test_valid_plot_accepts_backup_payload(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm

    job = make_plot_job(dm, backup="backup.tar.gz", backup_type=dm.FileType.local)

    assert api.valid_plot(job).backup == "backup.tar.gz"


def test_valid_job_rejects_unsupported_type(launched_app):
    import dgenies.api as api
    from dgenies.lib.exceptions import DGeniesValidationError

    with pytest.raises(DGeniesValidationError, match="not supported"):
        api.valid_job(SimpleNamespace(type="batch"))


def test_valid_form_rejects_incorrect_job_count(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm
    from dgenies.lib.exceptions import DGeniesValidationError

    form = dm.BatchSubmissionQuery(batch_id="batch", email="u@example.org", nb_jobs=2, jobs=[make_align_job(dm)])

    with pytest.raises(DGeniesValidationError, match="Incorrect number of jobs"):
        api.valid_form(form)


def test_valid_form_rejects_empty_batch_id_for_multi_job(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm
    from dgenies.lib.exceptions import DGeniesValidationError

    form = dm.BatchSubmissionQuery(
        batch_id="",
        email="u@example.org",
        nb_jobs=2,
        jobs=[make_align_job(dm, job_id="a"), make_align_job(dm, job_id="b")],
    )

    with pytest.raises(DGeniesValidationError, match="Batch id is required"):
        api.valid_form(form)


def test_get_file_role_filters_local_and_url_roles(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm

    job = make_align_job(dm, query_type=dm.FileType.url, target_type=dm.FileType.local)

    assert list(api.get_file_role(job, ["local"])) == [("target.fa", "target")]
    assert list(api.get_file_role(job, ["url"])) == [("query.fa", "query")]


def test_get_file_role_for_plot_backup_uses_backup_only(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm

    job = make_plot_job(dm, backup="backup.tar.gz", backup_type=dm.FileType.local)

    assert list(api.get_file_role(job, ["local"])) == [("backup.tar.gz", "backup")]


def test_prepare_jobs_serializes_plot_backup(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm

    job = make_plot_job(dm, backup="backup.tar.gz", backup_type=dm.FileType.local)
    prepared = api.prepare_jobs("u@example.org", [job])[0]

    assert prepared["type"] == dm.JobType.plot
    assert prepared["backup"] == "backup.tar.gz"
    assert prepared["backup_type"] == "local"


def test_not_implemented_endpoints_return_501(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm

    path = dm.JobPath(job_id="job")

    for endpoint in [api.get_paf, api.get_backup, api.get_logs, api.get_viewer]:
        response, status = endpoint(path)
        assert status == 501
        assert response["message"] == "Not Implemented"


def test_post_free_noise_returns_501(launched_app):
    import dgenies.api as api
    from dgenies.api import datamodels as dm

    response, status = api.post_free_noise(dm.JobPath(job_id="job"), {})

    assert status == 501
    assert response["code"] == 501


def test_get_summary_maps_missing_file_to_404(launched_app, monkeypatch):
    import dgenies.api as api
    from dgenies.api import datamodels as dm

    monkeypatch.setattr(api, "compute_summary", lambda job_id: (None, "file_not_found"))

    response, status = api.get_summary(dm.JobPath(job_id="missing"))

    assert status == 404
    assert response["message"] == "Unable to load data!"


def test_get_summary_maps_failure_to_500(launched_app, monkeypatch):
    import dgenies.api as api
    from dgenies.api import datamodels as dm

    monkeypatch.setattr(api, "compute_summary", lambda job_id: (None, "fail"))

    response, status = api.get_summary(dm.JobPath(job_id="job"))

    assert status == 500
    assert "summary failed" in response["message"]


def test_prepare_fasta_query_reports_in_progress(launched_app, monkeypatch):
    import dgenies.api as api
    from dgenies.api import datamodels as dm

    monkeypatch.setattr(api, "build_fasta", lambda job_id, gzip: (1, False))

    response, status = api.prepare_fasta_query(dm.JobPath(job_id="job"), dm.PrepareFastaInput(gzip=True))

    assert status == 200
    assert response["data"]["status"] == dm.PrepareFastaEnum.in_progress


def test_prepare_fasta_query_reports_done(launched_app, monkeypatch):
    import dgenies.api as api
    from dgenies.api import datamodels as dm

    monkeypatch.setattr(api, "build_fasta", lambda job_id, gzip: (2, True))

    response, status = api.prepare_fasta_query(dm.JobPath(job_id="job"), dm.PrepareFastaInput(gzip=True))

    assert status == 200
    assert response["data"]["gzip"] is True


def test_prepare_fasta_query_maps_missing_job_to_404(launched_app, monkeypatch):
    import dgenies.api as api
    from dgenies.api import datamodels as dm
    from dgenies.lib.exceptions import DGeniesMissingJobError

    def raise_missing(job_id, gzip):
        raise DGeniesMissingJobError()

    monkeypatch.setattr(api, "build_fasta", raise_missing)

    response, status = api.prepare_fasta_query(dm.JobPath(job_id="missing"), dm.PrepareFastaInput(gzip=False))

    assert status == 404
    assert response["message"] == "Job doesn't exist"


def test_delete_job_returns_ok_when_job_is_missing(launched_app, monkeypatch):
    import dgenies.api as api
    from dgenies.api import datamodels as dm
    from dgenies.lib.exceptions import DGeniesMissingJobError

    class MissingJob:
        def __init__(self, id_job):
            pass

        def delete(self):
            raise DGeniesMissingJobError()

    monkeypatch.setattr(api, "JobManager", MissingJob)

    assert api.delete_job(dm.JobPath(job_id="missing")) == {"code": 0, "message": "ok"}


def test_delete_job_maps_gallery_forbidden_to_403(launched_app, monkeypatch):
    import dgenies.api as api
    from dgenies.api import datamodels as dm
    from dgenies.lib.exceptions import DGeniesDeleteGalleryJobForbidden

    class ForbiddenJob:
        def __init__(self, id_job):
            pass

        def delete(self):
            raise DGeniesDeleteGalleryJobForbidden()

    monkeypatch.setattr(api, "JobManager", ForbiddenJob)

    response, status = api.delete_job(dm.JobPath(job_id="gallery"))

    assert status == 403
    assert response["message"] == "Access denied"


def test_get_gallery_renames_id_job_to_job_id(launched_app, monkeypatch):
    import dgenies.api as api

    monkeypatch.setattr(api, "MODE", "webserver", raising=False)
    monkeypatch.setattr(
        api.Functions,
        "get_gallery_items",
        staticmethod(lambda: [{"id_job": "job1", "name": "Demo"}]),
        raising=False,
    )

    response = api.get_gallery()

    assert response["data"] == [{"name": "Demo", "job_id": "job1"}]


def test_get_example_files_omits_empty_config_entries(launched_app, monkeypatch):
    import dgenies.api as api

    monkeypatch.setattr(api.config_reader, "example_backup", "")
    monkeypatch.setattr(api.config_reader, "example_query", "/examples/query.fa")
    monkeypatch.setattr(api.config_reader, "example_target", "")

    response, status = api.get_example_files()

    assert status == 200
    assert response["data"] == ["example://query.fa"]
