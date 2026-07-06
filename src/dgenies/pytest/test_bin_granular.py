import importlib
import sys
import types
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path

import pytest


def test_index_file_rejects_invalid_sequence_line(tmp_path):
    from dgenies.bin.index import index_file

    fasta = tmp_path / "bad.fa"
    out = tmp_path / "bad.idx"
    fasta.write_text(">ctg\nACGT\nBAD!\n")

    assert index_file(str(fasta), "Bad", str(out)) == (False, 0, "Error: invalid sequence at line 3")


def test_index_file_rejects_empty_contig_before_next_header(tmp_path):
    from dgenies.bin.index import index_file

    fasta = tmp_path / "bad.fa"
    out = tmp_path / "bad.idx"
    fasta.write_text(">empty\n>next\nACGT\n")

    assert index_file(str(fasta), "Bad", str(out)) == (False, 0, "Error: contig is empty: empty")


def test_index_file_requires_header_after_blank_sequence_line(tmp_path):
    from dgenies.bin.index import index_file

    fasta = tmp_path / "bad.fa"
    out = tmp_path / "bad.idx"
    fasta.write_text(">ctg\nACGT\n\nACGT\n")

    assert index_file(str(fasta), "Bad", str(out)) == (False, 0, "Error: new header line expected at line 4")


def test_index_file_reports_no_header_for_plain_sequence(tmp_path):
    from dgenies.bin.index import index_file

    fasta = tmp_path / "bad.fa"
    out = tmp_path / "bad.idx"
    fasta.write_text("ACGT\n")

    assert index_file(str(fasta), "Bad", str(out)) == (False, 0, "")
    assert out.read_text() == "Bad\n"


def test_index_file_can_copy_fasta_while_indexing(tmp_path):
    from dgenies.bin.index import index_file

    fasta = tmp_path / "query.fa"
    copied = tmp_path / "copied.fa"
    out = tmp_path / "query.idx"
    fasta.write_text(">q\nACGT\n")

    assert index_file(str(fasta), "Query", str(out), write_fa=str(copied)) == (True, 1, "")
    assert copied.read_text() == fasta.read_text()


def test_splitter_split_contig_keeps_sequence_below_threshold():
    from dgenies.bin.split_fa import Splitter

    assert Splitter.split_contig("ctg", "A" * 10, 10) == {"ctg": "A" * 10}


def test_splitter_write_contig_wraps_sequence_at_sixty_bases(tmp_path):
    from dgenies.bin.split_fa import Splitter

    out = tmp_path / "out.fa"
    with out.open("w") as handle:
        Splitter.write_contig("ctg", "A" * 61, handle)

    assert out.read_text().splitlines() == [">ctg", "A" * 60, "A", ""]


def test_splitter_rejects_invalid_sequence_line(tmp_path):
    from dgenies.bin.split_fa import Splitter

    fasta = tmp_path / "bad.fa"
    output = tmp_path / "split.fa"
    fasta.write_text(">ctg\nACGT\nBAD!\n")

    assert Splitter(str(fasta), "Bad", str(output), size_c=10).split() == (
        False,
        "Error: invalid sequence at line 3",
    )


def test_splitter_rejects_empty_contig_before_next_header(tmp_path):
    from dgenies.bin.split_fa import Splitter

    fasta = tmp_path / "bad.fa"
    output = tmp_path / "split.fa"
    fasta.write_text(">empty\n>next\nACGT\n")

    assert Splitter(str(fasta), "Bad", str(output), size_c=10).split() == (
        False,
        "Error: contig is empty: empty",
    )


def test_splitter_reports_no_header_for_plain_sequence(tmp_path):
    from dgenies.bin.split_fa import Splitter

    fasta = tmp_path / "bad.fa"
    output = tmp_path / "split.fa"
    fasta.write_text("ACGT\n")

    splitter = Splitter(str(fasta), "Bad", str(output), size_c=10)

    assert splitter.split() == (False, "")
    assert splitter.nb_contigs == 1


def test_merger_get_sorted_splits_orders_numeric_split_ids():
    from dgenies.bin.merge_splitted_chrms import Merger

    all_contigs, splits = Merger._get_sorted_splits({"ctg": {"10": 2, "2": 3, "1": 5}}, {})

    assert all_contigs == {"ctg": 10}
    assert list(splits["ctg"].items()) == [("1", 0), ("2", 5), ("10", 8)]


