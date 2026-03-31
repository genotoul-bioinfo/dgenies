"""JobManager-focused tests."""

import json
import os
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from dgenies.lib.datafile import DataFile
from dgenies.lib.exceptions import (
    DGeniesAlignmentFileInvalid,
    DGeniesAlignmentFileUnsupported,
    DGeniesBackupUnpackError,
    DGeniesClusterRunError,
    DGeniesDeleteGalleryJobForbidden,
    DGeniesDistantFileTypeUnsupported,
    DGeniesDownloadError,
    DGeniesFastaFileInvalid,
    DGeniesIndexFileInvalid,
    DGeniesLocalRunError,
    DGeniesMissingJobError,
    DGeniesMissingParserError,
    DGeniesNotGzipFileError,
    DGeniesRunError,
    DGeniesUploadedFileSizeLimitError,
    DGeniesURLInvalid,
    DgeniesMissingSubjobsError,
)


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyQuery(list):
    def where(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self


def _setup_job_manager_env(monkeypatch, tmp_path, mode="standalone"):
    import dgenies.lib.job_manager as job_manager_module

    class DummyConfig:
        def __init__(self, app_data):
            self.app_data = app_data
            self.max_upload_size = 10**6
            self.max_upload_size_ava = 2 * 10**6
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

    class DummyTool:
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

    class DummyTools:
        def __init__(self):
            self.tools = {
                "minimap2": DummyTool("minimap2"),
                "splitter": DummyTool("splitter", split_before=True),
                "parser_tool": DummyTool("parser_tool", parser="mock_parser"),
            }

        def get_default(self):
            return "minimap2"

    class DummyAllowedExtensions:
        formats = {
            "fasta": {
                "extensions": ["fa", "fasta", "fna", "fa.gz", "fasta.gz", "fna.gz"],
                "description": "a Fasta file",
            },
            "idx": {"extensions": ["idx"], "description": "an index file"},
            "map": {"extensions": ["maf", "paf"], "description": "an alignment file"},
            "backup": {"extensions": ["tar", "tar.gz"], "description": "a backup file"},
        }
        roles = {
            "new": {"query": ["fasta"], "target": ["fasta"]},
            "plot": {"query": ["fasta", "idx"], "target": ["fasta", "idx"], "align": ["map"], "backup": ["backup"]},
            "batch": {},
        }

        def get_roles(self, job_type):
            return list(self.roles.get(job_type, {}).keys())

        def get_formats(self, job_type, file_role):
            return list(self.roles.get(job_type, {}).get(file_role, []))

        def get_description(self, file_format):
            return self.formats[file_format]["description"]

        def get_extensions(self, file_format):
            return list(self.formats[file_format]["extensions"])

    class DummyJobModel:
        id_job = object()
        runner_type = object()
        status = object()
        _records = {}
        _current = None

        @classmethod
        def connect(cls):
            return _NullContext()

        @classmethod
        def reset(cls):
            cls._records = {}
            cls._current = None

        @classmethod
        def create(cls, **kwargs):
            record = SimpleNamespace(**kwargs)
            if not hasattr(record, "status"):
                record.status = "submitted"
            if not hasattr(record, "runner_type"):
                record.runner_type = "local"
            if not hasattr(record, "mem_peak"):
                record.mem_peak = None
            if not hasattr(record, "time_elapsed"):
                record.time_elapsed = None
            if not hasattr(record, "error"):
                record.error = ""

            def save():
                cls._records[record.id_job] = record
                cls._current = record

            def delete_instance():
                cls._records.pop(record.id_job, None)
                if cls._current is record:
                    cls._current = next(iter(cls._records.values()), None)

            record.save = save
            record.delete_instance = delete_instance
            record.save()
            return record

        @classmethod
        def get(cls, *_args, **kwargs):
            if "id_job" in kwargs:
                return cls._records[kwargs["id_job"]]
            if cls._current is not None:
                return cls._current
            if len(cls._records) == 1:
                return next(iter(cls._records.values()))
            raise KeyError("Missing dummy job record")

        @classmethod
        def select(cls):
            return _DummyQuery(list(cls._records.values()))

    class DummySessionModel:
        _records = {}

        @classmethod
        def new(cls, keep_active=False):
            s_id = f"session_{len(cls._records) + 1}"
            record = SimpleNamespace(s_id=s_id, status="pending", keep_active=keep_active)

            def ask_for_upload(change_status=False):
                if change_status:
                    record.status = "active"
                return True

            def save():
                cls._records[record.s_id] = record

            def delete_instance():
                cls._records.pop(record.s_id, None)

            record.ask_for_upload = ask_for_upload
            record.save = save
            record.delete_instance = delete_instance
            record.save()
            return s_id

        @classmethod
        def get(cls, **kwargs):
            return cls._records[kwargs["s_id"]]

    class DummyGalleryModel:
        @classmethod
        def select(cls):
            return _DummyQuery([])

    monkeypatch.setattr(
        job_manager_module,
        "AppConfigReader",
        lambda *_args, **_kwargs: DummyConfig(str(tmp_path)),
        raising=False,
    )
    monkeypatch.setattr(job_manager_module, "Tools", DummyTools, raising=False)
    monkeypatch.setattr(job_manager_module, "AllowedExtensions", DummyAllowedExtensions, raising=False)
    monkeypatch.setattr(job_manager_module, "Job", DummyJobModel, raising=False)
    monkeypatch.setattr(job_manager_module, "Session", DummySessionModel, raising=False)
    monkeypatch.setattr(job_manager_module, "Gallery", DummyGalleryModel, raising=False)
    monkeypatch.setattr(job_manager_module, "DoesNotExist", KeyError, raising=False)
    monkeypatch.setattr(job_manager_module, "MODE", mode, raising=False)
    DummyJobModel.reset()
    DummySessionModel._records = {}

    return SimpleNamespace(
        module=job_manager_module,
        JobManager=job_manager_module.JobManager,
        DummyJob=DummyJobModel,
        DummySession=DummySessionModel,
        DummyTool=DummyTool,
    )


def _make_manager(env, job_id="job", **kwargs):
    manager = env.JobManager(id_job=job_id, **kwargs)
    Path(manager.output_dir).mkdir(parents=True, exist_ok=True)
    return manager


def _build_backup(backup_path):
    files = {
        "map.paf": "query\t4\t0\t4\t+\ttarget\t4\t0\t4\t4\t4\t255\n",
        "query.idx": "Query\nchr1\t4\n",
        "target.idx": "Target\nchr1\t4\n",
        "logs.txt": "log line\n",
    }
    with tarfile.open(backup_path, "w:gz") as tar:
        for name, content in files.items():
            tmp_file = backup_path.parent / name
            tmp_file.write_text(content)
            tar.add(tmp_file, arcname=name)
            tmp_file.unlink()


def test_job_manager_creation_and_basic_helpers(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path)
    module = env.module

    plain = tmp_path / "plain.txt"
    plain.write_text("1234567890")
    gz_path = tmp_path / "data.fa.gz"
    import gzip

    with gzip.open(gz_path, "wt") as gz_out:
        gz_out.write("abcdefghij")

    query = DataFile("query", str(tmp_path / "query_reads.fa.gz"), "local")
    target = DataFile("target", str(tmp_path / "target_ref.fa.gz"), "local")
    align = DataFile("map", str(tmp_path / "map.paf"), "local")
    backup = DataFile("backup", str(tmp_path / "backup.tar.gz"), "local")
    for datafile in (query, target, align, backup):
        Path(datafile.get_path()).write_text("x")

    align_job = module.JobManager.create(
        "align_job",
        "align",
        [{"query": query, "target": target, "tool": "minimap2", "options": ["-x asm5"]}],
        email="user@example.org",
    )
    assert align_job.query is query
    assert align_job.target is target
    assert align_job.tool_name == "minimap2"
    assert align_job.options == ["-x asm5"]

    plot_job = module.JobManager.create(
        "plot_job",
        "plot",
        [{"query": query, "target": target, "align": align, "backup": backup}],
        email="user@example.org",
    )
    assert plot_job.align is align
    assert plot_job.backup is backup

    subjob_base = {"type": "align", "query": query, "target": target, "tool": "minimap2"}
    collision_dir = tmp_path / "batch_abcde"
    collision_dir.mkdir()
    random_values = iter(["abcde", "vwxyz"])
    monkeypatch.setattr(
        module.Functions,
        "random_string",
        staticmethod(lambda _length: next(random_values)),
        raising=False,
    )
    subjob = module.JobManager.create_subjob("batch", dict(subjob_base), email="user@example.org")
    assert subjob.id_job == "batch_vwxyz"
    assert Path(subjob.output_dir).exists()

    jm = _make_manager(env, "jm_test", query=query, target=target, tool="minimap2")
    assert module.JobManager.get_align_format("/path/to/map.paf") == "paf"
    assert module.JobManager.get_align_format("reads.fa.gz") == "gz"
    assert jm.do_align() is True
    Path(jm.output_dir, ".align").write_text("")
    assert jm.do_align() is False
    assert jm.get_file_size(str(plain)) == 10
    assert jm.get_file_size(str(gz_path)) == 10

    jm.query = SimpleNamespace(get_path=lambda: "/data/query.fa.gz")
    jm.tool = env.DummyTool("minimap2", split_before=False)
    assert jm.get_query_split() == "/data/query.fa.gz"
    jm.tool = env.DummyTool("splitter", split_before=True)
    assert jm.get_query_split().endswith("split_query.fa")

    jm.set_role("align", align)
    assert jm.align is align
    assert jm.aln_format == "paf"
    jm.unset_role("align")
    assert jm.align is None
    assert "id_job:jm_test" in repr(jm)

    assert jm.is_align() is True
    jm.is_plot()
    assert jm.is_ava() is False
    assert jm.get_job_type() == "new"
    assert jm.get_file_size_for_role("target") == jm.config.max_upload_size


def test_job_manager_set_inputs_and_mail_helpers(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path, mode="webserver")
    jm = _make_manager(env, "mail_job", tool="minimap2")

    query_path = Path(jm.output_dir, "query_sample.fa.gz")
    target_path = Path(jm.output_dir, "target_reference.idx")
    align_path = Path(jm.output_dir, "map.maf")
    query_path.write_text(">q\nACGT\n")
    target_path.write_text("Target\nchr1\t4\n")
    align_path.write_text("dummy\n")
    Path(jm.output_dir, ".query").write_text(str(query_path))
    Path(jm.output_dir, ".target").write_text(str(target_path))
    Path(jm.output_dir, ".align").write_text(str(align_path))
    Path(jm.output_dir, ".jobs").write_text(json.dumps([{"id_job": "subjob"}]))
    Path(jm.output_dir, ".filter-query").write_text("")
    Path(jm.output_dir, ".filter-target").write_text("")
    Path(jm.logs).write_text("error log\n")
    Path(jm.idx_q).write_text("QueryAlpha\nchr1\t4\n")
    Path(jm.idx_t).write_text("TargetAlpha\nchr1\t4\n")

    jm.set_inputs_from_res_dir()
    assert jm.query.get_name() == "sample"
    assert jm.target.get_name() == "query"
    assert jm.align.get_path() == str(align_path)
    assert jm.aln_format == "maf"
    assert jm.batch == [{"id_job": "subjob"}]
    assert jm.check_job_success() == "fail"
    Path(jm.paf_raw).write_text("")
    assert jm.check_job_success() == "no-match"
    Path(jm.paf_raw).write_text("content\n")
    assert jm.check_job_success() == "succeed"
    assert jm.is_query_filtered() is True
    assert jm.is_target_filtered() is True
    assert jm._get_query_target_names() == ("QueryAlpha", "TargetAlpha")
    Path(jm.idx_q).write_text("TargetAlpha\n")
    assert jm._get_query_target_names() == (None, "TargetAlpha")

    success_part = jm.get_job_mail_part("success", "TargetAlpha", "QueryAlpha")
    assert "result/mail_job" in success_part
    assert "filter-out/mail_job/target" in success_part
    assert "filter-out/mail_job/query" in success_part

    jm.error = "Detailed error for #ID#<br/>Please inspect the logs."
    fail_part = jm.get_job_mail_part("fail", "TargetAlpha", "QueryAlpha")
    assert "Detailed error for mail_job" in fail_part
    assert "logs/mail_job" in fail_part

    message = jm.get_mail_content("success", "TargetAlpha", "QueryAlpha")
    assert message.startswith("D-Genies")
    assert message.endswith("The D-Genies team")

    jm.batch = None
    html = jm.get_mail_content_html("success", "TargetAlpha", "QueryAlpha")
    assert "Your job mail_job was completed successfully" in html
    assert "TargetAlpha" in html
    assert "QueryAlpha" in html

    assert jm.get_mail_subject("success") == "DGenies - Job completed: mail_job"
    assert jm.get_mail_subject("no-match") == "DGenies - Job completed: mail_job"
    assert jm.get_mail_subject("fail") == "DGenies - Job failed: mail_job"

    assert jm.is_send_mail_allowed() is True
    jm.set_send_mail(False)
    assert jm.is_send_mail_allowed() is False
    jm.set_send_mail(True)
    assert jm.is_send_mail_allowed() is True

    jm.config.disable_anonymous_analytics = True
    jm.config.anonymous_analytics = "full_hash"
    full_hash = jm._anonymize_mail_client("user@example.org")
    assert len(full_hash) == 40
    jm.config.anonymous_analytics = "dual_hash"
    dual_hash = jm._anonymize_mail_client("user@example.org")
    assert "@" in dual_hash and dual_hash.split("@", 1)[0] != "user"
    jm.config.anonymous_analytics = "groups"
    assert jm._anonymize_mail_client("user@example.org") == "staff"


def test_job_manager_batch_mail_and_prepare_batch(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path)
    parent = _make_manager(env, "batch_parent", tool=None)

    subjobs = []
    for job_id, status in (("sub1", "success"), ("sub2", "no-match")):
        query = DataFile("query", str(tmp_path / f"{job_id}_query.fa"), "local")
        target = DataFile("target", str(tmp_path / f"{job_id}_target.fa"), "local")
        Path(query.get_path()).write_text(">q\nACGT\n")
        Path(target.get_path()).write_text(">t\nACGT\n")
        subjob = _make_manager(env, job_id, query=query, target=target, tool="minimap2")
        Path(subjob.output_dir, ".query").write_text(query.get_path())
        Path(subjob.output_dir, ".target").write_text(target.get_path())
        Path(subjob.idx_q).write_text(f"{job_id}_query\nchr1\t4\n")
        Path(subjob.idx_t).write_text(f"{job_id}_target\nchr1\t4\n")
        if status == "success":
            Path(subjob.output_dir, ".filter-target").write_text("")
        subjob.set_status_standalone(status, "")
        subjobs.append(subjob)

    parent.batch = subjobs
    Path(parent.output_dir, ".batch").write_text("sub1\nsub2\n")
    parent.write_jobs(subjobs)
    assert {entry["id_job"] for entry in parent.read_jobs()} == {"sub1", "sub2"}
    assert parent.get_subjob_ids() == ["sub1", "sub2"]

    batch_text = parent.get_batch_mail_part("success")
    assert "Here the detail of each job" in batch_text
    assert "sub1" in batch_text and "sub2" in batch_text
    batch_html = parent.get_mail_content_html("success", None)
    assert "Your batch job batch_parent was completed successfully" in batch_html
    assert "Job sub1 was completed successfully" in batch_html

    launch_calls = []

    def fake_launch_standalone(self, sync=False):
        launch_calls.append((self.id_job, sync))
        self.set_status_standalone("success" if self.id_job == "sub1" else "no-match")

    monkeypatch.setattr(env.module.JobManager, "launch_standalone", fake_launch_standalone, raising=False)
    parent.prepare_job()
    assert parent.get_status_standalone() == "success"
    assert launch_calls == [("sub1", True), ("sub2", True)]
    assert parent.refresh_batch_status() == "success"

    empty_parent = _make_manager(env, "batch_empty", tool=None)
    empty_parent.batch = []
    Path(empty_parent.output_dir, ".jobs").write_text("[]")
    with pytest.raises(DgeniesMissingSubjobsError):
        empty_parent.prepare_batch()


def test_job_manager_send_mail_and_launch_helpers(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path, mode="webserver")
    jm = _make_manager(
        env,
        "runner_job",
        query=DataFile("query", str(tmp_path / "query.fa"), "local"),
        target=DataFile("target", str(tmp_path / "target.fa"), "local"),
        tool="minimap2",
    )
    Path(jm.query.get_path()).write_text(">q\nACGT\n")
    Path(jm.target.get_path()).write_text(">t\nACGT\n")
    Path(jm.idx_q).write_text("Query\nchr1\t4\n")
    Path(jm.idx_t).write_text("Target\nchr1\t4\n")
    Path(jm.logs).write_text("existing\n")

    env.DummyJob.create(
        id_job=jm.id_job,
        email="user@example.org",
        status="success",
        error="",
        runner_type="local",
        date_created=datetime.now(),
        tool=jm.tool_name,
        options=jm.options,
    )

    sent_mails = []
    jm.mailer = SimpleNamespace(send_mail=lambda **kwargs: sent_mails.append(kwargs))
    jm.send_mail_if_allowed()
    assert sent_mails[0]["recipients"] == ["user@example.org"]
    assert sent_mails[0]["subject"] == "DGenies - Job completed: runner_job"
    assert "Query" in sent_mails[0]["message"]

    monkeypatch.setattr(
        env.module.Functions,
        "random_string",
        staticmethod(lambda _length: "A" * 15),
        raising=False,
    )
    posted_requests = []

    class FakeResponse:
        def getcode(self):
            return 200

    monkeypatch.setattr(
        env.module.request,
        "urlopen",
        lambda req: posted_requests.append(req) or FakeResponse(),
        raising=False,
    )
    jm.send_mail_post_if_allowed()
    assert Path(jm.output_dir, ".key").read_text() == "A" * 15
    assert posted_requests[0].get_full_url() == "https://notify.example/send-mail/runner_job"

    logged_errors = []
    monkeypatch.setattr(jm.logger, "error", lambda message: logged_errors.append(str(message)), raising=False)
    monkeypatch.setattr(
        env.module.request,
        "urlopen",
        lambda _req: (_ for _ in ()).throw(env.module.URLError("network down")),
        raising=False,
    )
    jm.send_mail_post_if_allowed()
    assert any("Send mail failed" in message for message in logged_errors)

    monkeypatch.setattr(
        env.module.subprocess,
        "check_output",
        lambda *_args, **_kwargs: b"[morecore] insufficient memory\n[morecore] 1024 bytes requested but not available.\n",
        raising=False,
    )
    assert "memory limit exceeded" in jm.search_error()

    exe, args, out_file = jm.forge_align_command()
    assert exe == "/usr/bin/minimap2"
    assert "--query" in args
    assert out_file == jm.paf_raw
    jm.query = None
    _, ava_args, _ = jm.forge_align_command()
    assert "--query" not in ava_args
    assert jm.is_ava() is True
    assert jm.get_file_size_for_role("target") == jm.config.max_upload_size_ava

    popen_returns = iter(
        [
            SimpleNamespace(pid=321, returncode=0, wait=lambda: None),
            SimpleNamespace(pid=654, returncode=1, wait=lambda: None),
        ]
    )
    monkeypatch.setattr(env.module.subprocess, "Popen", lambda *_args, **_kwargs: next(popen_returns), raising=False)
    monkeypatch.setattr(jm, "check_job_success", lambda: "no-match", raising=False)
    analytics_updates = []
    monkeypatch.setattr(jm, "_set_analytics_job_status", lambda status: analytics_updates.append(status), raising=False)
    jm.query = DataFile("query", str(tmp_path / "query.fa"), "local")
    jm._launch_local()
    db_job = env.DummyJob.get()
    assert db_job.id_process == 321
    assert db_job.status == "no-match"
    assert analytics_updates == ["no-match"]

    monkeypatch.setattr(jm, "search_error", lambda: "mapped failure", raising=False)
    with pytest.raises(DGeniesLocalRunError, match="mapped failure"):
        jm._launch_local()

    monkeypatch.setattr(
        env.module.subprocess,
        "check_output",
        lambda *_args, **_kwargs: b"COMPLETED|2048K|01:02:03",
        raising=False,
    )
    assert jm.check_job_status_slurm() is True
    assert "3723 2048" in Path(jm.logs).read_text()

    monkeypatch.setattr(
        env.module.subprocess,
        "check_output",
        lambda *_args, **_kwargs: (
            "failed       0\n"
            "start_time   Mon Jan 01 00:00:00 2024\n"
            "end_time     Mon Jan 01 00:10:00 2024\n"
        ).encode(),
        raising=False,
    )
    assert jm.check_job_status_sge() is True

    monkeypatch.setattr(
        env.module.Index,
        "load",
        staticmethod(lambda *_args, **_kwargs: ("name", [], {}, {}, {}, 400000000)),
        raising=False,
    )
    assert jm._get_runner_config("prepare") == (8, 1, jm.config.cluster_walltime_prepare)
    jm.query = None
    memory, threads, walltime = jm._get_runner_config("start")
    assert (memory, threads, walltime) == (32, 6, jm.config.cluster_walltime_align)

    cluster_log = Path(jm.logs + ".cluster")
    cluster_log.write_text("cluster output\n")
    template_state = {}

    class FakeSession:
        def createJobTemplate(self):
            template_state["template"] = SimpleNamespace()
            return template_state["template"]

        def runJob(self, job_template):
            template_state["submitted"] = job_template
            return "12345"

        def wait(self, _jobid, _timeout):
            return SimpleNamespace(hasExited=True)

        def deleteJobTemplate(self, _job_template):
            template_state["deleted"] = True

    monkeypatch.setitem(sys.modules, "drmaa", SimpleNamespace(Session=SimpleNamespace(TIMEOUT_WAIT_FOREVER=-1)))
    monkeypatch.setitem(
        sys.modules,
        "dgenies.lib.drmaasession",
        SimpleNamespace(DrmaaSession=lambda: SimpleNamespace(session=FakeSession())),
    )
    job_updates = []
    monkeypatch.setattr(jm, "update_job_status", lambda status, pid=None: job_updates.append((status, pid)), raising=False)
    monkeypatch.setattr(jm, "check_job_status_slurm", lambda: True, raising=False)
    jm.launch_to_cluster(
        step="start",
        runner_type="slurm",
        command="/usr/bin/minimap2",
        args=["--preset", "asm5"],
        log_out=str(cluster_log),
        log_err=str(cluster_log),
        scheduled_status="scheduled-cluster",
    )
    assert job_updates == [("scheduled-cluster", "12345")]
    assert template_state["submitted"].nativeSpecification == "--mem-per-cpu=5333 --nodes=1 --mincpus=6 --cpus-per-task=6 --time=04:00:00"
    assert template_state["deleted"] is True

    error_log = Path(tmp_path, "cluster.err")
    error_log.write_text("###ERR### cluster parser failed\n")
    assert env.module.JobManager.find_error_in_log(str(error_log)) == "cluster parser failed"
    monkeypatch.setattr(jm, "launch_to_cluster", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(jm, "check_job_success", lambda: "success", raising=False)
    final_statuses = []
    monkeypatch.setattr(jm, "update_job_status", lambda status, pid=None: final_statuses.append((status, pid)), raising=False)
    jm._launch_drmaa("slurm")
    assert final_statuses[-1] == ("success", None)


def test_job_manager_file_transfer_validation_and_context_helpers(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path)
    jm = _make_manager(env, "files_job", tool="minimap2")

    src_example = tmp_path / "example.fa"
    src_example.write_text(">q\nACGT\n")
    copied_path = jm._getting_local_file(DataFile("example", str(src_example), "local", example=True))
    assert Path(copied_path).exists()
    assert src_example.exists()

    src_local = tmp_path / "uploaded.fa"
    src_local.write_text(">q\nACGT\n")
    moved_path = jm._getting_local_file(DataFile("upload", str(src_local), "local"))
    assert Path(moved_path).exists()
    assert not src_local.exists()

    with pytest.raises(Exception, match="does not exists"):
        jm._getting_local_file(DataFile("missing", str(tmp_path / "missing.fa"), "local"))

    head_calls = []

    class FakeHeadResponse:
        url = "https://example.org/downloads/reference.fa.gz"
        headers = {"content-disposition": 'attachment; filename="real_reference.fa.gz"'}

    monkeypatch.setattr(
        env.module.requests,
        "head",
        lambda url, allow_redirects=True: head_calls.append(url) or FakeHeadResponse(),
        raising=False,
    )
    assert jm._get_filename_from_url("https://example.org/data") == "real_reference.fa.gz"
    assert jm._get_filename_from_url("https://example.org/data") == "real_reference.fa.gz"
    assert head_calls == ["https://example.org/data"]
    assert jm._get_filename_from_url("ftp://example.org/path/query.fa.gz") == "query.fa.gz"

    monkeypatch.setattr(
        env.module.requests,
        "head",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(env.module.ConnectionError("offline")),
        raising=False,
    )
    with pytest.raises(DGeniesURLInvalid):
        jm._get_filename_from_url("https://offline.example")

    collision = Path(jm.output_dir, "download")
    collision.mkdir()
    Path(collision, "real_reference.fa.gz").write_text("existing\n")
    monkeypatch.setattr(jm, "_get_filename_from_url", lambda _url: "real_reference.fa.gz", raising=False)

    class FakeGetResponse:
        def iter_content(self, chunk_size=1024):
            assert chunk_size == 1024
            yield b"AC"
            yield b"GT"

    monkeypatch.setattr(env.module.requests, "get", lambda *_args, **_kwargs: FakeGetResponse(), raising=False)
    distant_name, downloaded_path = jm._download_file("https://example.org/reference.fa.gz")
    assert distant_name == "real_reference.fa.gz"
    assert Path(downloaded_path).name == "1_real_reference.fa.gz"
    assert Path(downloaded_path).read_bytes() == b"ACGT"

    retrieved = []
    monkeypatch.setattr(env.module, "urlretrieve", lambda url, dest: retrieved.append((url, dest)), raising=False)
    monkeypatch.setattr(jm, "_get_filename_from_url", lambda _url: "ftp.fa.gz", raising=False)
    ftp_name, ftp_path = jm._download_file("ftp://example.org/ftp.fa.gz")
    assert ftp_name == "ftp.fa.gz"
    assert retrieved == [("ftp://example.org/ftp.fa.gz", ftp_path)]

    monkeypatch.setattr(jm, "_download_file", lambda _url: ("/tmp/query.fa.gz", str(tmp_path / "query.fa.gz")), raising=False)
    query_url = DataFile.create("query.fa.gz", "https://example.org/query.fa.gz")
    dl_path, dl_name = jm._getting_file_from_url(query_url)
    assert dl_path == str(tmp_path / "query.fa.gz")
    assert dl_name == "query"

    monkeypatch.setattr(
        jm,
        "_download_file",
        lambda _url: (_ for _ in ()).throw(env.module.URLError("down")),
        raising=False,
    )
    with pytest.raises(DGeniesURLInvalid):
        jm._getting_file_from_url(query_url)

    monkeypatch.setattr(
        env.module.Functions,
        "allowed_file",
        staticmethod(lambda filename, formats: filename.endswith(".fa.gz") and "fasta" in formats),
        raising=False,
    )
    jm._check_url(DataFile.create("query.fa.gz", "https://example.org/query.fa.gz"), [("new", "query")])
    monkeypatch.setattr(env.module.Functions, "allowed_file", staticmethod(lambda *_args, **_kwargs: False), raising=False)
    with pytest.raises(DGeniesDistantFileTypeUnsupported):
        jm._check_url(DataFile.create("query.fa.gz", "https://example.org/query.fa.gz"), [("new", "query")])

    bad_gz = tmp_path / "query.fa.gz"
    bad_gz.write_text("not gz\n")
    monkeypatch.setattr(env.module.Functions, "is_gz_file", staticmethod(lambda _path: False), raising=False)
    with pytest.raises(DGeniesNotGzipFileError):
        jm.check_file(DataFile("query", str(bad_gz), "local"), "query", jm.config.max_upload_size, True)

    plain = tmp_path / "query.fa"
    plain.write_text(">q\nACGT\n")
    monkeypatch.setattr(env.module.Functions, "is_gz_file", staticmethod(lambda _path: True), raising=False)
    monkeypatch.setattr(jm, "get_file_size", lambda _path: 11, raising=False)
    with pytest.raises(DGeniesUploadedFileSizeLimitError):
        jm.check_file(DataFile("query", str(plain), "local"), "query", 10, True)

    align_invalid = tmp_path / "align.sam"
    align_invalid.write_text("bad\n")
    with pytest.raises(DGeniesAlignmentFileUnsupported):
        jm.check_file(DataFile("align", str(align_invalid), "local"), "align", 100, True)

    align_bad = tmp_path / "align.paf"
    align_bad.write_text("bad\n")
    monkeypatch.setattr(env.module.validators, "paf", lambda _path: False, raising=False)
    with pytest.raises(DGeniesAlignmentFileInvalid):
        jm.check_file(DataFile("align", str(align_bad), "local"), "align", 100, True)

    index_file = tmp_path / "query.idx"
    index_file.write_text("bad idx\n")
    monkeypatch.setattr(env.module.validators, "v_idx", lambda _path: False, raising=False)
    with pytest.raises(DGeniesIndexFileInvalid):
        jm.check_file(DataFile("query", str(index_file), "local"), "query", 100, True)

    jm.config.runner_type = "slurm"
    jm.config.min_query_size = 5
    monkeypatch.setattr(env.module.validators, "v_idx", lambda _path: True, raising=False)
    monkeypatch.setattr(jm, "get_file_size", lambda _path: 10, raising=False)
    should_be_local = jm.check_file(DataFile("query", str(index_file), "local"), "query", 100, True)
    assert should_be_local is False

    local_shared = DataFile("shared_query", str(tmp_path / "shared_query.fa"), "local")
    remote_shared = DataFile.create("remote_target.fa.gz", "https://example.org/remote_target.fa.gz")
    Path(local_shared.get_path()).write_text(">q\nACGT\n")
    job = _make_manager(env, "context_job", query=local_shared, target=remote_shared, tool="minimap2")
    dcm = env.module.DataFileContextManager([job])
    assert dcm.get_distinct(local_shared, "file_role") == {("query",)}
    removed = dcm.remove(local_shared, file_role="query")
    assert len(removed) == 1
    dcm.add(local_shared, removed[0])
    assert local_shared in dcm.get_datafiles()

    checked = []
    monkeypatch.setattr(jm, "_getting_local_file", lambda datafile: str(tmp_path / f"done_{Path(datafile.get_path()).name}"), raising=False)
    monkeypatch.setattr(
        jm,
        "check_file",
        lambda datafile, role, size_limit, should_be_local: checked.append((datafile.get_name(), role, size_limit)) or should_be_local,
        raising=False,
    )
    monkeypatch.setattr(
        jm,
        "_check_url",
        lambda datafile, contexts: checked.append((datafile.get_name(), tuple(sorted(contexts)))),
        raising=False,
    )
    assert jm.move_and_check_local_files(dcm) is True
    assert any(item[0] == "shared_query" for item in checked)
    assert any(item[0] == "remote_target.fa.gz" for item in checked)


def test_job_manager_backup_distribution_and_start_job(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path)
    module = env.module

    backup_path = tmp_path / "backup.tar.gz"
    _build_backup(backup_path)
    plot_job = _make_manager(
        env,
        "backup_plot",
        query=None,
        target=None,
        align=None,
        backup=DataFile("backup", str(backup_path), "local"),
        tool=None,
    )
    monkeypatch.setattr(module.validators, "paf", lambda _path: True, raising=False)
    monkeypatch.setattr(module.validators, "v_idx", lambda _path: True, raising=False)

    tar_members = [
        tarfile.TarInfo("map.paf"),
        tarfile.TarInfo("logs.txt"),
        tarfile.TarInfo("query.idx"),
    ]
    yielded = [member.name for member in module.JobManager.allowed_backup_files(tar_members, {"map.paf", "query.idx"}, {"logs.txt"})]
    assert yielded == ["map.paf", "query.idx"]

    backup_contexts = module.DataFileContextManager([plot_job])
    plot_job.unpack_backups(backup_contexts)
    assert plot_job.backup is None
    assert plot_job.align.get_path().endswith("map.paf")
    assert plot_job.query.get_path().endswith("query.idx")
    assert plot_job.target.get_path().endswith("target.idx")
    assert not backup_path.exists()

    bad_backup = tmp_path / "bad_backup.tar.gz"
    with tarfile.open(bad_backup, "w:gz") as tar:
        bad_file = tmp_path / "invalid.txt"
        bad_file.write_text("bad\n")
        tar.add(bad_file, arcname="invalid.txt")
        bad_file.unlink()
    with pytest.raises(DGeniesBackupUnpackError):
        plot_job._unpack_backup(DataFile("backup", str(bad_backup), "local"), tmp_path / "invalid_unpack")

    shared_query = DataFile("query", str(tmp_path / "shared_query.fa"), "local")
    shared_target = DataFile("target", str(tmp_path / "shared_target.fa"), "local")
    Path(shared_query.get_path()).write_text(">q\nACGT\n")
    Path(shared_target.get_path()).write_text(">t\nACGT\n")
    sub1 = _make_manager(env, "batch_sub1", query=shared_query, target=shared_target, tool="minimap2")
    sub2 = _make_manager(env, "batch_sub2", query=shared_query, target=shared_target, tool="minimap2")
    parent = _make_manager(env, "batch_root", tool=None)
    parent.batch = [sub1, sub2]
    Path(parent.output_dir, ".batch").write_text("batch_sub1\nbatch_sub2\n")

    prepare_calls = []
    monkeypatch.setattr(parent, "prepare_job_in_thread", lambda: prepare_calls.append("prepared"), raising=False)
    monkeypatch.setattr(parent, "check_file", lambda _df, _role, _limit, should_be_local: should_be_local, raising=False)
    parent.start_job()
    assert prepare_calls == ["prepared"]
    assert parent.get_status_standalone() == "waiting"
    assert Path(parent.output_dir, ".jobs").exists()
    assert Path(sub1.output_dir, ".already_checked").exists()
    assert Path(sub2.output_dir, ".already_checked").exists()
    assert sub1.query.get_path().startswith(sub1.output_dir)
    assert sub2.target.get_path().startswith(sub2.output_dir)
    assert sub1.query.get_path() != sub2.query.get_path()
    assert sub1.as_job_entry()["type"] == "new"
    assert module.JobManager.to_job_list([{"type": "align", "id_job": "x"}]) == [("align", {"id_job": "x"})]

    cache = {}
    job_type, params = parent.from_file_to_datafiles(
        "align",
        {"query": sub1.query.get_path(), "target": sub1.target.get_path(), "tool": "minimap2"},
        cache=cache,
    )
    assert job_type == "align"
    assert isinstance(params["query"], DataFile)
    assert params["query"] is cache[sub1.query.get_path()]
    assert ("query", params["query"]) in _make_manager(env, "tmp_job", query=params["query"], target=params["target"], tool="minimap2").get_datafiles()


def test_job_manager_prepare_align_and_run_align_workflow(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path)
    module = env.module
    query = DataFile("query", str(tmp_path / "query.fa"), "local")
    target = DataFile("target", str(tmp_path / "target.fa"), "local")
    Path(query.get_path()).write_text(">query\nACGT\n")
    Path(target.get_path()).write_text(">target\nACGT\n")
    jm = _make_manager(env, "align_flow", query=query, target=target, tool="splitter")

    class DummySplitter:
        def __init__(self, input_f, name_f, output_f, query_index, debug=False):
            self.input_f = input_f
            self.name_f = name_f
            self.output_f = output_f
            self.query_index = query_index
            self.nb_contigs = 8

        def split(self):
            Path(self.output_f).write_text(">query\nACGT\n")
            Path(self.query_index).write_text("Query\nchr1\t4\n")
            return True, ""

    class DummyFilter:
        def __init__(self, fasta, index_file, type_f, min_filtered, split, out_fasta, replace_fa):
            self.type_f = type_f
            self.out_fasta = out_fasta

        def filter(self):
            Path(self.out_fasta).write_text("filtered\n")
            return self.type_f == "target"

    class DummyMerger:
        def __init__(self, paf_in, paf_out, query_index_split, idx_q, debug=False):
            self.paf_out = paf_out
            self.idx_q = idx_q

        def merge(self):
            Path(self.paf_out).write_text("merged\n")
            Path(self.idx_q).write_text("Query\nchr1\t4\n")

    class DummySorter:
        def __init__(self, src, dst):
            self.src = src
            self.dst = dst

        def sort(self):
            Path(self.dst).write_text(Path(self.src).read_text())

    class DummyPaf:
        def __init__(self, **kwargs):
            self.parsed = False

        def sort(self):
            self.parsed = True

    monkeypatch.setattr(module, "Splitter", DummySplitter, raising=False)
    monkeypatch.setattr(module, "Filter", DummyFilter, raising=False)
    monkeypatch.setattr(module, "Merger", DummyMerger, raising=False)
    monkeypatch.setattr(module, "Sorter", DummySorter, raising=False)
    monkeypatch.setattr(module, "Paf", DummyPaf, raising=False)
    monkeypatch.setattr(
        module,
        "index_file",
        lambda _path, name, out_idx, _uncompressed=None: (Path(out_idx).write_text(f"{name}\nchr1\t4\n") or True, 8, ""),
        raising=False,
    )
    monkeypatch.setattr(module.parsers, "mock_parser", lambda src, dst: Path(dst).write_text(Path(src).read_text()), raising=False)
    monkeypatch.setattr(
        jm,
        "_launch_local",
        lambda: Path(jm.paf_raw).write_text("raw mappings\n"),
        raising=False,
    )
    Path(jm.output_dir, ".do-sort").write_text("")
    jm.tool.parser = "mock_parser"
    jm.prepare_job()
    assert jm.get_status_standalone() == "success"
    assert Path(jm.paf).exists()
    assert not Path(jm.target.get_path()).exists()
    assert not Path(jm.query_index_split).exists()

    failing_job = _make_manager(env, "align_fail", query=query, target=target, tool="splitter")
    monkeypatch.setattr(failing_job, "prepare_align_local", lambda: (_ for _ in ()).throw(DGeniesFastaFileInvalid("Query", "bad fasta")), raising=False)
    failing_job.prepare_job()
    assert failing_job.get_status_standalone(with_error=True)[0] == "fail"


def test_job_manager_prepare_dotplot_launch_status_and_delete(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path)
    module = env.module

    target_idx = tmp_path / "target.idx"
    target_idx.write_text("Target\nchr1\t4\n")
    align_paf = tmp_path / "align.paf"
    align_paf.write_text("query\t4\t0\t4\t+\ttarget\t4\t0\t4\t4\t4\t255\n")
    plot_job = _make_manager(
        env,
        "plot_flow",
        query=None,
        target=DataFile("target", str(target_idx), "local"),
        align=DataFile("map", str(align_paf), "local"),
        tool=None,
    )
    Path(plot_job.output_dir, ".target").write_text(str(target_idx))

    class DummySorter:
        def __init__(self, src, dst):
            self.src = src
            self.dst = dst

        def sort(self):
            Path(self.dst).write_text(Path(self.src).read_text())

    send_calls = []
    monkeypatch.setattr(module, "Sorter", DummySorter, raising=False)
    monkeypatch.setattr(plot_job, "send_mail_post_if_allowed", lambda: send_calls.append("sent"), raising=False)
    plot_job.prepare_job()
    assert plot_job.get_status_standalone() == "success"
    assert plot_job.align.get_path() == plot_job.paf
    assert Path(plot_job.idx_q).read_text() == Path(plot_job.idx_t).read_text()
    assert send_calls == ["sent"]
    assert plot_job.is_plot() is True
    assert plot_job.is_ava() is True
    assert plot_job.get_job_type() == "plot"

    failing_plot = _make_manager(
        env,
        "plot_fail",
        query=None,
        target=DataFile("target", str(target_idx), "local"),
        align=DataFile("map", str(align_paf), "local"),
        tool=None,
    )
    monkeypatch.setattr(
        failing_plot,
        "prepare_dotplot_local",
        lambda: (_ for _ in ()).throw(DGeniesMissingParserError("maf")),
        raising=False,
    )
    failing_plot.prepare_job()
    assert failing_plot.get_status_standalone(with_error=True)[0] == "fail"

    timer_calls = []

    class ImmediateTimer:
        def __init__(self, interval, func, kwargs=None):
            self.interval = interval
            self.func = func
            self.kwargs = kwargs or {}
            timer_calls.append((interval, func.__name__))

        def start(self):
            self.func(**self.kwargs)

        def join(self):
            return None

    launch_target = DataFile("target", str(tmp_path / "launch.fa"), "local")
    Path(launch_target.get_path()).write_text(">t\nACGT\n")
    launch_job = _make_manager(env, "launch_job", query=None, target=launch_target, tool="minimap2")
    monkeypatch.setattr(module.threading, "Timer", ImmediateTimer, raising=False)
    monkeypatch.setattr(launch_job, "start_job", lambda: launch_job.set_status_standalone("waiting"), raising=False)
    launch_job.launch_standalone(sync=True)
    assert launch_job.status() == {"status": "waiting", "mem_peak": None, "time_elapsed": None, "error": ""}
    assert timer_calls == [(1, "<lambda>")]

    thread_job = _make_manager(env, "thread_job", query=None, target=launch_target, tool="minimap2")
    monkeypatch.setattr(thread_job, "run_align", lambda runner_type="local": thread_job.set_status_standalone(runner_type), raising=False)
    monkeypatch.setattr(thread_job, "prepare_job", lambda: thread_job.set_status_standalone("prepared"), raising=False)
    thread_job.run_align_in_thread("local")
    assert thread_job.get_status_standalone() == "local"
    thread_job.prepare_job_in_thread()
    assert thread_job.get_status_standalone() == "prepared"

    standalone_unknown = _make_manager(env, "unknown_job", query=None, target=launch_target, tool="minimap2")
    assert standalone_unknown.status() == {"status": "unknown", "error": ""}

    launch_job.set_status_standalone("fail", "bad things")
    assert launch_job.get_status_standalone(with_error=True) == ["fail", "bad things"]
    assert launch_job.status()["error"] == "bad things"
    launch_job.delete()
    assert not Path(launch_job.output_dir).exists()


def test_job_manager_cluster_prepare_helpers(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path, mode="webserver")

    query = DataFile("query", str(tmp_path / "cluster_query.fa"), "local")
    target = DataFile("target", str(tmp_path / "cluster_target.fa"), "local")
    align = DataFile("map", str(tmp_path / "cluster_map.paf"), "local")
    for datafile, content in (
        (query, ">q\nACGT\n"),
        (target, ">t\nACGT\n"),
        (align, "query\t4\t0\t4\t+\ttarget\t4\t0\t4\t4\t4\t255\n"),
    ):
        Path(datafile.get_path()).write_text(content)

    align_job = _make_manager(env, "align_cluster", query=query, target=target, tool="splitter")
    cluster_calls = []
    monkeypatch.setattr(
        align_job,
        "launch_to_cluster",
        lambda **kwargs: cluster_calls.append(kwargs),
        raising=False,
    )
    status_updates = []
    monkeypatch.setattr(
        align_job,
        "update_job_status",
        lambda status, pid=None: status_updates.append((status, pid)),
        raising=False,
    )
    align_job.prepare_align_cluster("slurm")
    assert cluster_calls[0]["step"] == "prepare"
    assert cluster_calls[0]["runner_type"] == "slurm"
    assert "--split" in cluster_calls[0]["args"]
    assert "-u" in cluster_calls[0]["args"]
    assert status_updates == [("prepared", None)]

    plot_job = _make_manager(env, "plot_cluster", query=None, target=target, align=align, tool=None)
    cluster_calls = []
    end_calls = []

    def fake_launch_to_cluster(**kwargs):
        cluster_calls.append(kwargs)
        Path(plot_job.idx_t).write_text("Target\nchr1\t4\n")

    monkeypatch.setattr(plot_job, "launch_to_cluster", fake_launch_to_cluster, raising=False)
    monkeypatch.setattr(plot_job, "_end_of_prepare_dotplot", lambda: end_calls.append("done"), raising=False)
    status_updates = []
    monkeypatch.setattr(
        plot_job,
        "update_job_status",
        lambda status, pid=None: status_updates.append((status, pid)),
        raising=False,
    )
    plot_job.prepare_dotplot_cluster("sge")
    assert cluster_calls[0]["runner_type"] == "sge"
    assert "--index-only" in cluster_calls[0]["args"]
    assert "-t" in cluster_calls[0]["args"]
    assert Path(plot_job.idx_q).read_text() == Path(plot_job.idx_t).read_text()
    assert status_updates == [("prepared", None)]
    assert end_calls == ["done"]


def test_job_manager_webserver_launch_analytics_status_and_delete(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path, mode="webserver")
    import dgenies.database as database_module

    class DummyAnalyticsRecord(SimpleNamespace):
        def save(self):
            return None

    class DummyAnalytics:
        id_job = object()
        _records = {}

        @classmethod
        def create(cls, **kwargs):
            record = DummyAnalyticsRecord(status="unknown", **kwargs)
            cls._records[record.id_job] = record
            return record

        @classmethod
        def get(cls, *_args, **_kwargs):
            return next(iter(cls._records.values()))

    monkeypatch.setattr(database_module, "Analytics", DummyAnalytics, raising=False)

    query = DataFile("query", str(tmp_path / "analytics_query.fa"), "local")
    target = DataFile("target", str(tmp_path / "analytics_target.fa"), "local")
    Path(query.get_path()).write_text(">q\nACGT\n")
    Path(target.get_path()).write_text(">t\nACGT\n")
    jm = _make_manager(env, "web_job", query=query, target=target, tool="minimap2")
    jm.config.analytics_enabled = True
    env.DummyJob.create(
        id_job=jm.id_job,
        email="user@example.org",
        runner_type="slurm",
        date_created=datetime.now(),
        tool=jm.tool_name,
        options=jm.options,
    )
    jm._save_analytics_data()
    analytics_record = DummyAnalytics.get()
    assert analytics_record.target_size == os.path.getsize(target.get_path())
    assert analytics_record.query_size == os.path.getsize(query.get_path())
    assert analytics_record.mail_client == "user@example.org"
    assert analytics_record.runner_type == "slurm"
    assert analytics_record.job_type == "new"

    jm._set_analytics_job_status("success")
    assert analytics_record.status == "success"
    analytics_record.status = "no-match"
    jm._set_analytics_job_status("fail")
    assert analytics_record.status == "no-match"

    timer_calls = []

    class ImmediateTimer:
        def __init__(self, interval, func, kwargs=None):
            self.interval = interval
            self.func = func
            self.kwargs = kwargs or {}

        def start(self):
            timer_calls.append((self.interval, self.func.__name__))
            self.func(**self.kwargs)

    monkeypatch.setattr(env.module.threading, "Timer", ImmediateTimer, raising=False)
    monkeypatch.setattr(jm, "start_job", lambda: None, raising=False)
    jm.launch()
    db_job = env.DummyJob.get()
    assert db_job.id_job == "web_job"
    assert timer_calls == [(1, "<lambda>")]

    db_job.mem_peak = 4096
    db_job.time_elapsed = 123
    db_job.error = "warning"
    assert jm.status() == {"status": "submitted", "mem_peak": 4096, "time_elapsed": 123, "error": "warning"}

    missing_inputs = _make_manager(env, "invalid_web", query=None, target=None, tool="minimap2")
    missing_inputs.launch()
    invalid_record = env.DummyJob.get(id_job="invalid_web")
    assert invalid_record.status == "fail"

    unknown_job = _make_manager(env, "unknown_web", query=None, target=target, tool="minimap2")
    monkeypatch.setattr(env.DummyJob, "get", classmethod(lambda cls, *_args, **_kwargs: (_ for _ in ()).throw(KeyError("missing"))), raising=False)
    assert unknown_job.status() == {"status": "unknown", "error": ""}
    monkeypatch.setattr(env.DummyJob, "get", classmethod(lambda cls, *_args, **_kwargs: cls._records["web_job"]), raising=False)

    jm.delete()
    assert "web_job" not in env.DummyJob._records
    assert not Path(jm.output_dir).exists()


def test_job_manager_prepare_job_webserver_error_paths(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path, mode="webserver")

    align_job = _make_manager(
        env,
        "prepare_align_web",
        query=DataFile("query", str(tmp_path / "prepare_query.fa"), "local"),
        target=DataFile("target", str(tmp_path / "prepare_target.fa"), "local"),
        tool="minimap2",
    )
    env.DummyJob.create(
        id_job=align_job.id_job,
        email="user@example.org",
        runner_type="slurm",
        date_created=datetime.now(),
        tool=align_job.tool_name,
        options=align_job.options,
    )
    align_statuses = []
    align_analytics = []
    align_mail = []
    monkeypatch.setattr(
        align_job,
        "prepare_align_cluster",
        lambda runner_type: (_ for _ in ()).throw(DGeniesClusterRunError(f"{runner_type} failed")),
        raising=False,
    )
    monkeypatch.setattr(
        align_job,
        "set_job_status",
        lambda status, error="": align_statuses.append((status, error)),
        raising=False,
    )
    monkeypatch.setattr(
        align_job,
        "_set_analytics_job_status",
        lambda status: align_analytics.append(status),
        raising=False,
    )
    monkeypatch.setattr(
        align_job,
        "send_mail_post_if_allowed",
        lambda: align_mail.append("sent"),
        raising=False,
    )
    align_job.prepare_job()
    assert align_statuses == [("fail", "slurm failed<br/>Please check your input file and try again.")]
    assert align_analytics == ["fail-prepare"]
    assert align_mail == ["sent"]

    plot_job = _make_manager(
        env,
        "prepare_plot_web",
        query=None,
        target=DataFile("target", str(tmp_path / "plot_target.fa"), "local"),
        align=DataFile("map", str(tmp_path / "plot_align.paf"), "local"),
        tool=None,
    )
    env.DummyJob.create(
        id_job=plot_job.id_job,
        email="user@example.org",
        runner_type="local",
        date_created=datetime.now(),
        tool=plot_job.tool_name,
        options=plot_job.options,
    )
    plot_statuses = []
    plot_analytics = []
    plot_mail = []
    monkeypatch.setattr(
        plot_job,
        "prepare_dotplot_local",
        lambda: (_ for _ in ()).throw(DGeniesMissingParserError("sam")),
        raising=False,
    )
    monkeypatch.setattr(
        plot_job,
        "set_job_status",
        lambda status, error="": plot_statuses.append((status, error)),
        raising=False,
    )
    monkeypatch.setattr(
        plot_job,
        "_set_analytics_job_status",
        lambda status: plot_analytics.append(status),
        raising=False,
    )
    monkeypatch.setattr(
        plot_job,
        "send_mail_post_if_allowed",
        lambda: plot_mail.append("sent"),
        raising=False,
    )
    plot_job.prepare_job()
    assert plot_statuses == [("fail", "No parser found for format sam. Please contact the support.")]
    assert plot_analytics == ["fail-all"]
    assert plot_mail == ["sent"]


def test_job_manager_run_align_webserver_error_paths(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path, mode="webserver")
    jm = _make_manager(
        env,
        "run_align_web",
        query=DataFile("query", str(tmp_path / "run_query.fa"), "local"),
        target=DataFile("target", str(tmp_path / "run_target.fa"), "local"),
        tool="minimap2",
    )
    Path(jm.logs).write_text("base log\n")
    env.DummyJob.create(
        id_job=jm.id_job,
        email="user@example.org",
        runner_type="local",
        date_created=datetime.now(),
        tool=jm.tool_name,
        options=jm.options,
    )

    analytics = []
    mailed = []
    monkeypatch.setattr(jm, "_set_analytics_job_status", lambda status: analytics.append(status), raising=False)
    monkeypatch.setattr(jm, "send_mail_post_if_allowed", lambda: mailed.append("sent"), raising=False)
    monkeypatch.setattr(jm, "_launch_local", lambda: (_ for _ in ()).throw(DGeniesRunError("mapping failed")), raising=False)
    jm.run_align("local")
    db_job = env.DummyJob.get()
    assert db_job.status == "fail"
    assert db_job.error == "mapping failed"
    assert analytics == ["fail-map"]
    assert mailed == ["sent"]

    set_status_calls = []
    monkeypatch.setattr(
        jm,
        "set_job_status",
        lambda status, error="": set_status_calls.append((status, error)),
        raising=False,
    )
    analytics.clear()
    monkeypatch.setattr(jm, "_launch_local", lambda: (_ for _ in ()).throw(ValueError("unexpected boom")), raising=False)
    jm.run_align("local")
    assert set_status_calls == [("fail", "Your job has failed for an unexpected reason. Please contact the support if the problem persists.")]
    assert analytics == ["fail-map-after"]
    assert "unexpected boom" in Path(jm.logs).read_text()


def test_job_manager_additional_batch_mail_and_status_helpers(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path)
    module = env.module

    query = DataFile("query", str(tmp_path / "batch_query.fa"), "local")
    target = DataFile("target", str(tmp_path / "batch_target.fa"), "local")
    Path(query.get_path()).write_text(">q\nACGT\n")
    Path(target.get_path()).write_text(">t\nACGT\n")

    Path(tmp_path / "batch_parent").mkdir()
    generated = iter(["abcde", "fghij"])
    monkeypatch.setattr(module.Functions, "random_string", staticmethod(lambda _length: next(generated)), raising=False)
    batch_job = module.JobManager.create(
        "batch_parent",
        "batch",
        [
            {"type": "align", "id_job": "sub_one", "query": query, "target": target, "tool": "minimap2"},
            {"type": "align", "id_job": "sub_two", "query": query, "target": target, "tool": "minimap2"},
        ],
        email="user@example.org",
    )
    assert (Path(batch_job.output_dir) / ".batch").read_text().splitlines() == ["sub_one_abcde", "sub_two_fghij"]

    batch_job.error = ""
    batch_text = batch_job.get_batch_mail_part("fail")
    assert "Your batch job batch_parent has failed!" in batch_text
    assert "You can try again." in batch_text
    assert "sub_one_abcde" in batch_text

    target_only = batch_job.get_job_mail_part("fail", "TargetOnly")
    assert "Target: TargetOnly" in target_only
    assert "Query:" not in target_only

    batch_job.config.disable_anonymous_analytics = True
    batch_job.config.anonymous_analytics = "groups"
    batch_job.config.analytics_groups = [("staff", r".*@example\.org")]
    assert batch_job._anonymize_mail_client("nobody@elsewhere.test") == ""

    batch_job.options = ["-x asm5"]
    entry = batch_job.as_job_entry()
    assert entry["type"] == "batch"
    assert entry["options"] == ["-x asm5"]

    ctx = module.DataFileContext(batch_job, "new", "target", 1024)
    assert "file_role:target" in repr(ctx)
    assert str(ctx) == repr(ctx)

    manager = module.DataFileContextManager([_make_manager(env, "ctx_repr", query=query, target=target, tool="minimap2")])
    assert "batch_query.fa" in repr(manager) or "batch_target.fa" in repr(manager)
    assert str(manager) == repr(manager)

    env_web = _setup_job_manager_env(monkeypatch, tmp_path / "mail_web", mode="webserver")
    mail_job = _make_manager(env_web, "mail_post", query=query, target=target, tool="minimap2")
    env_web.DummyJob.create(
        id_job=mail_job.id_job,
        email="user@example.org",
        status="success",
        error="",
        runner_type="local",
        date_created=datetime.now(),
        tool=mail_job.tool_name,
        options=mail_job.options,
    )
    mail_errors = []
    monkeypatch.setattr(mail_job.logger, "error", lambda message: mail_errors.append(str(message)), raising=False)

    class Non200Response:
        def getcode(self):
            return 500

    monkeypatch.setattr(env_web.module.Functions, "random_string", staticmethod(lambda _length: "K" * 15), raising=False)
    monkeypatch.setattr(env_web.module.request, "urlopen", lambda _req: Non200Response(), raising=False)
    mail_job.send_mail_post_if_allowed()
    assert any("Send mail failed" in message for message in mail_errors)

    monkeypatch.setattr(
        env_web.module.subprocess,
        "check_output",
        lambda *_args, **_kwargs: b"last but harmless\nstill harmless\n",
        raising=False,
    )
    assert "You can try again" in mail_job.search_error()


def test_job_manager_additional_local_cluster_and_update_helpers(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path)
    module = env.module

    query = DataFile("query", str(tmp_path / "local_query.fa"), "local")
    target = DataFile("target", str(tmp_path / "local_target.fa"), "local")
    Path(query.get_path()).write_text(">q\nACGT\n")
    Path(target.get_path()).write_text(">t\nACGT\n")
    jm = _make_manager(env, "local_status", query=query, target=target, tool="minimap2")
    jm.tool.command_line = "{exe} --target {target} --query {query} --threads {threads} {options}"

    popen = SimpleNamespace(pid=42, returncode=0, wait=lambda: None)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args, **_kwargs: popen, raising=False)
    monkeypatch.setattr(jm, "check_job_success", lambda: "no-match", raising=False)
    analytics = []
    monkeypatch.setattr(jm, "_set_analytics_job_status", lambda status: analytics.append(status), raising=False)
    jm._launch_local()
    assert jm.get_status_standalone() == "no-match"
    assert analytics == ["no-match"]

    jm.id_process = "sge-1"
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda *_args, **_kwargs: (
            "failed       0\n"
            "start_time   Mon Jan 01 00:00:00 2024\n"
            "end_time     Mon Jan 01 00:10:00 2024\n"
            "maxvmem      2048\n"
        ).encode(),
        raising=False,
    )
    assert jm.check_job_status_sge() is True
    assert "600 2048" in Path(jm.logs).read_text()

    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda *_args, **_kwargs: (
            "failed       0\n"
            "start_time   Mon Jan 01 00:00:00 2024\n"
            "end_time     Mon Jan 01 00:10:00 2024\n"
            "maxvmem      2G\n"
        ).encode(),
        raising=False,
    )
    assert jm.check_job_status_sge() is True
    assert "2097152" in Path(jm.logs).read_text()

    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda *_args, **_kwargs: (
            "failed       0\n"
            "start_time   Mon Jan 01 00:00:00 2024\n"
            "end_time     Mon Jan 01 00:10:00 2024\n"
            "maxvmem      2M\n"
        ).encode(),
        raising=False,
    )
    assert jm.check_job_status_sge() is True
    assert "2048" in Path(jm.logs).read_text()

    env_web = _setup_job_manager_env(monkeypatch, tmp_path / "status_web", mode="webserver")
    web_query = DataFile("query", str(tmp_path / "status_web_query.fa"), "local")
    web_target = DataFile("target", str(tmp_path / "status_web_target.fa"), "local")
    Path(web_query.get_path()).write_text(">q\nACGT\n")
    Path(web_target.get_path()).write_text(">t\nACGT\n")
    web_job = _make_manager(env_web, "web_status", query=web_query, target=web_target, tool="minimap2")
    env_web.DummyJob.create(
        id_job=web_job.id_job,
        email="user@example.org",
        status="submitted",
        error="",
        runner_type="sge",
        date_created=datetime.now(),
        tool=web_job.tool_name,
        options=web_job.options,
    )
    web_job.set_job_status("prepared", "none")
    assert env_web.DummyJob.get().status == "prepared"
    assert env_web.DummyJob.get().error == "none"
    web_job.update_job_status("scheduled", "123")
    assert env_web.DummyJob.get().status == "scheduled"
    assert env_web.DummyJob.get().id_process == "123"

    monkeypatch.setattr(module, "MODE", "standalone", raising=False)
    jm.update_job_status("scheduled-local")
    assert jm.get_status_standalone() == "scheduled-local"

    Path(web_job.logs).write_text("cluster err\n")
    cluster_stdout = Path(web_job.logs + ".out")
    cluster_stderr = Path(web_job.logs + ".err")
    cluster_stdout.write_text("stdout\n")
    cluster_stderr.write_text("stderr\n")
    template_state = {}

    class FakeSession:
        def __init__(self, has_exited=True):
            self.has_exited = has_exited

        def createJobTemplate(self):
            template_state["template"] = SimpleNamespace()
            return template_state["template"]

        def runJob(self, job_template):
            template_state["submitted"] = job_template
            return "999"

        def wait(self, _jobid, _timeout):
            return SimpleNamespace(hasExited=self.has_exited)

        def deleteJobTemplate(self, _template):
            template_state["deleted"] = True

    monkeypatch.setitem(sys.modules, "drmaa", SimpleNamespace(Session=SimpleNamespace(TIMEOUT_WAIT_FOREVER=-1)))
    monkeypatch.setitem(
        sys.modules,
        "dgenies.lib.drmaasession",
        SimpleNamespace(DrmaaSession=lambda: SimpleNamespace(session=FakeSession(True))),
    )
    monkeypatch.setattr(web_job, "check_job_status_sge", lambda: True, raising=False)
    cluster_updates = []
    monkeypatch.setattr(web_job, "update_job_status", lambda status, pid=None: cluster_updates.append((status, pid)), raising=False)
    web_job.launch_to_cluster(
        step="prepare",
        runner_type="sge",
        command="/usr/bin/python3",
        args=["prepare.py"],
        log_out=str(cluster_stdout),
        log_err=str(cluster_stderr),
        scheduled_status="prepare-scheduled",
    )
    assert cluster_updates == [("prepare-scheduled", "999")]
    assert template_state["submitted"].joinFiles is False
    assert template_state["submitted"].errorPath == ":" + str(cluster_stderr)
    assert template_state["submitted"].nativeSpecification == "-l mem=8000,h_vmem=8000 -pe parallel_smp 1"
    assert "stderr" in Path(web_job.logs).read_text()

    monkeypatch.setitem(
        sys.modules,
        "dgenies.lib.drmaasession",
        SimpleNamespace(DrmaaSession=lambda: SimpleNamespace(session=FakeSession(False))),
    )
    monkeypatch.setattr(web_job, "find_error_in_log", lambda _path: "cluster failed", raising=False)
    with pytest.raises(DGeniesClusterRunError, match="cluster failed"):
        web_job.launch_to_cluster(
            step="prepare",
            runner_type="sge",
            command="/usr/bin/python3",
            args=["prepare.py"],
            log_out=str(cluster_stdout),
            log_err=str(cluster_stderr),
            scheduled_status="prepare-scheduled",
        )

    analytics = []
    final_updates = []
    monkeypatch.setattr(web_job, "launch_to_cluster", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(web_job, "check_job_success", lambda: "no-match", raising=False)
    monkeypatch.setattr(web_job, "update_job_status", lambda status, pid=None: final_updates.append((status, pid)), raising=False)
    monkeypatch.setattr(web_job, "_set_analytics_job_status", lambda status: analytics.append(status), raising=False)
    web_job._launch_drmaa("slurm")
    assert analytics == ["no-match"]
    assert final_updates[-1] == ("no-match", None)

    monkeypatch.setattr(web_job, "launch_to_cluster", lambda **_kwargs: (_ for _ in ()).throw(DGeniesClusterRunError("boom")), raising=False)
    with pytest.raises(DGeniesClusterRunError, match="boom"):
        web_job._launch_drmaa("slurm")


def test_job_manager_additional_file_transfer_start_launch_and_delete_branches(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path, mode="webserver")
    module = env.module

    missing_query = DataFile("query", str(tmp_path / "missing_query.fa"), "local")
    normalize_job = _make_manager(env, "normalize_missing", query=missing_query, target=None, tool="minimap2")
    with pytest.raises(Exception, match="does not exists"):
        normalize_job.normalize_files()

    assert module.JobManager.get_pending_local_number() == 0
    env.DummyJob.create(
        id_job="pending_local",
        email="user@example.org",
        status="submitted",
        error="",
        runner_type="local",
        date_created=datetime.now(),
        tool="minimap2",
        options=None,
    )
    assert module.JobManager.get_pending_local_number() == 1
    monkeypatch.setattr(module, "MODE", "standalone", raising=False)
    assert module.JobManager.get_pending_local_number() == 0
    monkeypatch.setattr(module, "MODE", "webserver", raising=False)

    download_job = _make_manager(
        env,
        "download_dir_job",
        query=None,
        target=DataFile.create("remote.fa.gz", "https://example.org/remote.fa.gz"),
        tool="minimap2",
    )
    with pytest.raises(DGeniesURLInvalid):
        download_job._get_filename_from_url("custom://remote.fa.gz")

    monkeypatch.setattr(download_job, "_get_filename_from_url", lambda _url: "remote.fa.gz", raising=False)

    class FakeGetResponse:
        def iter_content(self, chunk_size=1024):
            assert chunk_size == 1024
            yield b"AA"
            yield b"TT"

    monkeypatch.setattr(module.requests, "get", lambda *_args, **_kwargs: FakeGetResponse(), raising=False)
    distant_name, local_path = download_job._download_file("https://example.org/remote.fa.gz")
    assert distant_name == "remote.fa.gz"
    assert Path(local_path).read_bytes() == b"AATT"

    clear_job = _make_manager(env, "clear_me", query=None, target=None, tool="minimap2")
    clear_job.clear()
    assert not Path(clear_job.output_dir).exists()

    loop_job = _make_manager(
        env,
        "pending_job",
        query=None,
        target=DataFile.create("target.fa.gz", "https://example.org/target.fa.gz"),
        tool="minimap2",
    )
    env.DummyJob.create(
        id_job=loop_job.id_job,
        email="user@example.org",
        status="submitted",
        error="",
        runner_type="slurm",
        date_created=datetime.now(),
        tool=loop_job.tool_name,
        options=loop_job.options,
    )

    class WaitingSession:
        def __init__(self):
            self.deleted = 0
            self.calls = []

        def ask_for_upload(self, change_status=False):
            self.calls.append(change_status)
            return len(self.calls) > 1

        def delete_instance(self):
            self.deleted += 1

    waiting_session = WaitingSession()
    monkeypatch.setattr(module, "Session", SimpleNamespace(new=lambda *_args, **_kwargs: "session", get=lambda **_kwargs: waiting_session), raising=False)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None, raising=False)
    downloaded_target = tmp_path / "downloaded_target.fa"
    downloaded_target.write_text(">t\nACGT\n")
    monkeypatch.setattr(loop_job, "_getting_file_from_url", lambda _datafile: (str(downloaded_target), "target"), raising=False)
    checked = []
    monkeypatch.setattr(
        loop_job,
        "check_file",
        lambda datafile, role, size_limit, should_be_local: checked.append((datafile.get_type(), role, size_limit)) or False,
        raising=False,
    )
    dcm = module.DataFileContextManager([loop_job])
    assert loop_job.download_files_with_pending(dcm, True) is False
    assert waiting_session.calls == [True, False]
    assert waiting_session.deleted == 1
    assert loop_job.target.get_type() == "local"
    assert checked[0][0] == "local"

    failing_session = WaitingSession()
    monkeypatch.setattr(module, "Session", SimpleNamespace(new=lambda *_args, **_kwargs: "session", get=lambda **_kwargs: failing_session), raising=False)
    error_job = _make_manager(
        env,
        "pending_error",
        query=None,
        target=DataFile.create("bad.fa.gz", "https://example.org/bad.fa.gz"),
        tool="minimap2",
    )
    env.DummyJob.create(
        id_job=error_job.id_job,
        email="user@example.org",
        status="submitted",
        error="",
        runner_type="slurm",
        date_created=datetime.now(),
        tool=error_job.tool_name,
        options=error_job.options,
    )
    monkeypatch.setattr(error_job, "_getting_file_from_url", lambda _datafile: (_ for _ in ()).throw(RuntimeError("boom")), raising=False)
    with pytest.raises(DGeniesDownloadError):
        error_job.download_files_with_pending(module.DataFileContextManager([error_job]), True)
    assert failing_session.deleted == 1

    target_file = tmp_path / "start_target.fa"
    target_file.write_text(">t\nACGT\n")
    start_job = _make_manager(env, "start_switch", query=None, target=DataFile("target", str(target_file), "local"), tool="minimap2")
    Path(start_job.output_dir, ".already_checked").write_text("")
    env.DummyJob.create(
        id_job=start_job.id_job,
        email="user@example.org",
        status="submitted",
        error="",
        runner_type="slurm",
        date_created=datetime.now(),
        tool=start_job.tool_name,
        options=start_job.options,
    )
    analytics = []
    monkeypatch.setattr(start_job, "_save_analytics_data", lambda: analytics.append("saved"), raising=False)
    monkeypatch.setattr(start_job, "get_pending_local_number", lambda: 0, raising=False)
    start_job.start_job()
    db_job = env.DummyJob.get(id_job=start_job.id_job)
    assert db_job.runner_type == "local"
    assert db_job.status == "waiting"
    assert analytics == ["saved"]

    failing_start = _make_manager(env, "start_fail", query=DataFile("query", str(tmp_path / "start_fail_query.fa"), "local"), target=DataFile("target", str(target_file), "local"), tool="minimap2")
    Path(failing_start.query.get_path()).write_text(">q\nACGT\n")
    env.DummyJob.create(
        id_job=failing_start.id_job,
        email="user@example.org",
        status="submitted",
        error="",
        runner_type="local",
        date_created=datetime.now(),
        tool=failing_start.tool_name,
        options=failing_start.options,
    )
    mail_calls = []
    monkeypatch.setattr(failing_start, "move_and_check_local_files", lambda _dcm: (_ for _ in ()).throw(RuntimeError("boom")), raising=False)
    monkeypatch.setattr(failing_start, "_save_analytics_data", lambda: None, raising=False)
    monkeypatch.setattr(failing_start, "_set_analytics_job_status", lambda status: analytics.append(status), raising=False)
    monkeypatch.setattr(failing_start, "send_mail_if_allowed", lambda: mail_calls.append("sent"), raising=False)
    failing_start.start_job()
    assert mail_calls == ["sent"]
    assert env.DummyJob.get(id_job=failing_start.id_job).status == "fail"

    timer_calls = []

    class ImmediateTimer:
        def __init__(self, interval, func, kwargs=None):
            self.interval = interval
            self.func = func
            self.kwargs = kwargs or {}
            timer_calls.append((interval, func.__name__))

        def start(self):
            return None

        def join(self):
            return None

    monkeypatch.setattr(module.threading, "Timer", ImmediateTimer, raising=False)
    monkeypatch.setattr(module, "MODE", "standalone", raising=False)
    standalone_launch = module.JobManager(id_job="launch_missing_dir", query=DataFile("query", str(tmp_path / "launch_query.fa"), "local"), target=DataFile("target", str(target_file), "local"), tool="minimap2")
    standalone_launch.launch_standalone(sync=True)
    assert Path(standalone_launch.output_dir).exists()

    monkeypatch.setattr(module, "MODE", "webserver", raising=False)
    web_launch = module.JobManager(id_job="launch_web_dir", query=None, target=DataFile("target", str(target_file), "local"), tool="minimap2")
    web_launch.launch()
    assert Path(web_launch.output_dir).exists()

    missing_job = module.JobManager(id_job="missing_delete")
    with pytest.raises(DGeniesMissingJobError):
        missing_job.delete()

    gallery_job = _make_manager(env, "gallery_delete", query=None, target=DataFile("target", str(target_file), "local"), tool="minimap2")
    env.DummyJob.create(
        id_job=gallery_job.id_job,
        email="user@example.org",
        status="submitted",
        error="",
        runner_type="local",
        date_created=datetime.now(),
        tool=gallery_job.tool_name,
        options=gallery_job.options,
    )

    class GalleryQuery(list):
        def where(self, *_args, **_kwargs):
            return [1]

    monkeypatch.setattr(module.Gallery, "job", type("GalleryExpr", (), {"__eq__": lambda self, other: other})(), raising=False)
    monkeypatch.setattr(module.Gallery, "select", classmethod(lambda cls: GalleryQuery()), raising=False)
    with pytest.raises(DGeniesDeleteGalleryJobForbidden):
        gallery_job.delete()

    monkeypatch.setattr(module.Gallery, "select", classmethod(lambda cls: type("EmptyGalleryQuery", (), {"where": lambda self, *_args, **_kwargs: []})()), raising=False)
    gallery_job.delete()
    assert gallery_job.id_job not in env.DummyJob._records


