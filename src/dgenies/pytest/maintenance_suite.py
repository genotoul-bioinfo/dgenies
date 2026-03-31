"""Maintenance, cron, and cleanup helper tests."""

import builtins
import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

# This file was split out from src/dgenies/test_dgenies_api.py.

def test_crons_and_clean_jobs_helpers(monkeypatch, tmp_path):
    import dgenies.bin.clean_jobs as clean_jobs_module
    import dgenies.lib.crons as crons_module

    class FakeField:
        def __init__(self):
            self.every_value = None
            self.on_value = None

        def every(self, value):
            self.every_value = value

        def on(self, value):
            self.on_value = value

    class FakeJob:
        def __init__(self, command, comment):
            self.command = command
            self.comment = comment
            self.day = FakeField()
            self.hour = FakeField()
            self.minute = FakeField()

    class FakeCronTab:
        def __init__(self, user=True):
            self.user = user
            self.jobs = []
            self.removed = []
            self.write_calls = 0

        def remove_all(self, comment=None):
            self.removed.append(comment)

        def write(self):
            self.write_calls += 1

        def new(self, command, comment=None):
            job = FakeJob(command, comment)
            self.jobs.append(job)
            return job

    fake_config = SimpleNamespace(
        config_dir=str(tmp_path),
        cron_clean_time=(1, 30),
        cron_clean_freq=2,
        log_dir=str(tmp_path),
        upload_folder=str(tmp_path / "uploads"),
        app_data=str(tmp_path / "jobs"),
    )
    monkeypatch.setattr(crons_module, "CronTab", FakeCronTab, raising=False)
    monkeypatch.setattr(crons_module, "AppConfigReader", lambda: fake_config, raising=False)

    monkeypatch.setattr(crons_module.sys, "executable", "/env/lib/python3.14/site-packages/bin/python", raising=False)
    crons = crons_module.Crons("/base", debug=True)
    assert crons._get_python_exec() == "/env/bin/python3.14"

    pid_file = Path(crons.local_scheduler_pid_file)
    pid_file.write_text("1234\n")
    terminated = []
    monkeypatch.setattr(crons_module.psutil, "pid_exists", lambda pid: pid == 1234, raising=False)
    monkeypatch.setattr(crons_module.psutil, "Process", lambda pid: SimpleNamespace(terminate=lambda: terminated.append(pid)), raising=False)
    crons.clear()
    assert terminated == [1234]
    assert not pid_file.exists()
    assert crons.my_cron.removed == ["dgenies"]

    crons.init_clean_cron()
    assert "clean_jobs.py" in crons.my_cron.jobs[0].command
    assert crons.my_cron.jobs[0].day.every_value == 2
    assert crons.my_cron.jobs[0].hour.on_value == 1
    assert crons.my_cron.jobs[0].minute.on_value == 30

    crons.init_launch_local_cron()
    assert "start_local_scheduler.sh" in crons.my_cron.jobs[1].command
    assert str(pid_file) in crons.my_cron.jobs[1].command
    assert crons.my_cron.jobs[1].minute.every_value == 1

    started = []
    monkeypatch.setattr(crons, "clear", lambda kill_scheduler=True, remove_pid_file=True: started.append(("clear", kill_scheduler, remove_pid_file)), raising=False)
    monkeypatch.setattr(crons, "init_clean_cron", lambda: started.append(("clean",)), raising=False)
    monkeypatch.setattr(crons, "init_launch_local_cron", lambda: started.append(("local",)), raising=False)
    crons.start_all()
    assert started == [("clear", False, True), ("clean",), ("local",)]

    crons.base_dir = None
    with pytest.raises(Exception, match="base_dir must not be None"):
        crons_module.Crons.init_clean_cron(crons)

    upload_dir = Path(fake_config.upload_folder)
    upload_dir.mkdir()
    old_folder = upload_dir / "old_folder"
    old_folder.mkdir()
    old_file = upload_dir / "old.txt"
    old_file.write_text("old")
    fresh_file = upload_dir / "fresh.txt"
    fresh_file.write_text("fresh")

    now = 10 * 86400
    ctime_map = {
        str(old_folder): 0,
        str(old_file): 0,
        str(fresh_file): now,
    }
    monkeypatch.setattr(clean_jobs_module.os.path, "getctime", lambda path: ctime_map[str(path)], raising=False)
    clean_jobs_module.parse_upload_folders(str(upload_dir), now, {"uploads": 1}, fake=False)
    assert not old_folder.exists()
    assert not old_file.exists()
    assert fresh_file.exists()

    old_folder.mkdir()
    old_file.write_text("old")
    ctime_map[str(old_folder)] = 0
    ctime_map[str(old_file)] = 0
    clean_jobs_module.parse_upload_folders(str(upload_dir), now, {"uploads": 1}, fake=True)
    assert old_folder.exists()
    assert old_file.exists()

    broken_folder = upload_dir / "broken_folder"
    broken_folder.mkdir()
    ctime_map[str(broken_folder)] = 0
    logger_calls = []
    real_rmtree = clean_jobs_module.shutil.rmtree

    def failing_rmtree(path):
        if Path(path) == broken_folder:
            raise OSError("permission denied")
        return real_rmtree(path)

    monkeypatch.setattr(clean_jobs_module.shutil, "rmtree", failing_rmtree, raising=False)
    monkeypatch.setattr(clean_jobs_module.logger, "exception", lambda *_args, **_kwargs: logger_calls.append("upload"), raising=False)
    clean_jobs_module.parse_upload_folders(str(upload_dir), now, {"uploads": 1}, fake=False)
    assert logger_calls == ["upload"]

    app_data = Path(fake_config.app_data)
    app_data.mkdir()
    gallery_dir = app_data / "gallery"
    gallery_dir.mkdir()
    obsolete_file = app_data / "obsolete.txt"
    obsolete_file.write_text("obsolete")
    stale_job = app_data / "stale_job"
    stale_job.mkdir()
    fresh_job = app_data / "fresh_job"
    fresh_job.mkdir()
    (fresh_job / ".query").write_text("query.fa\n")
    sorted_fasta = fresh_job / "query.fa.sorted"
    sorted_fasta.write_text(">q\nACGT\n")
    query_ref = fresh_job / "as_reference_query.fa"
    query_ref.write_text(">q\nACGT\n")

    ctime_map.update({
        str(obsolete_file): 0,
        str(stale_job): 0,
        str(fresh_job): now,
        str(sorted_fasta): 0,
        str(query_ref): 0,
    })
    monkeypatch.setattr(clean_jobs_module.Functions, "get_fasta_file", staticmethod(lambda _res_dir, _type_f, _sorted: str(sorted_fasta)), raising=False)
    clean_jobs_module.parse_data_folders(
        str(app_data),
        gallery_jobs=["gallery_job"],
        now=now,
        max_age={"data": 1, "fasta_sorted": 1},
        fake=False,
    )
    assert not obsolete_file.exists()
    assert not stale_job.exists()
    assert gallery_dir.exists()
    assert fresh_job.exists()
    assert not sorted_fasta.exists()
    assert not query_ref.exists()

    fresh_job_no_sorted = app_data / "fresh_job_no_sorted"
    fresh_job_no_sorted.mkdir()
    (fresh_job_no_sorted / ".query").write_text("query.fa\n")
    unsorted_query = fresh_job_no_sorted / "query.fa"
    unsorted_query.write_text(">q\nACGT\n")
    stale_file = app_data / "stale_again.txt"
    stale_file.write_text("obsolete")
    ctime_map.update({
        str(fresh_job_no_sorted): now,
        str(stale_file): 0,
    })
    real_remove = clean_jobs_module.os.remove

    def failing_remove(path):
        if Path(path) == stale_file:
            raise OSError("permission denied")
        return real_remove(path)

    safe_extra = app_data / "safe_extra.txt"
    safe_extra.write_text("safe")
    assert failing_remove(str(safe_extra)) is None
    monkeypatch.setattr(clean_jobs_module.os, "remove", failing_remove, raising=False)
    monkeypatch.setattr(clean_jobs_module.Functions, "get_fasta_file", staticmethod(lambda _res_dir, _type_f, _sorted: str(unsorted_query)), raising=False)
    clean_jobs_module.parse_data_folders(
        str(app_data),
        gallery_jobs=[],
        now=now,
        max_age={"data": 1, "fasta_sorted": 1},
        fake=False,
    )
    assert logger_calls == ["upload", "upload"]