def test_merger_write_query_index_preserves_order(tmp_path):
    from collections import OrderedDict

    from dgenies.bin.merge_splitted_chrms import Merger

    out = tmp_path / "query.idx"

    Merger.write_query_index(str(out), OrderedDict([("first", 10), ("second", 20)]), "Query")

    assert out.read_text().splitlines() == ["Query", "first\t10", "second\t20"]


def test_merger_printer_is_silent_unless_debug_enabled(capsys):
    from dgenies.bin.merge_splitted_chrms import Merger

    Merger("in", "out", "qin", "qout", debug=False)._printer("silent")
    assert capsys.readouterr().out == ""

    Merger("in", "out", "qin", "qout", debug=True)._printer("visible")
    assert capsys.readouterr().out == "visible\n"


def test_sorter_sort_lines_applies_identity_weight(tmp_path):
    from io import StringIO

    from dgenies.bin.sort_paf import Sorter

    paf = tmp_path / "map.paf"
    paf.write_text("")
    lines = StringIO(
        "long-low-id\t100\t0\t100\t+\tt\t100\t0\t100\t10\t100\t60\n"
        "short-high-id\t100\t0\t20\t+\tt\t100\t0\t20\t20\t20\t60\n"
    )

    sorted_lines = Sorter(str(paf), "out")._sort_lines(lines)

    assert [line[0] for line in sorted_lines] == ["short-high-id", "long-low-id"]


def test_filter_filter_returns_false_without_filtered_contigs(tmp_path):
    from dgenies.bin.filter_contigs import Filter

    filtered = []
    filterer = Filter("input.fa", "input.idx", "query")
    filterer._check_filter = lambda: []
    filterer._filter_out = filtered.append

    assert filterer.filter() is False
    assert filtered == []


def test_filter_filter_removes_detected_contigs(tmp_path):
    from dgenies.bin.filter_contigs import Filter

    filtered = []
    filterer = Filter("input.fa", "input.idx", "query")
    filterer._check_filter = lambda: ["drop"]
    filterer._filter_out = lambda **kwargs: filtered.append(kwargs["f_outs"])

    assert filterer.filter() is True
    assert filtered == [["drop"]]


def test_filter_out_can_replace_original_fasta(tmp_path):
    from dgenies.bin.filter_contigs import Filter

    fasta = tmp_path / "input.fa"
    fasta.write_text(">keep\nAAAA\n>drop\nCCCC\n")

    Filter(str(fasta), "unused.idx", "query", replace_fa=True)._filter_out(["drop"])

    assert ">keep" in fasta.read_text()
    assert ">drop" not in fasta.read_text()


def test_filter_check_filter_marks_query_for_sort_when_small_contigs_dominate(tmp_path):
    from dgenies.bin.filter_contigs import Filter

    fasta = tmp_path / "query.fa"
    index = tmp_path / "query.idx"
    fasta.write_text(">big\nAAAA\n")
    index.write_text("Query\nbig\t10\n" + "".join(f"small{i}\t1\n" for i in range(100)))

    assert Filter(str(fasta), str(index), "query")._check_filter() == []
    assert (tmp_path / ".do-sort").exists()


def test_filter_check_filter_does_not_mark_target_for_sort(tmp_path):
    from dgenies.bin.filter_contigs import Filter

    fasta = tmp_path / "target.fa"
    index = tmp_path / "target.idx"
    fasta.write_text(">big\nAAAA\n")
    index.write_text("Target\nbig\t10\n" + "".join(f"small{i}\t1\n" for i in range(100)))

    assert Filter(str(fasta), str(index), "target")._check_filter() == []
    assert not (tmp_path / ".do-sort").exists()


def test_clean_jobs_fake_mode_keeps_old_upload_entries(tmp_path, monkeypatch):
    from dgenies.bin.clean_jobs import parse_upload_folders

    old_file = tmp_path / "old.txt"
    old_dir = tmp_path / "old-dir"
    old_file.write_text("old")
    old_dir.mkdir()
    monkeypatch.setattr("os.path.getctime", lambda path: 0.0)

    parse_upload_folders(str(tmp_path), now=100_000.0, max_age={"uploads": 0.01}, fake=True)

    assert old_file.exists()
    assert old_dir.exists()


