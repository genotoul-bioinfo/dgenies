import importlib
import runpy
import sys
import types
from contextlib import nullcontext
from pathlib import Path


def test_index_save_load_and_fasta_index(tmp_path):
    from dgenies.bin.index import Index, index_file

    idx = tmp_path / "sample.idx"
    Index.save(
        str(idx),
        "Sample",
        {"ctgA": 4, "ctgB": 6},
        ["ctgA", "ctgB"],
        {"ctgA": False, "ctgB": True},
    )

    name, order, contigs, reversed_c, abs_start, total = Index.load(str(idx))
    assert name == "Sample"
    assert order == ["ctgA", "ctgB"]
    assert contigs == {"ctgA": 4, "ctgB": 6}
    assert reversed_c == {"ctgA": False, "ctgB": True}
    assert abs_start == {"ctgA": 0, "ctgB": 4}
    assert total == 10

    fasta = tmp_path / "query.fa"
    fasta.write_text(">q1 comment\nACGT\nAC\n>q2\nNNNN\n")
    out = tmp_path / "query.idx"
    assert index_file(str(fasta), "Query", str(out)) == (True, 2, "")
    assert out.read_text().splitlines() == ["Query", "q1\t6", "q2\t4"]


def test_index_load_can_merge_split_contigs(tmp_path):
    from dgenies.bin.index import Index

    idx = tmp_path / "split.idx"
    idx.write_text("Query\nctg_###_1\t3\nctg_###_2\t5\nother\t7\n")

    name, order, contigs, reversed_c, abs_start, total = Index.load(str(idx), merge_splits=True)

    assert name == "Query"
    assert order == ["ctg", "other"]
    assert contigs == {"ctg": 8, "other": 7}
    assert reversed_c == {"ctg": False, "other": False}
    assert abs_start == {"ctg": 0, "other": 8}
    assert total == 15


def test_splitter_splits_large_contigs_and_writes_index(tmp_path):
    from dgenies.bin.split_fa import Splitter

    assert list(Splitter.split_contig("ctg", "ABCDEFGHIJK", 5).keys()) == [
        "ctg_###_1",
        "ctg_###_2",
        "ctg_###_3",
    ]

    source = tmp_path / "query.fa"
    source.write_text(">ctg\nACGTACGTACGT\n")
    output = tmp_path / "query.split.fa"
    splitter = Splitter(str(source), "Query", str(output), size_c=5)

    assert splitter.split() == (True, "")
    assert ">ctg_###_1" in output.read_text()
    assert (tmp_path / "query_split.idx").read_text().splitlines() == [
        "Query",
        "ctg_###_1\t5",
        "ctg_###_2\t5",
        "ctg_###_3\t2",
    ]


def test_merger_combines_split_index_and_offsets_paf(tmp_path):
    from dgenies.bin.merge_splitted_chrms import Merger

    idx = tmp_path / "query_split.idx"
    idx.write_text("Query\nctg_###_2\t5\nctg_###_1\t3\nplain\t7\n")
    merger = Merger("in.paf", "out.paf", str(idx), "merged.idx")
    contigs, splits, q_name = merger.load_query_index(str(idx))

    assert q_name == "Query"
    assert contigs == {"ctg": 8, "plain": 7}
    assert list(splits["ctg"].items()) == [("1", 0), ("2", 3)]

    paf_in = tmp_path / "map.paf"
    paf_out = tmp_path / "merged.paf"
    paf_in.write_text("ctg_###_2\t5\t1\t4\t+\ttgt\t20\t2\t5\t3\t3\t60\nplain\t7\t0\t3\t+\ttgt\t20\t0\t3\t3\t3\t60\n")
    Merger.merge_paf(str(paf_in), str(paf_out), contigs, splits)

    assert paf_out.read_text().splitlines()[0].split("\t")[:4] == ["ctg", "8", "4", "7"]


def test_sorter_orders_paf_by_weighted_match_length(tmp_path):
    from dgenies.bin.sort_paf import Sorter

    paf = tmp_path / "map.paf"
    out = tmp_path / "sorted.paf"
    short = "q1\t100\t0\t10\t+\tt1\t100\t0\t10\t10\t10\t60"
    long = "q2\t100\t0\t40\t+\tt1\t100\t0\t40\t40\t40\t60"
    paf.write_text(short + "\n" + long + "\n")

    Sorter(str(paf), str(out)).sort()

    assert out.read_text().splitlines()[0].startswith("q2\t")


def test_filter_out_removes_contigs_from_fasta(tmp_path):
    from dgenies.bin.filter_contigs import Filter

    fasta = tmp_path / "input.fa"
    fasta.write_text(">keep\nAAAA\n>drop\nCCCC\n")
    out = tmp_path / "filtered.fa"

    Filter(str(fasta), "unused.idx", "query", out_fasta=str(out))._filter_out(["drop"])

    assert ">keep" in out.read_text()
    assert ">drop" not in out.read_text()