def test_job_manager_prepare_align_local_gzip_filtering_and_failures(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path)
    module = env.module

    filter_decisions = {"query": False, "target": True}

    class TrackingFilter:
        def __init__(self, fasta, index_file, type_f, min_filtered, split, out_fasta, replace_fa):
            self.type_f = type_f
            self.out_fasta = out_fasta

        def filter(self):
            Path(self.out_fasta).write_text("filtered\n")
            return filter_decisions[self.type_f]

    def index_success(path, name, out_idx, uncompressed=None):
        Path(out_idx).write_text(f"{name}\nchr1\t4\n")
        if uncompressed is not None:
            Path(uncompressed).write_text(">chr1\nACGT\n")
        return True, 8, ""

    monkeypatch.setattr(module, "Filter", TrackingFilter, raising=False)
    monkeypatch.setattr(module, "index_file", index_success, raising=False)

    def make_job(job_id, query_name, target_name):
        query = DataFile("query", str(tmp_path / query_name), "local")
        target = DataFile("target", str(tmp_path / target_name), "local")
        Path(query.get_path()).write_text("query.gz")
        Path(target.get_path()).write_text("target.gz")
        return _make_manager(env, job_id, query=query, target=target, tool="minimap2")

    success_job = make_job("align_gzip", "query.fa.gz", "target.fa.gz")
    run_calls = []
    monkeypatch.setattr(success_job, "run_align", lambda runner_type="local": run_calls.append(runner_type), raising=False)
    success_job.prepare_align_local()
    assert run_calls == ["local"]
    assert success_job.target.get_path().endswith("target.fa")
    assert Path(success_job.output_dir, ".target").read_text() == str(tmp_path / "target.fa")
    assert not Path(tmp_path / "target.fa.gz").exists()
    success_job.tool.max_memory = 12
    assert success_job._get_runner_config("start")[0] == 12

    filter_decisions["target"] = False
    unfiltered_job = make_job("align_gzip_unfiltered", "query_keep.fa.gz", "target_keep.fa.gz")
    monkeypatch.setattr(unfiltered_job, "run_align", lambda runner_type="local": None, raising=False)
    unfiltered_job.prepare_align_local()
    assert not Path(tmp_path / "target_keep.fa").exists()

    invalid_query_job = make_job("align_invalid_query", "invalid_query.fa.gz", "unused_target.fa.gz")

    def index_invalid_query(path, name, out_idx, uncompressed=None):
        assert "invalid_query.fa.gz" in path
        return False, 0, "bad query"

    monkeypatch.setattr(module, "index_file", index_invalid_query, raising=False)
    with pytest.raises(DGeniesFastaFileInvalid, match="Query"):
        invalid_query_job.prepare_align_local()

    invalid_target_job = make_job("align_invalid_target", "valid_query.fa.gz", "invalid_target.fa.gz")

    def index_invalid_target(path, name, out_idx, uncompressed=None):
        if "valid_query.fa.gz" in path:
            Path(out_idx).write_text(f"{name}\nchr1\t4\n")
            if uncompressed is not None:
                Path(uncompressed).write_text(">chr1\nACGT\n")
            return True, 8, ""
        return False, 0, "bad target"

    monkeypatch.setattr(module, "index_file", index_invalid_target, raising=False)
    with pytest.raises(DGeniesFastaFileInvalid, match="Target"):
        invalid_target_job.prepare_align_local()


