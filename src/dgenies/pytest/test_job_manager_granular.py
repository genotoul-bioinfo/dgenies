import gzip
import io
import os
import tarfile
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from dgenies.lib.datafile import DataFile
from dgenies.lib.exceptions import (
    DGeniesAlignmentFileInvalid,
    DGeniesAlignmentFileUnsupported,
    DGeniesBackupUnpackError,
    DGeniesDistantFileTypeUnsupported,
    DGeniesIndexFileInvalid,
    DGeniesMissingJobError,
    DGeniesNotGzipFileError,
    DGeniesUploadedFileSizeLimitError,
    DGeniesURLInvalid,
)


class _Query(list):
    def where(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self


class _Field:
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return True

    def __and__(self, other):
        return True


class _DummyConfig:
    def __init__(self, app_data):
        self.app_data = str(app_data)
        self.max_upload_size = 100
        self.max_upload_size_ava = 200
        self.send_mail_status = True
        self.web_url = "https://dgenies.example"
        self.send_mail_url = "https://notify.example"
        self.runner_type = "local"
        self.min_query_size = 50
        self.min_target_size = 50
        self.min_align_size = 50
        self.max_run_local = 4
        self.cluster_memory = 64
        self.cluster_memory_ava = 96
        self.cluster_walltime_align = "04:00:00"
        self.cluster_walltime_prepare = "00:30:00"
        self.cluster_prepare_script = "/cluster/prepare.py"
        self.cluster_python_exec = "/usr/bin/python3"
        self.drmaa_native_specs = "###DEFAULT###"
        self.analytics_enabled = False
        self.disable_anonymous_analytics = False
        self.anonymous_analytics = "groups"
        self.analytics_groups = [("staff", r".*@example\.org")]


class _DummyTool:
    def __init__(self, name="minimap2", split_before=False, parser=None):
        self.name = name
        self.label = name.upper()
        self.exec = f"/usr/bin/{name}"
        self.command_line = "{exe} --target {target} --query {query} --threads {threads} {options} > {out}"
        self.all_vs_all = "{exe} --target {target} --threads {threads} {options} > {out}"
        self.max_memory = 48
        self.threads = 4
        self.threads_cluster = 6
        self.parser = parser
        self.split_before = split_before


class _DummyTools:
    def __init__(self):
        self.tools = {
            "minimap2": _DummyTool("minimap2"),
            "splitter": _DummyTool("splitter", split_before=True),
            "parser_tool": _DummyTool("parser_tool", parser="mock_parser"),
        }

    def get_default(self):
        return "minimap2"


class _DummyAllowedExtensions:
    roles = {
        "new": {"query": ["fasta"], "target": ["fasta"]},
        "plot": {"query": ["fasta", "idx"], "target": ["fasta", "idx"], "align": ["map"], "backup": ["backup"]},
        "batch": {},
    }
    formats = {
        "fasta": {"extensions": ["fa", "fasta", "fa.gz"], "description": "a Fasta file"},
        "idx": {"extensions": ["idx"], "description": "an index file"},
        "map": {"extensions": ["paf", "maf"], "description": "an alignment file"},
        "backup": {"extensions": ["tar", "tar.gz"], "description": "a backup file"},
    }

    def get_roles(self, job_type):
        return list(self.roles.get(job_type, {}).keys())

    def get_formats(self, job_type, file_role):
        return list(self.roles.get(job_type, {}).get(file_role, []))

    def get_extensions(self, file_format):
        return list(self.formats[file_format]["extensions"])

    def get_description(self, file_format):
        return self.formats[file_format]["description"]


class _DummyJob:
    id_job = _Field()
    runner_type = _Field()
    status = _Field()
    _records = {}
    _current = None

    @classmethod
    def connect(cls):
        return nullcontext()

    @classmethod
    def reset(cls):
        cls._records = {}
        cls._current = None

    @classmethod
    def create(cls, **kwargs):
        record = SimpleNamespace(**kwargs)
        record.status = getattr(record, "status", "submitted")
        record.runner_type = getattr(record, "runner_type", "local")
        record.mem_peak = getattr(record, "mem_peak", None)
        record.time_elapsed = getattr(record, "time_elapsed", None)
        record.error = getattr(record, "error", "")

        def save():
            cls._records[record.id_job] = record
            cls._current = record

        def delete_instance():
            cls._records.pop(record.id_job, None)

        record.save = save
        record.delete_instance = delete_instance
        record.save()
        return record

    @classmethod
    def get(cls, *args, **kwargs):
        if "id_job" in kwargs:
            return cls._records[kwargs["id_job"]]
        if cls._current is not None:
            return cls._current
        if len(cls._records) == 1:
            return next(iter(cls._records.values()))
        raise KeyError("missing dummy job")

    @classmethod
    def select(cls):
        return _Query(list(cls._records.values()))


class _DummyGallery:
    @classmethod
    def select(cls):
        return _Query([])


@pytest.fixture
def jm_env(monkeypatch, tmp_path):
    import dgenies.lib.job_manager as module

    monkeypatch.setattr(module, "AppConfigReader", lambda *args, **kwargs: _DummyConfig(tmp_path), raising=False)
    monkeypatch.setattr(module, "Tools", _DummyTools, raising=False)
    monkeypatch.setattr(module, "AllowedExtensions", _DummyAllowedExtensions, raising=False)
    monkeypatch.setattr(module, "Job", _DummyJob, raising=False)
    monkeypatch.setattr(module, "Gallery", _DummyGallery, raising=False)
    monkeypatch.setattr(module, "DoesNotExist", KeyError, raising=False)
    monkeypatch.setattr(module, "MODE", "standalone", raising=False)
    _DummyJob.reset()
    return SimpleNamespace(module=module, JobManager=module.JobManager, Job=_DummyJob, root=tmp_path)


@pytest.fixture
def manager(jm_env):
    return make_manager(jm_env, "job")


def make_manager(env, job_id="job", **kwargs):
    manager = env.JobManager(id_job=job_id, **kwargs)
    Path(manager.output_dir).mkdir(parents=True, exist_ok=True)
    return manager


def datafile(tmp_path, name, content="x", type_f="local"):
    path = tmp_path / name
    path.write_text(content)
    return DataFile(Path(name).stem, str(path), type_f)


def make_backup(path):
    files = {
        "map.paf": "query\t4\t0\t4\t+\ttarget\t4\t0\t4\t4\t4\t255\n",
        "query.idx": "Query\nchr1\t4\n",
        "target.idx": "Target\nchr1\t4\n",
        "logs.txt": "log\n",
    }
    with tarfile.open(path, "w:gz") as tar:
        for name, content in files.items():
            item = path.parent / name
            item.write_text(content)
            tar.add(item, arcname=name)
            item.unlink()


def test_create_align_job_keeps_inputs_and_options(jm_env, tmp_path):
    query = datafile(tmp_path, "query.fa")
    target = datafile(tmp_path, "target.fa")

    job = jm_env.JobManager.create("align", "align", [{"query": query, "target": target, "tool": "minimap2", "options": "-x"}])

    assert job.query is query
    assert job.target is target
    assert job.tool_name == "minimap2"
    assert job.options == "-x"


def test_job_manager_module_keeps_public_import_contract():
    import dgenies.lib.job_manager as module

    assert module.JobManager.__name__ == "JobManager"
    assert module.DataFileContext.__name__ == "DataFileContext"
    assert module.DataFileContextManager.__name__ == "DataFileContextManager"
    assert hasattr(module, "requests")
    assert hasattr(module, "validators")


def test_create_plot_job_keeps_alignment_and_backup(jm_env, tmp_path):
    align = datafile(tmp_path, "map.paf")
    backup = datafile(tmp_path, "backup.tar.gz")

    job = jm_env.JobManager.create("plot", "plot", [{"align": align, "backup": backup}])

    assert job.align is align
    assert job.backup is backup
    assert job.tool is not None


def test_create_subjob_avoids_existing_directory(jm_env, tmp_path, monkeypatch):
    (tmp_path / "batch_abcde").mkdir()
    values = iter(["abcde", "vwxyz"])
    monkeypatch.setattr(jm_env.module.Functions, "random_string", staticmethod(lambda length: next(values)), raising=False)

    subjob = jm_env.JobManager.create_subjob("batch", {"type": "align", "target": datafile(tmp_path, "target.fa")})

    assert subjob.id_job == "batch_vwxyz"
    assert Path(subjob.output_dir).is_dir()


def test_repr_includes_non_empty_fields(manager, tmp_path):
    manager.target = datafile(tmp_path, "target.fa")

    assert "id_job:job" in repr(manager)
    assert "target:" in repr(manager)


def test_get_align_format_returns_last_suffix(jm_env):
    assert jm_env.JobManager.get_align_format("map.paf") == "paf"
    assert jm_env.JobManager.get_align_format("query.fa.gz") == "gz"


def test_get_file_size_reads_plain_file(manager, tmp_path):
    plain = tmp_path / "plain.txt"
    plain.write_text("1234567890")

    assert manager.get_file_size(str(plain)) == 10


def test_get_file_size_reads_uncompressed_gzip_size(manager, tmp_path):
    gz_path = tmp_path / "query.fa.gz"
    with gzip.open(gz_path, "wt") as handle:
        handle.write("A" * 12)

    assert manager.get_file_size(str(gz_path)) == 12


def test_do_align_depends_on_align_marker(manager):
    assert manager.do_align() is True
    Path(manager.output_dir, ".align").write_text("")
    assert manager.do_align() is False


def test_get_query_split_returns_original_when_tool_does_not_split(manager, tmp_path):
    manager.query = datafile(tmp_path, "query.fa.gz")
    manager.tool = _DummyTool(split_before=False)

    assert manager.get_query_split() == manager.query.get_path()


def test_get_query_split_removes_gzip_suffix_for_split_tool(manager, tmp_path):
    manager.query = datafile(tmp_path, "query.fa.gz")
    manager.tool = _DummyTool("splitter", split_before=True)

    assert manager.get_query_split().endswith("split_query.fa")


def test_set_role_align_sets_alignment_format(manager, tmp_path):
    align = datafile(tmp_path, "map.paf")

    manager.set_role("align", align)

    assert manager.align is align
    assert manager.aln_format == "paf"


def test_unset_role_clears_existing_role(manager, tmp_path):
    manager.target = datafile(tmp_path, "target.fa")

    manager.unset_role("target")

    assert manager.target is None


def test_set_inputs_from_res_dir_loads_dotfiles(jm_env, tmp_path):
    query = datafile(tmp_path, "query_sample.fa.gz")
    target = datafile(tmp_path, "target_reference.idx")
    align = datafile(tmp_path, "map.maf")
    manager = make_manager(jm_env, "inputs")
    Path(manager.output_dir, ".query").write_text(query.get_path())
    Path(manager.output_dir, ".target").write_text(target.get_path())
    Path(manager.output_dir, ".align").write_text(align.get_path())
    Path(manager.output_dir, ".jobs").write_text('[{"id_job": "sub"}]')

    manager.set_inputs_from_res_dir()

    assert manager.query.get_name() == "sample"
    assert manager.target.get_name() == "query"
    assert manager.align.get_path() == align.get_path()
    assert manager.aln_format == "maf"
    assert manager.batch == [{"id_job": "sub"}]


def test_check_job_success_reports_fail_without_raw_paf(manager):
    assert manager.check_job_success() == "fail"


def test_check_job_success_reports_no_match_for_empty_raw_paf(manager):
    Path(manager.paf_raw).write_text("")
    assert manager.check_job_success() == "no-match"


def test_check_job_success_reports_succeed_for_non_empty_raw_paf(manager):
    Path(manager.paf_raw).write_text("hit\n")
    assert manager.check_job_success() == "succeed"


def test_filtered_flags_read_marker_files(manager):
    Path(manager.output_dir, ".filter-query").write_text("")
    Path(manager.output_dir, ".filter-target").write_text("")

    assert manager.is_query_filtered()
    assert manager.is_target_filtered()


def test_get_query_target_names_reads_index_headers(manager):
    Path(manager.idx_q).write_text("Query\nchr1\t4\n")
    Path(manager.idx_t).write_text("Target\nchr1\t4\n")

    assert manager._get_query_target_names() == ("Query", "Target")


def test_get_query_target_names_suppresses_duplicate_query_name(manager):
    Path(manager.idx_q).write_text("Same\nchr1\t4\n")
    Path(manager.idx_t).write_text("Same\nchr1\t4\n")

    assert manager._get_query_target_names() == (None, "Same")


def test_success_mail_part_includes_result_link_and_filtered_notes(manager):
    Path(manager.output_dir, ".filter-query").write_text("")
    Path(manager.output_dir, ".filter-target").write_text("")

    message = manager.get_job_mail_part("success", "Target", "Query")

    assert "result/job" in message
    assert "filter-out/job/query" in message
    assert "filter-out/job/target" in message


def test_failure_mail_part_uses_error_and_logs(manager):
    Path(manager.logs).write_text("log")
    manager.error = "Error for #ID#<br/>Details"

    message = manager.get_job_mail_part("fail", "Target", "Query")

    assert "Error for job\nDetails" in message
    assert "logs/job" in message


def test_mail_subject_distinguishes_success_no_match_and_failure(manager):
    assert manager.get_mail_subject("success") == "DGenies - Job completed: job"
    assert manager.get_mail_subject("no-match") == "DGenies - Job completed: job"
    assert manager.get_mail_subject("fail") == "DGenies - Job failed: job"


def test_set_send_mail_toggles_no_mail_marker(jm_env, monkeypatch):
    monkeypatch.setattr(jm_env.module, "MODE", "webserver", raising=False)
    manager = make_manager(jm_env, "mail")

    manager.set_send_mail(False)
    assert manager.is_send_mail_allowed() is False
    manager.set_send_mail(True)
    assert manager.is_send_mail_allowed() is True


def test_anonymize_mail_returns_original_when_disabled(manager):
    manager.config.disable_anonymous_analytics = False
    assert manager._anonymize_mail_client("user@example.org") == "user@example.org"


def test_anonymize_mail_full_hash(manager):
    manager.config.disable_anonymous_analytics = True
    manager.config.anonymous_analytics = "full_hash"
    assert len(manager._anonymize_mail_client("user@example.org")) == 40


def test_anonymize_mail_group_match(manager):
    manager.config.disable_anonymous_analytics = True
    manager.config.anonymous_analytics = "groups"
    assert manager._anonymize_mail_client("user@example.org") == "staff"


def test_forge_align_command_uses_query_target_options_and_redirect(manager, tmp_path):
    manager.query = datafile(tmp_path, "query.fa")
    manager.target = datafile(tmp_path, "target.fa")
    manager.options = "-x asm5"

    exe, args, out_file = manager.forge_align_command()

    assert exe == "/usr/bin/minimap2"
    assert "--target" in args
    assert manager.target.get_path() in args
    assert manager.query.get_path() in args
    assert "-x asm5" in args
    assert out_file == manager.paf_raw


def test_forge_align_command_uses_all_vs_all_without_query(manager, tmp_path):
    manager.query = None
    manager.target = datafile(tmp_path, "target.fa")

    _, args, _ = manager.forge_align_command()

    assert "--query" not in args
    assert manager.target.get_path() in args


def test_get_runner_config_caps_start_memory_to_tool_max(manager):
    manager.target = DataFile("target", "target.fa", "local")
    manager.query = DataFile("query", "query.fa", "local")
    manager.config.cluster_memory = 80
    manager.tool.max_memory = 40

    assert manager._get_runner_config("start") == (40, 6, "04:00:00")


def test_get_runner_config_prepare_uses_fixed_light_resources(manager):
    assert manager._get_runner_config("prepare") == (8, 1, "00:30:00")


def test_getting_local_file_moves_uploaded_file(manager, tmp_path):
    source = tmp_path / "upload.fa"
    source.write_text(">q\nAAAA\n")
    file_obj = DataFile("query", str(source), "local")

    final_path = manager._getting_local_file(file_obj)

    assert Path(final_path).read_text() == ">q\nAAAA\n"
    assert not source.exists()


def test_getting_local_file_copies_example_file(manager, tmp_path):
    source = tmp_path / "example.fa"
    source.write_text(">e\nAAAA\n")
    file_obj = DataFile("query", str(source), "local", example=True)

    final_path = manager._getting_local_file(file_obj)

    assert Path(final_path).read_text() == ">e\nAAAA\n"
    assert source.exists()


def test_getting_local_file_raises_for_missing_source(manager, tmp_path):
    with pytest.raises(Exception, match="does not exists"):
        manager._getting_local_file(DataFile("query", str(tmp_path / "missing.fa"), "local"))


def test_normalize_files_prefixes_files_and_writes_dotfiles(jm_env, tmp_path):
    query = datafile(tmp_path, "query.fa")
    target = datafile(tmp_path, "target.fa")
    manager = make_manager(jm_env, "normalize", query=query, target=target)

    manager.normalize_files()

    assert Path(manager.output_dir, "query_query.fa").exists()
    assert Path(manager.output_dir, "target_target.fa").exists()
    assert Path(manager.output_dir, ".query").read_text().endswith("query_query.fa")
    assert Path(manager.output_dir, ".target").read_text().endswith("target_target.fa")


def test_get_filename_from_url_accepts_ftp(manager):
    assert manager._get_filename_from_url("ftp://example.org/data/query.fa") == "query.fa"


def test_get_filename_from_url_uses_content_disposition(manager, monkeypatch):
    import dgenies.lib.job_manager as job_manager_module

    response = SimpleNamespace(url="https://example.org/download", headers={"content-disposition": 'attachment; filename="query.fa.gz"'})
    monkeypatch.setattr(job_manager_module.requests, "head", lambda *args, **kwargs: response)

    assert manager._get_filename_from_url("https://example.org/download") == "query.fa.gz"


def test_get_filename_from_url_rejects_unknown_scheme(manager):
    with pytest.raises(DGeniesURLInvalid):
        manager._get_filename_from_url("file:///tmp/query.fa")


def test_download_file_streams_http_chunks(manager, monkeypatch):
    class Response:
        def iter_content(self, chunk_size):
            yield b"AA"
            yield b""
            yield b"CC"

    monkeypatch.setattr("dgenies.lib.job_manager.requests.get", lambda *args, **kwargs: Response())
    manager._filename_for_url["https://example.org/query.fa"] = "query.fa"

    filename, path = manager._download_file("https://example.org/query.fa")

    assert filename == "query.fa"
    assert Path(path).read_bytes() == b"AACC"


def test_check_url_rejects_remote_file_with_unsupported_extension(manager):
    remote = DataFile("remote", "https://example.org/query.exe", "URL")
    manager._filename_for_url[remote.get_path()] = "query.exe"

    with pytest.raises(DGeniesDistantFileTypeUnsupported):
        manager._check_url(remote, {("new", "query")})


def test_check_file_rejects_invalid_gzip(manager, tmp_path):
    bad_gz = tmp_path / "bad.fa.gz"
    bad_gz.write_text("not gzip")

    with pytest.raises(DGeniesNotGzipFileError):
        manager.check_file(DataFile("query", str(bad_gz), "local"), "query", 100, True)


def test_check_file_rejects_size_over_limit(manager, tmp_path):
    large = tmp_path / "large.fa"
    large.write_text("A" * 101)

    with pytest.raises(DGeniesUploadedFileSizeLimitError):
        manager.check_file(DataFile("query", str(large), "local"), "query", 100, True)


def test_check_file_rejects_unsupported_alignment_extension(manager, tmp_path):
    align = tmp_path / "map.sam"
    align.write_text("x")

    with pytest.raises(DGeniesAlignmentFileUnsupported):
        manager.check_file(DataFile("map", str(align), "local"), "align", 100, True)


def test_check_file_rejects_invalid_alignment_content(manager, tmp_path, monkeypatch):
    align = tmp_path / "map.paf"
    align.write_text("bad\n")
    monkeypatch.setattr("dgenies.lib.job_manager.validators.paf", lambda path: False)

    with pytest.raises(DGeniesAlignmentFileInvalid):
        manager.check_file(DataFile("map", str(align), "local"), "align", 100, True)


def test_check_file_rejects_invalid_index(manager, tmp_path, monkeypatch):
    idx = tmp_path / "query.idx"
    idx.write_text("bad\tfirst\n")
    monkeypatch.setattr("dgenies.lib.job_manager.validators.v_idx", lambda path: False)

    with pytest.raises(DGeniesIndexFileInvalid):
        manager.check_file(DataFile("query", str(idx), "local"), "query", 100, True)


def test_check_file_marks_cluster_when_file_exceeds_cluster_threshold(manager, tmp_path):
    manager.config.runner_type = "slurm"
    fasta = tmp_path / "query.fa"
    fasta.write_text("A" * 80)

    assert manager.check_file(DataFile("query", str(fasta), "local"), "query", 100, True) is False


def test_allowed_backup_files_keeps_allowed_and_not_ignored(jm_env):
    members = []
    for name in ["map.paf", "query.idx", "target.idx", "logs.txt", "other.txt"]:
        info = tarfile.TarInfo(name)
        info.size = 0
        members.append(info)

    kept = list(jm_env.JobManager.allowed_backup_files(members, {"map.paf", "query.idx", "target.idx", "logs.txt"}, {"logs.txt"}))

    assert [item.name for item in kept] == ["map.paf", "query.idx", "target.idx"]


def test_unpack_backup_extracts_valid_backup(manager, tmp_path):
    backup = tmp_path / "backup.tar.gz"
    make_backup(backup)
    out_dir = tmp_path / "unpacked"

    query, target, align = manager._unpack_backup(DataFile("backup", str(backup), "local"), str(out_dir))

    assert query.get_path().endswith("query.idx")
    assert target.get_path().endswith("target.idx")
    assert align.get_path().endswith("map.paf")


def test_unpack_backup_rejects_archive_with_unexpected_member(manager, tmp_path):
    backup = tmp_path / "bad.tar.gz"
    with tarfile.open(backup, "w:gz") as tar:
        bad = tmp_path / "bad.txt"
        bad.write_text("bad")
        tar.add(bad, arcname="bad.txt")

    with pytest.raises(DGeniesBackupUnpackError):
        manager._unpack_backup(DataFile("backup", str(backup), "local"), str(tmp_path / "bad-out"))


def test_write_and_read_jobs_round_trip(manager):
    child = make_manager(SimpleNamespace(JobManager=type(manager), root=Path(manager.config.app_data)), "child")
    child.get_job_type = lambda: "new"
    child.target = DataFile("target", "/data/target.fa", "local")

    manager.write_jobs([child])

    assert manager.read_jobs()[0]["id_job"] == "child"


def test_get_subjob_ids_returns_empty_when_batch_file_missing(manager):
    assert manager.get_subjob_ids() == []


def test_get_subjob_ids_reads_batch_file(manager):
    Path(manager.output_dir, ".batch").write_text("a\nb\n")
    assert manager.get_subjob_ids() == ["a", "b"]


def test_standalone_status_round_trip(manager):
    manager.set_status_standalone("fail", "boom")
    assert manager.get_status_standalone() == "fail"
    assert manager.get_status_standalone(with_error=True) == ["fail", "boom"]
    assert manager.status() == {"status": "fail", "mem_peak": None, "time_elapsed": None, "error": "boom"}


def test_status_reports_unknown_when_standalone_status_file_missing(manager):
    assert manager.status() == {"status": "unknown", "error": ""}


def test_delete_raises_for_missing_job_dir(jm_env):
    manager = jm_env.JobManager("missing")

    with pytest.raises(DGeniesMissingJobError):
        manager.delete()


def test_delete_removes_existing_job_dir(manager):
    manager.delete()
    assert not Path(manager.output_dir).exists()


def test_context_manager_collects_distinct_contexts(jm_env, tmp_path):
    from dgenies.lib.job_manager import DataFileContextManager

    target = datafile(tmp_path, "target.fa")
    job_a = make_manager(jm_env, "a", target=target)
    job_b = make_manager(jm_env, "b", target=target)

    contexts = DataFileContextManager([job_a, job_b])

    assert contexts.get_datafiles() == [target]
    assert contexts.get_distinct(target, "file_role") == {("target",)}
    assert contexts.get_distinct(target, "job") == {(job_a,), (job_b,)}


def test_context_manager_remove_deletes_only_matching_context(jm_env, tmp_path):
    from dgenies.lib.job_manager import DataFileContextManager

    target = datafile(tmp_path, "target.fa")
    job_a = make_manager(jm_env, "a", target=target)
    job_b = make_manager(jm_env, "b", target=target)
    contexts = DataFileContextManager([job_a, job_b])

    removed = contexts.remove(target, job=job_a)

    assert len(removed) == 1
    assert contexts.get_distinct(target, "job") == {(job_b,)}


def test_from_file_to_datafiles_reuses_cache(manager):
    cache = {}

    _, first = manager.from_file_to_datafiles("align", {"query": "/tmp/query.fa", "target": "/tmp/query.fa"}, cache)

    assert first["query"] is first["target"]
    assert cache["/tmp/query.fa"] is first["query"]


def test_to_job_list_pops_job_type(jm_env):
    jobs = [{"type": "align", "target": "target.fa"}]

    assert jm_env.JobManager.to_job_list(jobs) == [("align", {"target": "target.fa"})]


def test_as_job_entry_includes_roles_tool_and_options(jm_env, tmp_path):
    target = datafile(tmp_path, "target.fa")
    manager = make_manager(jm_env, "entry", target=target, options="-x")

    assert manager.as_job_entry() == {
        "type": "new",
        "id_job": "entry",
        "target": target.get_path(),
        "tool": "minimap2",
        "options": "-x",
    }