def test_clean_jobs_parse_data_folders_removes_old_sorted_query_outputs(tmp_path, monkeypatch):
    from dgenies.bin.clean_jobs import parse_data_folders

    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    query = job_dir / "query.fa"
    sorted_query = job_dir / "query.fa.sorted"
    as_reference = job_dir / "as_reference_query.fa"
    query.write_text(">q\nA\n")
    sorted_query.write_text(">q\nA\n")
    as_reference.write_text(">q\nA\n")
    (job_dir / ".query").write_text(str(query))

    def fake_ctime(path):
        name = Path(path).name
        if name in {"query.fa.sorted", "as_reference_query.fa"}:
            return 0.0
        return 100_000.0

    monkeypatch.setattr("os.path.getctime", fake_ctime)

    parse_data_folders(
        str(tmp_path),
        gallery_jobs=[],
        now=100_000.0,
        max_age={"data": 999, "fasta_sorted": 0.01},
        fake=False,
    )

    assert query.exists()
    assert not sorted_query.exists()
    assert not as_reference.exists()


def test_clean_jobs_parse_database_keeps_gallery_and_deletes_old_jobs(tmp_path, monkeypatch):
    import dgenies.bin.clean_jobs as clean_jobs

    deleted = []

    class Expr:
        def __and__(self, other):
            return self

        def __or__(self, other):
            return self

    class ExprField:
        def __eq__(self, other):
            return Expr()

        def __ne__(self, other):
            return Expr()

        def __lt__(self, other):
            return Expr()

    class IdField:
        def __eq__(self, other):
            return ("id_job", other)

    class JobObj:
        def __init__(self, id_job):
            self.id_job = id_job

        def delete_instance(self):
            deleted.append(self.id_job)

    jobs = [JobObj("gallery-job"), JobObj("old-job")]
    (tmp_path / "gallery-job").mkdir()
    (tmp_path / "old-job").mkdir()

    class Query(list):
        def where(self, *args):
            return self

    class GalleryQuery:
        def join(self, model):
            return self

        def where(self, *args):
            return [object()] if args and args[0] == ("id_job", "gallery-job") else []

    class FakeJob:
        status = ExprField()
        date_created = ExprField()
        id_job = IdField()

        @classmethod
        def connect(cls):
            return nullcontext()

        @classmethod
        def select(cls):
            return Query(jobs)

    class FakeGallery:
        @classmethod
        def select(cls):
            return GalleryQuery()

    monkeypatch.setattr("dgenies.database.Job", FakeJob)
    monkeypatch.setattr("dgenies.database.Gallery", FakeGallery)

    gallery_jobs = clean_jobs.parse_database(str(tmp_path), {"data": 1, "error": 1}, fake=False)

    assert gallery_jobs == ["gallery-job"]
    assert (tmp_path / "gallery-job").exists()
    assert not (tmp_path / "old-job").exists()
    assert deleted == ["old-job"]


def _import_local_scheduler(monkeypatch):
    singleton_mod = types.ModuleType("tendo.singleton")
    singleton_mod.SingleInstance = lambda: object()
    tendo_mod = types.ModuleType("tendo")
    tendo_mod.singleton = singleton_mod
    monkeypatch.setitem(sys.modules, "tendo", tendo_mod)
    monkeypatch.setitem(sys.modules, "tendo.singleton", singleton_mod)
    sys.modules.pop("dgenies.bin.local_scheduler", None)
    return importlib.import_module("dgenies.bin.local_scheduler")


class _Expr:
    def __and__(self, other):
        return self

    def __or__(self, other):
        return self


class _Field:
    def __eq__(self, other):
        return _Expr()

    def __ne__(self, other):
        return _Expr()


class _Query(list):
    def where(self, *args):
        return self

    def order_by(self, *args):
        return self