def test_job_manager_batch_prepare_and_prepare_job_web_paths(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path, mode="webserver")
    module = env.module

    assert module.Tools().get_default() == "minimap2"
    assert module.AllowedExtensions().get_extensions("fasta")[0] == "fa"
    session_id = env.DummySession.new(keep_active=True)
    session = env.DummySession.get(s_id=session_id)
    assert session.keep_active is True
    assert session.ask_for_upload(True) is True
    assert session.status == "active"
    session.delete_instance()
    env.DummyJob.reset()
    solo_job = env.DummyJob.create(id_job="solo", email="user@example.org")
    env.DummyJob._current = None
    assert env.DummyJob.get().id_job == "solo"
    assert env.DummyJob.select().order_by(None)[0] is solo_job
    env.DummyJob.reset()
    with pytest.raises(KeyError):
        env.DummyJob.get()
    assert env.module.Gallery.select() == []

    query = DataFile("query", str(tmp_path / "batch_query.fa"), "local")
    target = DataFile("target", str(tmp_path / "batch_target.fa"), "local")
    Path(query.get_path()).write_text(">q\nACGT\n")
    Path(target.get_path()).write_text(">t\nACGT\n")
    Path(tmp_path / "batch_web").mkdir()

    batch_job = module.JobManager.create(
        "batch_web",
        "batch",
        [
            {"type": "align", "id_job": "sub_a", "query": query, "target": target, "tool": "minimap2"},
            {"type": "align", "id_job": "sub_b", "query": query, "target": target, "tool": "minimap2"},
        ],
        email="user@example.org",
    )
    for subjob in batch_job.batch:
        Path(subjob.output_dir, ".query").write_text(subjob.query.get_path())
        Path(subjob.output_dir, ".target").write_text(subjob.target.get_path())
    batch_job.write_jobs(batch_job.batch)
    env.DummyJob.create(
        id_job=batch_job.id_job,
        email="user@example.org",
        runner_type="local",
        date_created=datetime.now(),
        tool=None,
        options=None,
    )
    launch_calls = []
    monkeypatch.setattr(module.JobManager, "launch", lambda self: launch_calls.append(self.id_job), raising=False)
    batch_job.error = "Failure on #ID#<br/>Please retry"
    assert "Failure on batch_web" in batch_job.get_batch_mail_part("fail")
    batch_job.prepare_job()
    assert launch_calls == [subjob.id_job for subjob in batch_job.batch]
    assert env.DummyJob.get(id_job=batch_job.id_job).status == "started-batch"
    assert all((Path(subjob.output_dir) / ".no_mail").exists() for subjob in batch_job.batch)

    Path(tmp_path / "batch_web_fail").mkdir()
    failing_batch = _make_manager(env, "batch_web_fail", batch=[], tool=None)
    env.DummyJob.create(
        id_job=failing_batch.id_job,
        email="user@example.org",
        runner_type="local",
        date_created=datetime.now(),
        tool=None,
        options=None,
    )
    analytics = []
    mails = []
    monkeypatch.setattr(
        failing_batch,
        "prepare_batch",
        lambda: (_ for _ in ()).throw(DgeniesMissingSubjobsError()),
        raising=False,
    )
    monkeypatch.setattr(failing_batch, "_set_analytics_job_status", lambda status: analytics.append(status), raising=False)
    monkeypatch.setattr(failing_batch, "send_mail_post_if_allowed", lambda: mails.append("sent"), raising=False)
    failing_batch.prepare_job()
    assert env.DummyJob.get(id_job=failing_batch.id_job).status == "fail"
    assert analytics == ["fail-batch-prepare"]
    assert mails == ["sent"]

    align_job = _make_manager(
        env,
        "prepare_align_local_web",
        query=DataFile("query", str(tmp_path / "prepare_query.fa"), "local"),
        target=DataFile("target", str(tmp_path / "prepare_target.fa"), "local"),
        tool="minimap2",
    )
    env.DummyJob.create(
        id_job=align_job.id_job,
        email="user@example.org",
        runner_type="local",
        date_created=datetime.now(),
        tool=align_job.tool_name,
        options=align_job.options,
    )
    align_calls = []
    monkeypatch.setattr(align_job, "prepare_align_local", lambda: align_calls.append("local"), raising=False)
    align_job.prepare_job()
    assert align_calls == ["local"]

    plot_target = DataFile("target", str(tmp_path / "plot_target.fa"), "local")
    plot_align = DataFile("map", str(tmp_path / "plot_map.paf"), "local")
    Path(plot_target.get_path()).write_text(">t\nACGT\n")
    Path(plot_align.get_path()).write_text("map\n")

    plot_job = _make_manager(env, "prepare_plot_cluster_web", query=None, target=plot_target, align=plot_align, tool=None)
    env.DummyJob.create(
        id_job=plot_job.id_job,
        email="user@example.org",
        runner_type="sge",
        date_created=datetime.now(),
        tool=plot_job.tool_name,
        options=plot_job.options,
    )
    cluster_calls = []
    analytics = []
    monkeypatch.setattr(plot_job, "prepare_dotplot_cluster", lambda runner_type: cluster_calls.append(runner_type), raising=False)
    monkeypatch.setattr(plot_job, "_set_analytics_job_status", lambda status: analytics.append(status), raising=False)
    plot_job.prepare_job()
    assert cluster_calls == ["sge"]
    assert analytics == ["success"]

    failing_plot = _make_manager(env, "prepare_plot_cluster_fail", query=None, target=plot_target, align=plot_align, tool=None)
    env.DummyJob.create(
        id_job=failing_plot.id_job,
        email="user@example.org",
        runner_type="slurm",
        date_created=datetime.now(),
        tool=failing_plot.tool_name,
        options=failing_plot.options,
    )
    statuses = []
    analytics = []
    mails = []
    monkeypatch.setattr(
        failing_plot,
        "prepare_dotplot_cluster",
        lambda runner_type: (_ for _ in ()).throw(DGeniesClusterRunError("cluster broke")),
        raising=False,
    )
    monkeypatch.setattr(failing_plot, "set_job_status", lambda status, error="": statuses.append((status, error)), raising=False)
    monkeypatch.setattr(failing_plot, "_set_analytics_job_status", lambda status: analytics.append(status), raising=False)
    monkeypatch.setattr(failing_plot, "send_mail_post_if_allowed", lambda: mails.append("sent"), raising=False)
    failing_plot.prepare_job()
    assert statuses == [("fail", "cluster broke<br/>Please check your input file and try again.")]
    assert analytics == ["fail-all"]
    assert mails == ["sent"]