def test_clean_jobs_database_main_and_remaining_parser_validator_branches(monkeypatch, tmp_path):
    import builtins
    import dgenies
    import dgenies.bin.clean_jobs as clean_jobs_module
    import dgenies.lib.parsers as parsers_module
    import dgenies.lib.validators as validators_module

    missing_paf = tmp_path / "missing.paf"
    assert validators_module.paf(str(missing_paf)) is False
    assert validators_module.v_idx(str(tmp_path / "missing.idx")) is False

    extra_after_blank = tmp_path / "extra_after_blank.idx"
    extra_after_blank.write_text("Query\nchr1\t10\n\nchr2\t20\n")
    wrong_columns = tmp_path / "wrong_columns.idx"
    wrong_columns.write_text("Query\nchr1\t10\t1\n")
    non_digit = tmp_path / "non_digit.idx"
    non_digit.write_text("Query\nchr1\tABC\n")
    assert validators_module.v_idx(str(extra_after_blank)) is False
    assert validators_module.v_idx(str(wrong_columns)) is False
    assert validators_module.v_idx(str(non_digit)) is False

    class FakeSeq:
        def __init__(self, seq_id, seq, annotations):
            self.id = seq_id
            self._seq = seq
            self.annotations = annotations

        def __getitem__(self, index):
            return self._seq[index]

        def __len__(self):
            return len(self._seq)

    class ExplodingParser:
        def __init__(self):
            self.closed = False

        def __iter__(self):
            raise ValueError("explode")

        def close(self):
            self.closed = True

    exploding = ExplodingParser()
    monkeypatch.setattr(parsers_module.AlignIO, "parse", lambda *_args, **_kwargs: exploding, raising=False)
    assert parsers_module.maf(str(tmp_path / "input.maf"), str(tmp_path / "output.paf")) is False
    assert exploding.closed is True

    class IterableParser:
        def __init__(self, groups):
            self.groups = groups
            self.closed = False

        def __iter__(self):
            return iter(self.groups)

        def close(self):
            self.closed = True

    reverse_target = FakeSeq("target", "ACGT", {"srcSize": 100, "start": 10, "size": 4, "strand": -1})
    reverse_query = FakeSeq("query", "ACGT", {"srcSize": 50, "start": 5, "size": 4, "strand": -1})
    reverse_parser = IterableParser([[reverse_target, reverse_query]])
    reverse_out = tmp_path / "reverse.paf"
    monkeypatch.setattr(parsers_module.AlignIO, "parse", lambda *_args, **_kwargs: reverse_parser, raising=False)
    assert parsers_module.maf(str(tmp_path / "input.maf"), str(reverse_out)) is True
    assert reverse_parser.closed is True
    assert reverse_out.read_text().strip() == "query\t50\t45\t41\t+\ttarget\t100\t90\t86\t4\t4\t255"

    class FakeExpr:
        def __init__(self):
            self.last = None

        def __eq__(self, other):
            self.last = other
            return self

        def __ne__(self, other):
            self.last = other
            return self

        def __lt__(self, other):
            self.last = other
            return self

        def __and__(self, other):
            return self

        def __or__(self, other):
            return self

    class DummyConnect:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    deleted_jobs = []

    class FakeJobRow:
        def __init__(self, job_id):
            self.id_job = job_id

        def delete_instance(self):
            deleted_jobs.append(self.id_job)

    class FakeJobQuery(list):
        def where(self, *_args, **_kwargs):
            return self

    class FakeGalleryQuery:
        def join(self, *_args, **_kwargs):
            return self

        def where(self, *_args, **_kwargs):
            return [1] if FakeJob.id_job.last == "gallery_job" else []

    class FakeJob:
        status = FakeExpr()
        date_created = FakeExpr()
        id_job = FakeExpr()

        @staticmethod
        def connect():
            return DummyConnect()

        @staticmethod
        def select():
            return FakeJobQuery([FakeJobRow("gallery_job"), FakeJobRow("remove_job"), FakeJobRow("missing_job")])

    class FakeGallery:
        @staticmethod
        def select():
            return FakeGalleryQuery()

    fake_db = ModuleType("dgenies.database")
    fake_db.Job = FakeJob
    fake_db.Gallery = FakeGallery
    fake_db.initialize = lambda: deleted_jobs.append("initialize")
    monkeypatch.setitem(sys.modules, "dgenies.database", fake_db)
    monkeypatch.setattr(dgenies, "database", fake_db, raising=False)

    app_data = tmp_path / "jobs_main"
    app_data.mkdir()
    (app_data / "remove_job").mkdir()

    gallery_jobs = clean_jobs_module.parse_database(str(app_data), {"data": 7, "error": 1}, fake=False)
    assert gallery_jobs == ["gallery_job"]
    assert not (app_data / "remove_job").exists()
    assert deleted_jobs == ["remove_job", "missing_job"]

    (app_data / "remove_job").mkdir()
    deleted_jobs.clear()
    clean_jobs_module.parse_database(str(app_data), {"data": 7, "error": 1}, fake=True)
    assert (app_data / "remove_job").exists()
    assert deleted_jobs == []

    reset_calls = []
    recorded = []
    monkeypatch.setattr(
        clean_jobs_module,
        "config_reader",
        SimpleNamespace(
            upload_folder=str(tmp_path / "uploads_main"),
            app_data=str(app_data),
            reset_config=lambda configs: reset_calls.append(configs),
        ),
        raising=False,
    )
    monkeypatch.setattr(clean_jobs_module.time, "time", lambda: 1234567890, raising=False)
    monkeypatch.setattr(clean_jobs_module, "parse_upload_folders", lambda **kwargs: recorded.append(("uploads", kwargs)), raising=False)
    monkeypatch.setattr(clean_jobs_module, "parse_database", lambda **kwargs: recorded.append(("database", kwargs)) or ["gallery_job"], raising=False)
    monkeypatch.setattr(clean_jobs_module, "parse_data_folders", lambda **kwargs: recorded.append(("data", kwargs)), raising=False)

    parse_args_success = SimpleNamespace(fake=True, max_age=5, log_file=str(tmp_path / "clean.log"), config=["conf.properties"])
    monkeypatch.setattr(clean_jobs_module.argparse.ArgumentParser, "parse_args", lambda self: parse_args_success, raising=False)
    clean_jobs_module.main()
    assert reset_calls == [["conf.properties"]]
    assert deleted_jobs == ["initialize"]
    assert recorded[0][0] == "uploads"
    assert recorded[1][0] == "database"
    assert recorded[2][0] == "data"

    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "dgenies.database":
            raise ImportError("missing db")
        return original_import(name, globals, locals, fromlist, level)

    parse_args_import_error = SimpleNamespace(fake=False, max_age=3, log_file=None, config=None)
    monkeypatch.setattr(clean_jobs_module.argparse.ArgumentParser, "parse_args", lambda self: parse_args_import_error, raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import, raising=False)
    sys.modules.pop("dgenies.database", None)
    recorded.clear()
    clean_jobs_module.main()
    assert [entry[0] for entry in recorded] == ["uploads", "database", "data"]
    monkeypatch.setattr(builtins, "__import__", original_import, raising=False)

    import importlib
    config_reader_module = importlib.import_module("dgenies.config_reader")

    uploads_guard = tmp_path / "uploads_guard"
    data_guard = tmp_path / "data_guard"
    uploads_guard.mkdir()
    data_guard.mkdir()
    monkeypatch.setattr(
        config_reader_module,
        "AppConfigReader",
        lambda *_args, **_kwargs: SimpleNamespace(
            upload_folder=str(uploads_guard),
            app_data=str(data_guard),
            reset_config=lambda _configs: None,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        clean_jobs_module.argparse.ArgumentParser,
        "parse_args",
        lambda self: SimpleNamespace(fake=True, max_age=1, log_file=None, config=None),
        raising=False,
    )
    monkeypatch.setitem(sys.modules, "dgenies.database", fake_db)
    sys.modules.pop("dgenies.bin.clean_jobs", None)
    runpy.run_module("dgenies.bin.clean_jobs", run_name="__main__")
