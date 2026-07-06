import json
from pathlib import Path

import pytest


def write_fasta(path, records):
    with open(path, "w") as handle:
        for name, sequence in records:
            handle.write(f">{name}\n{sequence}\n")


def build_small_paf_runtime(tmp_path):
    from dgenies.bin.index import index_file

    job_dir = tmp_path / "job"
    job_dir.mkdir()
    query_fasta = job_dir / "query.fa"
    target_fasta = job_dir / "target.fa"
    write_fasta(query_fasta, [("q1", "AAAAA"), ("q2", "AACCC"), ("q3", "TTTT")])
    write_fasta(target_fasta, [("t1", "GGGTT"), ("t2", "AAAAA")])

    query_idx = job_dir / "query.idx"
    target_idx = job_dir / "target.idx"
    assert index_file(str(query_fasta), "Query", str(query_idx))[0]
    assert index_file(str(target_fasta), "Target", str(target_idx))[0]

    paf_file = job_dir / "map.paf"
    paf_file.write_text(
        "q1\t5\t0\t5\t+\tt2\t5\t0\t5\t5\t5\t60\n"
        "q2\t5\t0\t5\t-\tt1\t5\t0\t5\t5\t5\t60\n"
    )
    (job_dir / ".query").write_text(str(query_fasta))
    return job_dir, query_fasta, paf_file, query_idx, target_idx


def test_parse_index_merges_runs_of_five_small_contigs(tmp_path):
    from dgenies.lib.paf import Paf

    paf = Paf(str(tmp_path / "map.paf"), str(tmp_path / "q.idx"), str(tmp_path / "t.idx"), auto_parse=False)

    contigs, order = paf.parse_index([f"ctg{i}" for i in range(5)], {f"ctg{i}": 1 for i in range(5)}, 1000)

    assert order == ["###MIX###_ctg0###ctg1###ctg2###ctg3###ctg4"]
    assert contigs[order[0]] == 5


def test_parse_index_keeps_short_runs_unmerged(tmp_path):
    from dgenies.lib.paf import Paf

    paf = Paf(str(tmp_path / "map.paf"), str(tmp_path / "q.idx"), str(tmp_path / "t.idx"), auto_parse=False)
    order = ["small1", "small2", "large"]
    contigs = {"small1": 1, "small2": 1, "large": 100}

    parsed_contigs, parsed_order = paf.parse_index(order, contigs, 1000)

    assert parsed_order == order
    assert parsed_contigs == contigs


def test_keyerror_message_adds_inverted_query_hint_when_align_marker_exists(tmp_path):
    from dgenies.lib.paf import Paf

    paf_file = tmp_path / "map.paf"
    paf_file.write_text("")
    (tmp_path / ".align").write_text("")
    paf = Paf(str(paf_file), str(tmp_path / "q.idx"), str(tmp_path / "t.idx"), auto_parse=False)

    assert "May be you invert query and target files?" in paf.keyerror_message(KeyError("ctg"), "target")


def test_parse_paf_reports_missing_query_index(tmp_path):
    from dgenies.lib.paf import Paf

    paf = Paf(str(tmp_path / "map.paf"), str(tmp_path / "missing.idx"), str(tmp_path / "target.idx"), auto_parse=False)

    assert paf.parse_paf() is False
    assert paf.error == "Index file does not exist for query!"


def test_parse_paf_reports_missing_target_index(tmp_path):
    from dgenies.lib.paf import Paf

    paf_file = tmp_path / "map.paf"
    query_idx = tmp_path / "query.idx"
    paf_file.write_text("")
    query_idx.write_text("Query\nq1\t10\n")
    paf = Paf(str(paf_file), str(query_idx), str(tmp_path / "missing-target.idx"), auto_parse=False)

    assert paf.parse_paf() is False
    assert paf.error == "Index file does not exist for target!"


def test_parse_paf_reports_missing_paf_file(tmp_path):
    from dgenies.lib.paf import Paf

    query_idx = tmp_path / "query.idx"
    target_idx = tmp_path / "target.idx"
    query_idx.write_text("Query\nq1\t10\n")
    target_idx.write_text("Target\nt1\t10\n")
    paf = Paf(str(tmp_path / "missing.paf"), str(query_idx), str(target_idx), auto_parse=False)

    assert paf.parse_paf() is False
    assert paf.error == "PAF file does not exist!"


def test_parse_paf_reports_unknown_query_contig(tmp_path):
    from dgenies.lib.paf import Paf

    paf_file = tmp_path / "map.paf"
    query_idx = tmp_path / "query.idx"
    target_idx = tmp_path / "target.idx"
    paf_file.write_text("q1\t10\t0\t10\t+\tt1\t10\t0\t10\t10\t10\t60\n")
    query_idx.write_text("Query\nmissing\t10\n")
    target_idx.write_text("Target\nt1\t10\n")
    paf = Paf(str(paf_file), str(query_idx), str(target_idx), auto_parse=False)

    assert paf.parse_paf() is False
    assert paf.error == "Invalid contig for query: q1"