def test_job_manager_prepare_dotplot_cluster_local_and_parser_paths(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path, mode="webserver")
    module = env.module

    query = DataFile("query", str(tmp_path / "cluster_query.fa"), "local")
    target = DataFile("target", str(tmp_path / "cluster_target.fa"), "local")
    align = DataFile("map", str(tmp_path / "cluster_align.maf"), "local")
    Path(query.get_path()).write_text(">q\nACGT\n")
    Path(target.get_path()).write_text(">t\nACGT\n")
    Path(align.get_path()).write_text("maf\n")

    align_job = _make_manager(env, "prepare_align_cluster_fail", query=query, target=target, tool="splitter")
    monkeypatch.setattr(
        align_job,
        "launch_to_cluster",
        lambda **_kwargs: (_ for _ in ()).throw(DGeniesClusterRunError("prepare failed")),
        raising=False,
    )
    with pytest.raises(DGeniesClusterRunError, match="prepare failed"):
        align_job.prepare_align_cluster("sge")

    env_local = _setup_job_manager_env(monkeypatch, tmp_path / "dotplot_local")
    local_module = env_local.module
    plot_job = _make_manager(
        env_local,
        "parser_plot",
        query=None,
        target=DataFile("target", str(tmp_path / "plot_target.fa"), "local"),
        align=DataFile("align", str(tmp_path / "plot_align.maf"), "local"),
        tool=None,
    )
    Path(plot_job.target.get_path()).write_text(">t\nACGT\n")
    Path(plot_job.align.get_path()).write_text("maf\n")

    class DummySorter:
        def __init__(self, src, dst):
            self.src = src
            self.dst = dst

        def sort(self):
            Path(self.dst).write_text(Path(self.src).read_text())

    monkeypatch.setattr(local_module, "Sorter", DummySorter, raising=False)
    monkeypatch.setattr(local_module.parsers, "maf", lambda src, dst: Path(dst).write_text(Path(src).read_text()), raising=False)
    monkeypatch.setattr(plot_job, "send_mail_post_if_allowed", lambda: None, raising=False)
    plot_job._end_of_prepare_dotplot()
    assert plot_job.align.get_path() == plot_job.paf
    assert not Path(plot_job.target.get_path()).exists()

    missing_parser_job = _make_manager(
        env_local,
        "missing_parser_plot",
        query=None,
        target=DataFile("target", str(tmp_path / "missing_parser_target.fa"), "local"),
        align=DataFile("align", str(tmp_path / "missing_parser.align"), "local"),
        tool=None,
    )
    Path(missing_parser_job.target.get_path()).write_text(">t\nACGT\n")
    Path(missing_parser_job.align.get_path()).write_text("unknown\n")
    missing_parser_job.aln_format = "unknown"
    with pytest.raises(DGeniesMissingParserError, match="unknown"):
        missing_parser_job._end_of_prepare_dotplot()

    idx_target = tmp_path / "input_target.idx"
    idx_query = tmp_path / "input_query.idx"
    idx_align = tmp_path / "input_map.paf"
    idx_target.write_text("Target\nchr1\t4\n")
    idx_query.write_text("Query\nchr1\t4\n")
    idx_align.write_text("map\n")
    cluster_plot = _make_manager(
        env,
        "plot_cluster_idx",
        query=DataFile("query", str(idx_query), "local"),
        target=DataFile("target", str(idx_target), "local"),
        align=DataFile("map", str(idx_align), "local"),
        tool=None,
    )
    Path(cluster_plot.output_dir, ".target").write_text(str(idx_target))
    Path(cluster_plot.output_dir, ".query").write_text(str(idx_query))
    end_calls = []
    updates = []
    monkeypatch.setattr(cluster_plot, "_end_of_prepare_dotplot", lambda: end_calls.append("done"), raising=False)
    monkeypatch.setattr(cluster_plot, "update_job_status", lambda status, pid=None: updates.append((status, pid)), raising=False)
    cluster_plot.prepare_dotplot_cluster("slurm")
    assert Path(cluster_plot.idx_t).read_text() == "Target\nchr1\t4\n"
    assert Path(cluster_plot.idx_q).read_text() == "Query\nchr1\t4\n"
    assert not Path(cluster_plot.output_dir, ".target").exists()
    assert not Path(cluster_plot.output_dir, ".query").exists()
    assert updates == [("prepared", None)]
    assert end_calls == ["done"]

    failing_cluster_plot = _make_manager(
        env,
        "plot_cluster_raise",
        query=query,
        target=target,
        align=DataFile("map", str(tmp_path / "plot_cluster_raise.paf"), "local"),
        tool=None,
    )
    Path(failing_cluster_plot.align.get_path()).write_text("map\n")
    monkeypatch.setattr(
        failing_cluster_plot,
        "launch_to_cluster",
        lambda **_kwargs: (_ for _ in ()).throw(DGeniesClusterRunError("index failed")),
        raising=False,
    )
    with pytest.raises(DGeniesClusterRunError, match="index failed"):
        failing_cluster_plot.prepare_dotplot_cluster("slurm")

    local_plot = _make_manager(
        env_local,
        "plot_local_index",
        query=DataFile("query", str(tmp_path / "plot_local_query.fa"), "local"),
        target=DataFile("target", str(tmp_path / "plot_local_target.fa"), "local"),
        align=DataFile("map", str(tmp_path / "plot_local_map.paf"), "local"),
        tool=None,
    )
    Path(local_plot.query.get_path()).write_text(">q\nACGT\n")
    Path(local_plot.target.get_path()).write_text(">t\nACGT\n")
    Path(local_plot.align.get_path()).write_text("map\n")
    monkeypatch.setattr(
        local_module,
        "index_file",
        lambda _path, name, out_idx, _uncompressed=None: (Path(out_idx).write_text(f"{name}\nchr1\t4\n") or True, 1, ""),
        raising=False,
    )
    monkeypatch.setattr(local_plot, "_end_of_prepare_dotplot", lambda: end_calls.append("local"), raising=False)
    local_plot.prepare_dotplot_local()
    assert Path(local_plot.idx_t).exists()
    assert Path(local_plot.idx_q).exists()
    assert "Index target file" in Path(local_plot.logs).read_text()
    assert end_calls[-1] == "local"

    local_plot_error = _make_manager(
        env_local,
        "plot_local_error",
        query=DataFile("query", str(tmp_path / "plot_local_error_query.fa"), "local"),
        target=DataFile("target", str(tmp_path / "plot_local_error_target.fa"), "local"),
        align=DataFile("map", str(tmp_path / "plot_local_error_map.paf"), "local"),
        tool=None,
    )
    Path(local_plot_error.query.get_path()).write_text(">q\nACGT\n")
    Path(local_plot_error.target.get_path()).write_text(">t\nACGT\n")
    Path(local_plot_error.align.get_path()).write_text("map\n")
    monkeypatch.setattr(local_plot_error, "_end_of_prepare_dotplot", lambda: (_ for _ in ()).throw(DGeniesMissingParserError("maf")), raising=False)
    with pytest.raises(DGeniesMissingParserError, match="maf"):
        local_plot_error.prepare_dotplot_local()

    query_idx_plot = _make_manager(
        env_local,
        "plot_local_query_idx",
        query=DataFile("query", str(tmp_path / "plot_local_query.idx"), "local"),
        target=DataFile("target", str(tmp_path / "plot_local_target_2.fa"), "local"),
        align=DataFile("map", str(tmp_path / "plot_local_map_2.paf"), "local"),
        tool=None,
    )
    Path(query_idx_plot.query.get_path()).write_text("Query\nchr1\t4\n")
    Path(query_idx_plot.target.get_path()).write_text(">t\nACGT\n")
    Path(query_idx_plot.align.get_path()).write_text("map\n")
    Path(query_idx_plot.output_dir, ".query").write_text(query_idx_plot.query.get_path())
    monkeypatch.setattr(query_idx_plot, "_end_of_prepare_dotplot", lambda: None, raising=False)
    query_idx_plot.prepare_dotplot_local()
    assert Path(query_idx_plot.idx_q).read_text() == "Query\nchr1\t4\n"
    assert not Path(query_idx_plot.output_dir, ".query").exists()