def test_clean_jobs_removes_only_old_upload_entries(tmp_path, monkeypatch):
    from dgenies.bin.clean_jobs import parse_upload_folders

    old_file = tmp_path / "old.txt"
    new_file = tmp_path / "new.txt"
    old_dir = tmp_path / "old-dir"
    old_file.write_text("old")
    new_file.write_text("new")
    old_dir.mkdir()

    now = 10_000.0

    def fake_ctime(path):
        return 0.0 if Path(path).name.startswith("old") else now

    monkeypatch.setattr("os.path.getctime", fake_ctime)
    parse_upload_folders(str(tmp_path), now, {"uploads": 0.01})

    assert not old_file.exists()
    assert not old_dir.exists()
    assert new_file.exists()


def test_local_scheduler_marks_scheduled_local_jobs(monkeypatch):
    singleton_mod = types.ModuleType("tendo.singleton")
    singleton_mod.SingleInstance = lambda: object()
    tendo_mod = types.ModuleType("tendo")
    tendo_mod.singleton = singleton_mod
    monkeypatch.setitem(sys.modules, "tendo", tendo_mod)
    monkeypatch.setitem(sys.modules, "tendo.singleton", singleton_mod)
    sys.modules.pop("dgenies.bin.local_scheduler", None)

    local_scheduler = importlib.import_module("dgenies.bin.local_scheduler")

    class Expr:
        def __and__(self, other):
            return self

        def __or__(self, other):
            return self

    class Field:
        def __eq__(self, other):
            return Expr()

        def __ne__(self, other):
            return Expr()

    class Query(list):
        def where(self, *args):
            return self

        def order_by(self, *args):
            return self

    class FakeJob:
        def __init__(self, id_job):
            self.id_job = id_job
            self.status = "prepared"
            self.saved = False

        def save(self):
            self.saved = True

    jobs = [FakeJob("job-a"), FakeJob("job-b")]

    class FakeJobModel:
        runner_type = Field()
        status = Field()
        date_created = Field()

        @classmethod
        def connect(cls):
            return nullcontext()

        @classmethod
        def select(cls):
            return Query(jobs)

    monkeypatch.setattr(local_scheduler, "Job", FakeJobModel)

    assert local_scheduler.Scheduler.get_scheduled_local_jobs() == ["job-a", "job-b"]
    assert [job.status for job in jobs] == ["scheduled", "scheduled"]
    assert all(job.saved for job in jobs)


def test_all_prepare_script_indexes_target_when_index_only(tmp_path, monkeypatch, package_dir):
    monkeypatch.syspath_prepend(str(package_dir / "bin"))
    target = tmp_path / "target.fa"
    target.write_text(">t1\nAAAA\n")
    preptime = tmp_path / "prep_times"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "all_prepare.py",
            "-t",
            str(target),
            "-m",
            "Target",
            "-p",
            str(preptime),
            "--index-only",
            "True",
        ],
    )

    runpy.run_path(str(package_dir / "bin" / "all_prepare.py"), run_name="__main__")

    assert (tmp_path / "target.idx").read_text().splitlines() == ["Target", "t1\t4"]
    assert len(preptime.read_text().splitlines()) == 2


def test_minimap_to_json_script_invokes_preparation_and_save_json(tmp_path, monkeypatch, package_dir):
    calls = {}
    parse_paf = types.ModuleType("lib.parse_paf")

    def save_json(paf_out, idx1, idx2, output):
        calls["save_json"] = (Path(paf_out).name, Path(idx1).name, Path(idx2).name)
        Path(output).write_text("json")

    parse_paf.save_json = save_json
    lib_mod = types.ModuleType("lib")
    lib_mod.__path__ = []
    prepare_paf = types.ModuleType("prepare_paf")
    prepare_paf.init = lambda *args: calls.setdefault("prepare", args)

    monkeypatch.setitem(sys.modules, "lib", lib_mod)
    monkeypatch.setitem(sys.modules, "lib.parse_paf", parse_paf)
    monkeypatch.setitem(sys.modules, "prepare_paf", prepare_paf)
    output = tmp_path / "out.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "minimap_to_json.py",
            "-i",
            "input.paf",
            "-q",
            "query.fa",
            "-t",
            "target.fa",
            "-o",
            str(output),
        ],
    )

    runpy.run_path(str(package_dir / "bin" / "minimap_to_json.py"), run_name="__main__")

    assert calls["prepare"][0] == "input.paf"
    assert calls["save_json"] == ("map.paf", "query.idx", "target.idx")
    assert output.read_text() == "json"