def test_parse_paf_assigns_identity_categories(tmp_path):
    from dgenies.lib.paf import Paf

    query_idx = tmp_path / "query.idx"
    target_idx = tmp_path / "target.idx"
    paf_file = tmp_path / "map.paf"
    query_idx.write_text("Query\nq0\t10\nq1\t10\nq2\t10\nq3\t10\n")
    target_idx.write_text("Target\nt0\t10\nt1\t10\nt2\t10\nt3\t10\n")
    paf_file.write_text(
        "q0\t10\t0\t10\t+\tt0\t10\t0\t10\t1\t10\t255\n"
        "q1\t10\t0\t10\t+\tt1\t10\t0\t10\t4\t10\t255\n"
        "q2\t10\t0\t10\t+\tt2\t10\t0\t10\t6\t10\t255\n"
        "q3\t10\t0\t10\t+\tt3\t10\t0\t10\t9\t10\t255\n"
    )

    paf = Paf(str(paf_file), str(query_idx), str(target_idx), auto_parse=False)
    paf.parse_paf(merge_index=False)

    assert [len(paf.lines[str(cls)]) for cls in range(4)] == [1, 1, 1, 1]


def test_parse_paf_marks_sampled_when_line_limit_is_exceeded(tmp_path):
    from dgenies.lib.paf import Paf

    _, _, paf_file, query_idx, target_idx = build_small_paf_runtime(tmp_path)
    paf = Paf(str(paf_file), str(query_idx), str(target_idx), auto_parse=False)
    paf.max_nb_lines = 0

    paf.parse_paf()

    assert paf.parsed is True
    assert paf.sampled is True
    assert paf.lines == {"0": [], "1": [], "2": [], "3": []}


def test_get_dotplot_data_sorts_when_requested_state_differs(tmp_path, monkeypatch):
    from dgenies.lib.paf import Paf

    paf = Paf(str(tmp_path / "map.paf"), str(tmp_path / "q.idx"), str(tmp_path / "t.idx"), auto_parse=False)
    calls = []

    def fake_sort():
        calls.append("sort")
        paf.sorted = True

    monkeypatch.setattr(paf, "sort", fake_sort)
    monkeypatch.setattr(paf, "get_d3js_data", lambda: {"sorted": paf.sorted})

    assert paf.get_dotplot_data(sorted=True) == {"sorted": True}
    assert calls == ["sort"]


def test_save_json_writes_d3_payload(tmp_path, monkeypatch):
    from dgenies.lib.paf import Paf

    paf = Paf(str(tmp_path / "map.paf"), str(tmp_path / "q.idx"), str(tmp_path / "t.idx"), auto_parse=False)
    monkeypatch.setattr(paf, "get_d3js_data", lambda: {"lines": {"3": [[0, 1, 0, 1, 1.0, "q", "t"]]}})

    out = tmp_path / "dotplot.json"
    paf.save_json(str(out))

    assert json.loads(out.read_text())["lines"]["3"][0][5:] == ["q", "t"]


def test_is_contig_well_oriented_accepts_increasing_target_medians(tmp_path):
    from dgenies.lib.paf import Paf

    paf = Paf(str(tmp_path / "map.paf"), str(tmp_path / "q.idx"), str(tmp_path / "t.idx"), auto_parse=False)
    paf.q_contigs = {"q1": 100}
    paf.t_contigs = {"t1": 100}

    assert paf.is_contig_well_oriented(
        [[10, 100, 10, 0, 10, 0, 10, 10], [30, 100, 30, 10, 20, 10, 20, 10]],
        "q1",
        "t1",
    )


def test_is_contig_well_oriented_rejects_decreasing_target_medians(tmp_path):
    from dgenies.lib.paf import Paf

    paf = Paf(str(tmp_path / "map.paf"), str(tmp_path / "q.idx"), str(tmp_path / "t.idx"), auto_parse=False)
    paf.q_contigs = {"q1": 100}
    paf.t_contigs = {"t1": 100}

    assert not paf.is_contig_well_oriented(
        [[10, 100, 30, 0, 10, 0, 10, 10], [30, 100, 10, 10, 20, 10, 20, 10]],
        "q1",
        "t1",
    )


def test_sort_creates_sorted_paf_index_and_marker(tmp_path):
    from dgenies.lib.paf import Paf

    job_dir, _, paf_file, query_idx, target_idx = build_small_paf_runtime(tmp_path)
    paf = Paf(str(paf_file), str(query_idx), str(target_idx))

    paf.sort()

    assert paf.sorted is True
    assert (job_dir / ".sorted").exists()
    assert (job_dir / "map.paf.sorted").exists()
    assert (job_dir / "query.idx.sorted").exists()


def test_build_query_chr_as_reference_requires_sorted_paf(tmp_path, monkeypatch):
    import dgenies.lib.paf as paf_module

    _, _, paf_file, query_idx, target_idx = build_small_paf_runtime(tmp_path)
    monkeypatch.setattr(paf_module, "MODE", "standalone", raising=False)
    paf = paf_module.Paf(str(paf_file), str(query_idx), str(target_idx))

    assert paf.build_query_chr_as_reference(compress=False) == "_._"


def test_build_summary_stats_moves_status_to_fail_when_unparsed(tmp_path, monkeypatch):
    from dgenies.lib.paf import Paf

    paf = Paf(str(tmp_path / "map.paf"), str(tmp_path / "q.idx"), str(tmp_path / "t.idx"), auto_parse=False)
    monkeypatch.setattr(paf, "parse_paf", lambda *args, **kwargs: None)
    paf.parsed = False
    status = tmp_path / ".summary"
    status.write_text("running")

    assert paf.build_summary_stats(str(status)) is None
    assert not status.exists()
    assert (tmp_path / ".summary.fail").exists()