def test_local_scheduler_marks_scheduled_cluster_jobs(monkeypatch):
    local_scheduler = _import_local_scheduler(monkeypatch)

    class FakeJob:
        def __init__(self, id_job, runner_type):
            self.id_job = id_job
            self.runner_type = runner_type
            self.status = "prepared"
            self.saved = False

        def save(self):
            self.saved = True

    jobs = [FakeJob("job-a", "slurm"), FakeJob("job-b", "sge")]

    class FakeJobModel:
        runner_type = _Field()
        status = _Field()
        date_created = _Field()

        @classmethod
        def connect(cls):
            return nullcontext()

        @classmethod
        def select(cls):
            return _Query(jobs)

    monkeypatch.setattr(local_scheduler, "Job", FakeJobModel)

    assert local_scheduler.Scheduler.get_scheduled_cluster_jobs() == [
        {"job_id": "job-a", "runner_type": "slurm"},
        {"job_id": "job-b", "runner_type": "sge"},
    ]
    assert [job.status for job in jobs] == ["scheduled", "scheduled"]
    assert all(job.saved for job in jobs)


def test_local_scheduler_start_align_updates_job_and_runs_manager(monkeypatch):
    local_scheduler = _import_local_scheduler(monkeypatch)
    calls = []
    job = types.SimpleNamespace(
        id_job="job1",
        email="user@example.org",
        tool="minimap2",
        options="repeat:many",
        status="prepared",
        save=lambda: calls.append("save"),
    )

    class FakeJobModel:
        id_job = _Field()

        @classmethod
        def connect(cls):
            return nullcontext()

        @classmethod
        def get(cls, *args):
            return job

    class FakeJobManager:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def set_inputs_from_res_dir(self):
            calls.append("set_inputs")

        def run_align_in_thread(self, runner_type):
            calls.append(("run_align", runner_type))

    monkeypatch.setattr(local_scheduler, "Job", FakeJobModel)
    monkeypatch.setattr(local_scheduler, "JobManager", FakeJobManager)

    local_scheduler.Scheduler().start_align("job1", runner_type="slurm")

    assert job.status == "starting"
    assert calls == [
        "save",
        ("init", {"id_job": "job1", "email": "user@example.org", "tool": "minimap2", "options": "repeat:many"}),
        "set_inputs",
        ("run_align", "slurm"),
    ]


def test_local_scheduler_prepare_job_updates_job_and_runs_preparation(monkeypatch):
    local_scheduler = _import_local_scheduler(monkeypatch)
    calls = []
    job = types.SimpleNamespace(
        id_job="job1",
        email="user@example.org",
        tool="minimap2",
        status="waiting",
        save=lambda: calls.append("save"),
    )

    class FakeJobModel:
        id_job = _Field()

        @classmethod
        def connect(cls):
            return nullcontext()

        @classmethod
        def get(cls, *args):
            return job

    class FakeJobManager:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def set_inputs_from_res_dir(self):
            calls.append("set_inputs")

        def prepare_job_in_thread(self):
            calls.append("prepare")

    monkeypatch.setattr(local_scheduler, "Job", FakeJobModel)
    monkeypatch.setattr(local_scheduler, "JobManager", FakeJobManager)

    local_scheduler.Scheduler().prepare_job("job1")

    assert job.status == "preparing"
    assert calls == [
        "save",
        ("init", {"id_job": "job1", "email": "user@example.org", "tool": "minimap2"}),
        "set_inputs",
        "prepare",
    ]


def test_local_scheduler_get_prep_scheduled_jobs(monkeypatch):
    local_scheduler = _import_local_scheduler(monkeypatch)
    jobs = [types.SimpleNamespace(id_job="job-a", runner_type="local"), types.SimpleNamespace(id_job="job-b", runner_type="slurm")]

    class FakeJobModel:
        status = _Field()
        date_created = _Field()

        @classmethod
        def connect(cls):
            return nullcontext()

        @classmethod
        def select(cls):
            return _Query(jobs)

    monkeypatch.setattr(local_scheduler, "Job", FakeJobModel)

    assert local_scheduler.Scheduler.get_prep_scheduled_jobs() == [("job-a", "local"), ("job-b", "slurm")]