def test_job_manager_run_align_backup_distribution_and_start_error_paths(monkeypatch, tmp_path):
    env = _setup_job_manager_env(monkeypatch, tmp_path, mode="webserver")
    module = env.module

    batch_manager = _make_manager(env, "batch_refresh", tool=None)
    refresh_calls = []
    monkeypatch.setattr(batch_manager, "refresh_batch_status", lambda: "started-batch", raising=False)
    monkeypatch.setattr(batch_manager, "set_job_status", lambda status, error="": refresh_calls.append((status, error)), raising=False)
    batch_manager.batch = []
    batch_manager.run_align("local")
    assert refresh_calls == [("started-batch", "")]
    batch_status_manager = _make_manager(env, "batch_status_parent", tool=None)
    Path(batch_status_manager.output_dir, ".batch").write_text("sub_started\n")
    monkeypatch.setattr(module.JobManager, "status", lambda self: {"status": "started"}, raising=False)
    assert batch_status_manager.refresh_batch_status() == "started-batch"

    query = DataFile("query", str(tmp_path / "run_query.fa"), "local")
    target = DataFile("target", str(tmp_path / "run_target.fa"), "local")
    Path(query.get_path()).write_text(">q\nACGT\n")
    Path(target.get_path()).write_text(">t\nACGT\n")

    split_job = _make_manager(env, "run_align_split_web", query=query, target=target, tool="splitter")
    env.DummyJob.create(
        id_job=split_job.id_job,
        email="user@example.org",
        runner_type="local",
        date_created=datetime.now(),
        tool=split_job.tool_name,
        options=split_job.options,
    )
    Path(split_job.logs).write_text("header\n5 100\n")
    Path(split_job.preptime_file).write_text("10\n20\n")
    Path(split_job.get_query_split()).write_text(">q\nACGT\n")
    Path(split_job.query_index_split).write_text("Query\nchr1\t4\n")
    Path(split_job.paf_raw).write_text("raw\n")
    mailed = []
    analytics = []

    class DummyMerger:
        def __init__(self, paf_in, paf_out, query_index_split, idx_q, debug=False):
            self.paf_out = paf_out
            self.idx_q = idx_q

        def merge(self):
            Path(self.paf_out).write_text("merged\n")
            Path(self.idx_q).write_text("Query\nchr1\t4\n")

    class DummySorter:
        def __init__(self, src, dst):
            self.src = src
            self.dst = dst

        def sort(self):
            Path(self.dst).write_text(Path(self.src).read_text())

    monkeypatch.setattr(module, "Merger", DummyMerger, raising=False)
    monkeypatch.setattr(module, "Sorter", DummySorter, raising=False)
    monkeypatch.setattr(split_job, "_launch_local", lambda: None, raising=False)
    monkeypatch.setattr(split_job, "_set_analytics_job_status", lambda status: analytics.append(status), raising=False)
    monkeypatch.setattr(split_job, "send_mail_post_if_allowed", lambda: mailed.append("sent"), raising=False)
    split_job.run_align("local")
    split_record = env.DummyJob.get(id_job=split_job.id_job)
    assert split_record.status == "success"
    assert split_record.time_elapsed >= 15
    assert analytics == ["success"]
    assert mailed == ["sent"]
    assert not Path(target.get_path()).exists()

    ava_target = DataFile("target", str(tmp_path / "ava_target.fa"), "local")
    Path(ava_target.get_path()).write_text(">t\nACGT\n")
    ava_job = _make_manager(env, "run_align_ava_web", query=None, target=ava_target, tool="minimap2")
    env.DummyJob.create(
        id_job=ava_job.id_job,
        email="user@example.org",
        runner_type="local",
        date_created=datetime.now(),
        tool=ava_job.tool_name,
        options=ava_job.options,
    )
    Path(ava_job.logs).write_text("header\n7 120\n")
    Path(ava_job.preptime_file).write_text("3\n9\n")
    Path(ava_job.paf_raw).write_text("raw\n")
    Path(ava_job.idx_t).write_text("Target\nchr1\t4\n")
    monkeypatch.setattr(ava_job, "_launch_local", lambda: None, raising=False)
    ava_job.run_align("local")
    assert Path(ava_job.idx_q).read_text() == Path(ava_job.idx_t).read_text()
    assert Path(ava_job.output_dir, ".all-vs-all").exists()

    class FailingPaf:
        def __init__(self, **kwargs):
            self.parsed = False

        def sort(self):
            self.parsed = False

    sort_fail_target = DataFile("target", str(tmp_path / "sort_fail_target.fa"), "local")
    Path(sort_fail_target.get_path()).write_text(">t\nACGT\n")
    sort_fail_job = _make_manager(env, "run_align_sort_fail_web", query=None, target=sort_fail_target, tool="minimap2")
    env.DummyJob.create(
        id_job=sort_fail_job.id_job,
        email="user@example.org",
        runner_type="local",
        date_created=datetime.now(),
        tool=sort_fail_job.tool_name,
        options=sort_fail_job.options,
    )
    Path(sort_fail_job.logs).write_text("header\n5 100\n")
    Path(sort_fail_job.preptime_file).write_text("1\n2\n")
    Path(sort_fail_job.paf_raw).write_text("raw\n")
    Path(sort_fail_job.idx_t).write_text("Target\nchr1\t4\n")
    Path(sort_fail_job.output_dir, ".do-sort").write_text("")
    sort_analytics = []
    monkeypatch.setattr(module, "Paf", FailingPaf, raising=False)
    monkeypatch.setattr(sort_fail_job, "_launch_local", lambda: None, raising=False)
    monkeypatch.setattr(sort_fail_job, "_set_analytics_job_status", lambda status: sort_analytics.append(status), raising=False)
    sort_fail_job.run_align("local")
    sort_fail_record = env.DummyJob.get(id_job=sort_fail_job.id_job)
    assert sort_fail_record.status == "fail"
    assert "sorting query" in sort_fail_record.error
    assert sort_analytics == ["fail-sort"]

    env_local = _setup_job_manager_env(monkeypatch, tmp_path / "run_align_local")
    local_module = env_local.module
    standalone_sort_target = DataFile("target", str(tmp_path / "standalone_sort_target.fa"), "local")
    Path(standalone_sort_target.get_path()).write_text(">t\nACGT\n")
    standalone_sort_job = _make_manager(env_local, "run_align_sort_fail_local", query=None, target=standalone_sort_target, tool="minimap2")
    Path(standalone_sort_job.logs).write_text("header\n5 100\n")
    Path(standalone_sort_job.preptime_file).write_text("1\n2\n")
    Path(standalone_sort_job.paf_raw).write_text("raw\n")
    Path(standalone_sort_job.idx_t).write_text("Target\nchr1\t4\n")
    Path(standalone_sort_job.output_dir, ".do-sort").write_text("")
    monkeypatch.setattr(local_module, "Sorter", DummySorter, raising=False)
    monkeypatch.setattr(local_module, "Paf", FailingPaf, raising=False)
    monkeypatch.setattr(standalone_sort_job, "_launch_local", lambda: None, raising=False)
    standalone_sort_job.run_align("local")
    assert standalone_sort_job.get_status_standalone(with_error=True) == [
        "fail",
        "Error while sorting query. Please contact us to report the bug",
    ]

    cluster_fail_job = _make_manager(env_local, "run_align_cluster_fail", query=query, target=DataFile("target", str(tmp_path / "cluster_fail_target.fa"), "local"), tool="minimap2")
    Path(cluster_fail_job.target.get_path()).write_text(">t\nACGT\n")
    monkeypatch.setattr(cluster_fail_job, "_launch_drmaa", lambda _runner_type: (_ for _ in ()).throw(DGeniesRunError("cluster failed")), raising=False)
    cluster_fail_job.run_align("slurm")
    assert cluster_fail_job.get_status_standalone(with_error=True) == ["fail", "cluster failed"]

    env_web_again = _setup_job_manager_env(monkeypatch, tmp_path / "run_align_web_again", mode="webserver")
    web_module = env_web_again.module
    known_error_job = _make_manager(
        env_web_again,
        "download_known_error",
        query=None,
        target=DataFile.create("remote.fa.gz", "https://example.org/remote.fa.gz"),
        tool="minimap2",
    )
    env_web_again.DummyJob.create(
        id_job=known_error_job.id_job,
        email="user@example.org",
        runner_type="slurm",
        date_created=datetime.now(),
        tool=known_error_job.tool_name,
        options=known_error_job.options,
    )

    class UploadSession:
        def __init__(self):
            self.deleted = 0

        def ask_for_upload(self, change_status=False):
            return True

        def delete_instance(self):
            self.deleted += 1

    upload_session = UploadSession()
    monkeypatch.setattr(web_module, "Session", SimpleNamespace(new=lambda *_args, **_kwargs: "session", get=lambda **_kwargs: upload_session), raising=False)
    monkeypatch.setattr(known_error_job, "_getting_file_from_url", lambda _datafile: (_ for _ in ()).throw(DGeniesURLInvalid("https://example.org/remote.fa.gz")), raising=False)
    with pytest.raises(DGeniesURLInvalid):
        known_error_job.download_files_with_pending(web_module.DataFileContextManager([known_error_job]), True)
    assert upload_session.deleted == 1

    backup_job = _make_manager(
        env_local,
        "backup_paths",
        query=None,
        target=DataFile("target", str(tmp_path / "backup_target.fa"), "local"),
        tool="minimap2",
    )
    Path(backup_job.target.get_path()).write_text(">t\nACGT\n")

    bad_member_backup = tmp_path / "bad_member.tar.gz"
    with tarfile.open(bad_member_backup, "w:gz") as tar:
        map_file = tmp_path / "bad_map.paf"
        query_idx = tmp_path / "bad_query.idx"
        target_idx = tmp_path / "bad_target.idx"
        extra = tmp_path / "extra.txt"
        map_file.write_text("query\t4\t0\t4\t+\ttarget\t4\t0\t4\t4\t4\t255\n")
        query_idx.write_text("Query\nchr1\t4\n")
        target_idx.write_text("Target\nchr1\t4\n")
        extra.write_text("bad\n")
        tar.add(map_file, arcname="map.paf")
        tar.add(query_idx, arcname="query.idx")
        tar.add(target_idx, arcname="target.idx")
        tar.add(extra, arcname="extra.txt")
    with pytest.raises(DGeniesBackupUnpackError):
        backup_job._unpack_backup(DataFile("backup", str(bad_member_backup), "local"), str(tmp_path / "unpack_bad_member"))

    valid_backup = tmp_path / "valid_backup.tar.gz"
    _build_backup(valid_backup)
    monkeypatch.setattr(local_module.validators, "paf", lambda _path: False, raising=False)
    with pytest.raises(DGeniesBackupUnpackError):
        backup_job._unpack_backup(DataFile("backup", str(valid_backup), "local"), str(tmp_path / "unpack_bad_paf"))

    monkeypatch.setattr(local_module.validators, "paf", lambda _path: True, raising=False)
    monkeypatch.setattr(local_module.validators, "v_idx", lambda _path: False, raising=False)
    with pytest.raises(DGeniesBackupUnpackError):
        backup_job._unpack_backup(DataFile("backup", str(valid_backup), "local"), str(tmp_path / "unpack_bad_idx"))

    backup_data = DataFile("backup", str(valid_backup), "local")
    plot_backup_job = _make_manager(
        env_local,
        "backup_unpack_error",
        query=None,
        target=None,
        align=None,
        backup=backup_data,
        tool=None,
    )
    monkeypatch.setattr(plot_backup_job, "_unpack_backup", lambda *_args, **_kwargs: (_ for _ in ()).throw(DGeniesBackupUnpackError()), raising=False)
    with pytest.raises(DGeniesBackupUnpackError):
        plot_backup_job.unpack_backups(local_module.DataFileContextManager([plot_backup_job]))

    shared_source = tmp_path / "shared_target.fa"
    shared_source.write_text(">t\n" + ("A" * 80) + "\n")
    shared_data = DataFile("target", str(shared_source), "local")
    shared_data.set_file_size(shared_source.stat().st_size)
    subjob = _make_manager(env_web_again, "distributed_subjob", query=None, target=shared_data, tool="minimap2")
    subjob.config.runner_type = "slurm"
    Path(subjob.output_dir, shared_source.name).write_text("existing\n")
    copies = []
    monkeypatch.setattr(web_module.Functions, "hardlink_or_copy", staticmethod(lambda src, dst: copies.append((src, dst)) or Path(dst).write_text(Path(src).read_text())), raising=False)
    distribute_manager = local_module.DataFileContextManager([subjob])
    backup_job.distribute_files(distribute_manager)
    assert copies[0][1].endswith("2_shared_target.fa")
    assert Path(subjob.output_dir, ".should_not_be_local").exists()

    error_target = DataFile("target", str(tmp_path / "start_error_target.fa"), "local")
    error_target_path = Path(error_target.get_path())
    error_target_path.write_text(">t\nACGT\n")
    start_error_job = _make_manager(env_web_again, "start_known_error", query=None, target=error_target, tool="minimap2")
    env_web_again.DummyJob.create(
        id_job=start_error_job.id_job,
        email="user@example.org",
        runner_type="local",
        date_created=datetime.now(),
        tool=start_error_job.tool_name,
        options=start_error_job.options,
    )
    known_statuses = []
    known_analytics = []
    clears = []
    monkeypatch.setattr(start_error_job, "move_and_check_local_files", lambda _dcm: (_ for _ in ()).throw(DGeniesNotGzipFileError("query")), raising=False)
    monkeypatch.setattr(start_error_job, "set_job_status", lambda status, error="": known_statuses.append((status, error)), raising=False)
    monkeypatch.setattr(start_error_job, "_save_analytics_data", lambda: None, raising=False)
    monkeypatch.setattr(start_error_job, "_set_analytics_job_status", lambda status: known_analytics.append(status), raising=False)
    monkeypatch.setattr(start_error_job, "clear", lambda: clears.append("cleared"), raising=False)
    start_error_job.start_job()
    assert known_statuses[0][0] == "fail"
    assert known_analytics == ["fail-getfiles"]
    assert clears == ["cleared"]

    backup_error_job = _make_manager(env_web_again, "start_backup_error", query=None, target=error_target, tool="minimap2")
    env_web_again.DummyJob.create(
        id_job=backup_error_job.id_job,
        email="user@example.org",
        runner_type="local",
        date_created=datetime.now(),
        tool=backup_error_job.tool_name,
        options=backup_error_job.options,
    )
    backup_statuses = []
    backup_mails = []
    backup_clears = []

    class ClearableBackupError(DGeniesBackupUnpackError):
        @property
        def clear_job(self):
            return True

    monkeypatch.setattr(backup_error_job, "move_and_check_local_files", lambda _dcm: True, raising=False)
    monkeypatch.setattr(backup_error_job, "download_files_with_pending", lambda _dcm, _should: True, raising=False)
    monkeypatch.setattr(backup_error_job, "unpack_backups", lambda _dcm: (_ for _ in ()).throw(ClearableBackupError()), raising=False)
    monkeypatch.setattr(backup_error_job, "set_job_status", lambda status, error="": backup_statuses.append((status, error)), raising=False)
    monkeypatch.setattr(backup_error_job, "_save_analytics_data", lambda: None, raising=False)
    monkeypatch.setattr(backup_error_job, "send_mail_if_allowed", lambda: backup_mails.append("sent"), raising=False)
    monkeypatch.setattr(backup_error_job, "clear", lambda: backup_clears.append("cleared"), raising=False)
    backup_error_job.start_job()
    assert backup_statuses[0][0] == "fail"
    assert backup_mails == ["sent"]
    assert backup_clears == ["cleared"]

    shared_for_remove = DataFile("target", str(tmp_path / "remove_shared.fa"), "local")
    Path(shared_for_remove.get_path()).write_text(">t\nACGT\n")
    remove_job_a = _make_manager(env_local, "remove_a", query=None, target=shared_for_remove, tool="minimap2")
    remove_job_b = _make_manager(env_local, "remove_b", query=None, target=shared_for_remove, tool="minimap2")
    context_manager = local_module.DataFileContextManager([remove_job_a, remove_job_b])
    removed = context_manager.remove(shared_for_remove, job=remove_job_a, file_role="target")
    assert len(removed) == 1
    assert shared_for_remove in context_manager.get_datafiles()
    context_manager.remove(shared_for_remove, job=remove_job_b, file_role="target")
    assert shared_for_remove not in context_manager.get_datafiles()