def test_local_scheduler_update_batch_status_sets_failure_error_and_sends_mail(monkeypatch):
    local_scheduler = _import_local_scheduler(monkeypatch)
    calls = []

    class BatchJob:
        def __init__(self, id_job, refreshed):
            self.id_job = id_job
            self.refreshed = refreshed
            self.status = "started-batch"
            self.error = ""

        def save(self):
            calls.append(("save", self.id_job, self.status, self.error))

    jobs = [BatchJob("batch-fail", "fail"), BatchJob("batch-ok", "success")]

    class FakeJobModel:
        status = _Field()

        @classmethod
        def connect(cls):
            return nullcontext()

        @classmethod
        def select(cls):
            return _Query(jobs)

    class FakeJobManager:
        def __init__(self, id_job):
            self.id_job = id_job

        def refresh_batch_status(self):
            return next(job.refreshed for job in jobs if job.id_job == self.id_job)

        def send_mail_post_if_allowed(self):
            calls.append(("mail", self.id_job))

    monkeypatch.setattr(local_scheduler, "Job", FakeJobModel)
    monkeypatch.setattr(local_scheduler, "JobManager", FakeJobManager)

    local_scheduler.Scheduler().update_batch_status()

    assert ("save", "batch-fail", "fail", "<p>At least one of your jobs has failed.</p>") in calls
    assert ("save", "batch-ok", "success", "") in calls
    assert ("mail", "batch-fail") in calls
    assert ("mail", "batch-ok") in calls


def test_local_scheduler_move_job_to_cluster_uses_config_runner_type(monkeypatch):
    local_scheduler = _import_local_scheduler(monkeypatch)
    job = types.SimpleNamespace(id_job="job1", runner_type="local", saved=False)
    job.save = lambda: setattr(job, "saved", True)

    class FakeJobModel:
        id_job = _Field()

        @classmethod
        def connect(cls):
            return nullcontext()

        @classmethod
        def get(cls, *args):
            return job

    monkeypatch.setattr(local_scheduler, "Job", FakeJobModel)
    monkeypatch.setattr(local_scheduler, "config_reader", types.SimpleNamespace(runner_type="slurm"))

    local_scheduler.Scheduler.move_job_to_cluster("job1")

    assert job.runner_type == "slurm"
    assert job.saved is True


def test_local_scheduler_cleaner_exits_drmaa_session(monkeypatch):
    local_scheduler = _import_local_scheduler(monkeypatch)
    exited = []
    monkeypatch.setattr(local_scheduler, "DRMAA_SESSION", types.SimpleNamespace(exit=lambda: exited.append(True)))

    local_scheduler.cleaner()

    assert exited == [True]


def test_local_scheduler_parse_uploads_transitions_sessions(monkeypatch):
    local_scheduler = _import_local_scheduler(monkeypatch)
    now = datetime.now()
    deleted = []
    saved = []

    class SessionObj:
        def __init__(self, s_id, status, seconds_old, keep_active=False):
            self.s_id = s_id
            self.status = status
            self.last_ping = now - timedelta(seconds=seconds_old)
            self.date_created = now
            self.keep_active = keep_active

        def save(self):
            saved.append((self.s_id, self.status))

        def delete_instance(self):
            deleted.append(self.s_id)

    active_old = SessionObj("active-old", "active", 99)
    pending_old = SessionObj("pending-old", "pending", 99)
    pending_new = SessionObj("pending-new", "pending", 1)
    expired = SessionObj("expired", "reset", 999)
    sessions = [active_old, pending_old, pending_new, expired]

    class StatusField:
        def __eq__(self, other):
            return ("status", other)

    class FilteringQuery(list):
        def where(self, *args):
            status_filters = [value for field, value in args if field == "status"]
            if status_filters:
                return FilteringQuery([session for session in self if session.status in status_filters])
            return self

        def order_by(self, *args):
            return self

    class FakeSessionModel:
        status = StatusField()
        date_created = object()

        @classmethod
        def connect(cls):
            return nullcontext()

        @classmethod
        def select(cls):
            return FilteringQuery(sessions)

    monkeypatch.setattr(local_scheduler, "Session", FakeSessionModel)
    monkeypatch.setattr(
        local_scheduler,
        "config_reader",
        types.SimpleNamespace(
            delete_allowed_session_delay=10,
            reset_pending_session_delay=10,
            max_concurrent_dl=1,
            delete_session_delay=100,
        ),
    )

    local_scheduler.Scheduler().parse_uploads_asks()

    assert "active-old" in deleted
    assert "expired" in deleted
    assert ("pending-old", "reset") in saved
    assert ("pending-new", "active") in saved
