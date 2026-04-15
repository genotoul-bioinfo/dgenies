"""PAF parsing and transformation tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

# This file was split out from src/dgenies/test_dgenies_api.py.


def test_paf_parse_index_and_flush_blocks(tmp_path):
    """Validate parsing and block merging in the Paf class.

    The Paf.parse_index method merges sequences of small contigs into a single
    "mix" block when at least five sequential contigs represent less than 0.2%
    of the overall length.  It leaves smaller runs unmerged.  This test
    constructs artificial index orders and contig definitions and verifies
    that merges occur only when expected and that the resulting index
    definitions and orders reflect the correct totals.
    """
    from dgenies.lib.paf import Paf

    # Prepare dummy file paths; the actual files need not exist because
    # parse_index does not access them.
    dummy_paf = tmp_path / "dummy.paf"
    dummy_idx_q = tmp_path / "q.idx"
    dummy_idx_t = tmp_path / "t.idx"
    p = Paf(str(dummy_paf), str(dummy_idx_q), str(dummy_idx_t), auto_parse=False)

    # Case 1: five very small contigs should be merged into a single block
    index_c = {f"ctg{i}": 1 for i in range(5)}
    index_o = list(index_c.keys())
    new_c, new_o = p.parse_index(index_o, index_c, 1000)
    # Only one entry should remain, named with the ###MIX### prefix, whose
    # length equals the sum of the original lengths.
    assert len(new_c) == 1, f"Expected 1 merged block, got {len(new_c)}"
    mix_name = new_o[0]
    assert mix_name.startswith("###MIX###"), f"Unexpected merged name: {mix_name}"
    assert new_c[mix_name] == sum(index_c.values())

    # Case 2: fewer than five small contigs should not be merged; large
    # contigs (>=0.2% of total length) are kept separate.
    index_c2 = {"small1": 1, "small2": 1, "small3": 1, "large": 100}
    index_o2 = ["small1", "small2", "small3", "large"]
    new_c2, new_o2 = p.parse_index(index_o2, index_c2, 1000)
    # All original names should remain in the order with no mixing
    assert set(new_o2) == set(index_o2)
    for name in index_o2:
        assert name in new_c2 and new_c2[name] == index_c2[name]


def test_paf_remove_noise_and_keyerror_message(tmp_path):
    """Test removal of short dot‑plot lines and building of KeyError messages.

    The remove_noise function filters out lines whose Euclidean length is
    below a supplied threshold.  The keyerror_message method appends a hint
    when a dotfile indicating alignment existence is present in the data
    directory.  Both behaviours are validated here using simple inputs.
    """
    from dgenies.lib.paf import Paf

    # Construct a set of lines with one long and one short entry
    lines = {
        "0": [[0, 10, 0, 10, 0.5, "c", "t"], [0, 1, 0, 1, 0.5, "c", "t"]],
        "1": [],
        "2": [],
        "3": [],
    }
    # Applying a noise limit of 5 should keep only the long line (length ~14.14)
    kept = Paf.remove_noise(lines, 5)
    assert kept["0"] == [lines["0"][0]]
    for cls in ["1", "2", "3"]:
        assert kept[cls] == []

    # Test keyerror_message without an .align marker
    paf_path = tmp_path / "fake.paf"
    paf_path.write_text("")
    idx_q = tmp_path / "q.idx"
    idx_q.write_text("")
    idx_t = tmp_path / "t.idx"
    idx_t.write_text("")
    p = Paf(str(paf_path), str(idx_q), str(idx_t), auto_parse=False)
    msg = p.keyerror_message(KeyError("missing"), "query")
    assert msg == "Invalid contig for query: missing"
    # With .align present in the data directory the hint should be appended
    align_marker = paf_path.parent / ".align"
    align_marker.touch()
    msg_hint = p.keyerror_message(KeyError("ctg"), "target")
    assert "invert query and target" in msg_hint


def test_paf_set_sorted_and_gravity_contigs_and_d3js(tmp_path):
    """Verify sorted status toggling, gravity computation and d3js data assembly.

    The set_sorted method should create and remove the .sorted marker file
    and update the internal flag accordingly.  compute_gravity_contigs must
    accumulate squared match lengths per contig/chromosome and return detailed
    line summaries.  get_d3js_data bundles internal properties into a dict.
    """
    from math import pow, sqrt

    import pytest

    from dgenies.lib.paf import Paf

    # Prepare dummy files
    paf_file = tmp_path / "map.paf"
    paf_file.write_text("")
    q_idx = tmp_path / "query.idx"
    q_idx.write_text("")
    t_idx = tmp_path / "target.idx"
    t_idx.write_text("")
    p = Paf(str(paf_file), str(q_idx), str(t_idx), auto_parse=False)

    # set_sorted should touch and remove the .sorted file
    p.set_sorted(True)
    sorted_marker = paf_file.parent / ".sorted"
    assert p.sorted is True and sorted_marker.exists()
    p.set_sorted(False)
    assert p.sorted is False and not sorted_marker.exists()

    # Populate lines for gravity computation: three matches across two contigs
    # c1 on t1: diagonal of length sqrt((10-0)^2+(10-0)^2) ≈14.142, len_m_2≈(1+14.142)^2
    # c1 on t2: horizontal line (5 units), len_m_2=(1+5)^2
    # c2 on t1: diagonal of length sqrt((6-2)^2+(6-2)^2)=5.657, len_m_2≈(1+5.657)^2
    p.lines = {
        "0": [
            [0, 10, 0, 10, 0.9, "c1", "t1"],
            [0, 5, 0, 0, 0.7, "c1", "t2"],
            [2, 6, 2, 6, 0.8, "c2", "t1"],
        ]
    }
    gravity, lines_on_block = p.compute_gravity_contigs()
    # Compute expected squared lengths
    len_c1_t1 = pow(1 + sqrt(pow(10 - 0, 2) + pow(10 - 0, 2)), 2)
    len_c1_t2 = pow(1 + sqrt(pow(5 - 0, 2) + pow(0 - 0, 2)), 2)
    len_c2_t1 = pow(1 + sqrt(pow(6 - 2, 2) + pow(6 - 2, 2)), 2)
    assert pytest.approx(gravity["c1"]["t1"]) == len_c1_t1
    assert pytest.approx(gravity["c1"]["t2"]) == len_c1_t2
    assert pytest.approx(gravity["c2"]["t1"]) == len_c2_t1
    # Each block should hold exactly one entry
    assert len(lines_on_block[("c1", "t1")]) == 1
    assert len(lines_on_block[("c1", "t2")]) == 1
    assert len(lines_on_block[("c2", "t1")]) == 1

    # Populate remaining attributes and test get_d3js_data
    p.len_q = 100
    p.len_t = 200
    p.min_idy = 0.5
    p.max_idy = 0.9
    p.q_contigs = {"c1": 50, "c2": 25}
    p.q_order = ["c1", "c2"]
    p.t_contigs = {"t1": 120, "t2": 80}
    p.t_order = ["t1", "t2"]
    p.name_q = "Query"
    p.name_t = "Target"
    d3_data = p.get_d3js_data()
    assert d3_data["y_len"] == 100
    assert d3_data["x_len"] == 200
    assert d3_data["min_idy"] == 0.5
    assert d3_data["max_idy"] == 0.9
    assert d3_data["lines"] == p.lines
    assert d3_data["y_contigs"] == p.q_contigs
    assert d3_data["y_order"] == p.q_order
    assert d3_data["x_contigs"] == p.t_contigs
    assert d3_data["x_order"] == p.t_order
    assert d3_data["name_y"] == "Query"
    assert d3_data["name_x"] == "Target"


def _write_fasta(path: Path, records: list[tuple[str, str]]) -> None:
    with open(path, "w") as fasta_out:
        for name, sequence in records:
            fasta_out.write(f">{name}\n{sequence}\n")


def _build_small_paf_runtime(tmp_path: Path):
    from dgenies.bin.index import index_file

    job_dir = tmp_path / "job"
    job_dir.mkdir()
    query_fasta = job_dir / "query.fa"
    target_fasta = job_dir / "target.fa"
    _write_fasta(query_fasta, [("q1", "AAAAA"), ("q2", "AACCC"), ("q3", "TTTT")])
    _write_fasta(target_fasta, [("t1", "GGGTT"), ("t2", "AAAAA")])

    query_idx = job_dir / "query.idx"
    target_idx = job_dir / "target.idx"
    ok_q, _, message_q = index_file(str(query_fasta), "Query", str(query_idx))
    ok_t, _, message_t = index_file(str(target_fasta), "Target", str(target_idx))
    assert ok_q, message_q
    assert ok_t, message_t

    paf_file = job_dir / "map.paf"
    paf_file.write_text(
        "q1\t5\t0\t5\t+\tt2\t5\t0\t5\t5\t5\t60\nq2\t5\t0\t5\t-\tt1\t5\t0\t5\t5\t5\t60\n"
    )
    (job_dir / ".query").write_text(str(query_fasta))
    return job_dir, query_fasta, target_fasta, paf_file, query_idx, target_idx


def test_paf_end_to_end_sort_association_and_query_as_reference(tmp_path):
    from dgenies.lib.paf import Paf

    job_dir, query_fasta, _, paf_file, query_idx, target_idx = _build_small_paf_runtime(
        tmp_path
    )

    paf = Paf(str(paf_file), str(query_idx), str(target_idx))
    assert paf.parsed is True
    assert paf.q_order == ["q1", "q2", "q3"]
    assert paf.t_order == ["t1", "t2"]
    assert paf.get_queries_on_target_association() == {"t2": ["q1"], "t1": ["q2"]}

    paf.sort()
    assert paf.sorted is True
    assert (job_dir / ".sorted").exists()
    assert (job_dir / "map.paf.sorted").exists()
    assert (job_dir / "query.idx.sorted").exists()
    assert paf.q_order == ["q2", "q1", "q3"]
    assert paf.q_reversed["q2"] is True

    records = list(paf.build_query_on_target_association_records())
    assert records[0][0:3] == ("q2", "t1", "-")
    assert records[1][0:3] == ("q1", "t2", "+")
    assert records[2][0:3] == ("q3", None, "+")
    assert paf.build_list_no_assoc("query") == {"q3"}
    assert paf.build_list_no_assoc("target") == set()

    assoc_file = paf.build_query_on_target_association_file()
    assert "q2\tt1\t-" in assoc_file
    assert "q3\tNone\t+" in assoc_file

    output_path = paf.build_query_chr_as_reference(compress=False)
    assert Path(output_path).exists()
    output_text = Path(output_path).read_text()
    assert ">t1" in output_text
    assert ">t2" in output_text
    assert ">q3_unaligned" in output_text
    assert "GGGTT" in output_text  # q2 reverse complement

    paf.reverse_contig("q1")
    assert paf.sorted is True
    assert paf.q_reversed["q1"] is True
    assert paf.q_order[0] == "q2"
    assert paf.q_order[1] == "q1"


def test_paf_build_query_as_reference_with_gz_input_and_webserver_mail(
    monkeypatch, tmp_path
):
    import dgenies.lib.paf as paf_module
    from dgenies.lib.functions import Functions

    job_dir, query_fasta, _, paf_file, query_idx, target_idx = _build_small_paf_runtime(
        tmp_path
    )
    gz_query = Functions.compress(str(query_fasta), overwrite=True, remove=True)
    assert gz_query is not None and Path(gz_query).exists()
    (job_dir / ".query").write_text(gz_query)

    mail_calls = []
    monkeypatch.setattr(paf_module, "MODE", "webserver", raising=False)
    monkeypatch.setattr(
        paf_module.Functions,
        "send_fasta_ready",
        staticmethod(lambda **kwargs: mail_calls.append(kwargs)),
        raising=False,
    )

    paf = paf_module.Paf(
        str(paf_file),
        str(query_idx),
        str(target_idx),
        mailer=object(),
        id_job="job-mail",
    )
    paf.sort()
    output_path = paf.build_query_chr_as_reference(compress=True)

    assert output_path.endswith(".gz")
    assert Path(output_path).exists()
    assert mail_calls[0]["job_name"] == "job-mail"
    assert mail_calls[0]["compressed"] is True
    assert mail_calls[0]["status"] == "success"


def test_paf_summary_stats_remove_overlaps(monkeypatch, tmp_path):
    from dgenies.lib.paf import Paf

    job_dir = tmp_path / "summary"
    job_dir.mkdir()
    paf = Paf(
        str(job_dir / "map.paf"),
        str(job_dir / "query.idx"),
        str(job_dir / "target.idx"),
        auto_parse=False,
    )
    paf.parsed = True
    paf.len_t = 10
    paf.lines = {
        "0": [],
        "1": [[0, 4, 0, 4, 0.4, "q1", "t1"]],
        "2": [],
        "3": [[2, 6, 2, 6, 0.9, "q2", "t1"]],
    }
    monkeypatch.setattr(paf, "parse_paf", lambda *_args, **_kwargs: None, raising=False)

    status_file = job_dir / ".summary.status"
    status_file.write_text("building")
    percents = paf.build_summary_stats(str(status_file))

    assert percents == {"-1": 30.0, "0": 0.0, "1": 20.0, "2": 0.0, "3": 50.0}
    assert not status_file.exists()
    assert json.loads((job_dir / "map.paf.summary").read_text()) == percents
    assert paf.get_summary_stats() == percents


def test_paf_error_branches_for_missing_inputs_and_failed_reference_build(tmp_path):
    from dgenies.lib.paf import Paf

    missing = Paf(
        str(tmp_path / "missing.paf"),
        str(tmp_path / "query.idx"),
        str(tmp_path / "target.idx"),
        auto_parse=False,
    )
    assert missing.parse_paf() is False
    assert missing.error == "Index file does not exist for query!"

    job_dir, _, _, paf_file, query_idx, target_idx = _build_small_paf_runtime(tmp_path)
    bad_target_idx = job_dir / "bad-target.idx"
    bad_target_idx.write_text("Target\nmissing\t5\n")
    paf = Paf(str(paf_file), str(query_idx), str(bad_target_idx), auto_parse=False)
    assert paf.parse_paf() is False
    assert paf.error == "Invalid contig for target: t2"

    unsorted = Paf(str(paf_file), str(query_idx), str(target_idx))
    assert unsorted.build_query_chr_as_reference(compress=False) == "_._"


def test_paf_sorted_marker_save_json_and_sorted_dotplot_branches(monkeypatch, tmp_path):
    from dgenies.lib.paf import Paf

    sorted_dir = tmp_path / "sorted-job"
    sorted_dir.mkdir()
    (sorted_dir / ".sorted").write_text("")
    sorted_paf = Paf(
        str(sorted_dir / "map.paf"),
        str(sorted_dir / "query.idx"),
        str(sorted_dir / "target.idx"),
        auto_parse=False,
    )
    assert sorted_paf.sorted is True
    assert sorted_paf.paf.endswith(".sorted")
    assert sorted_paf.idx_q.endswith(".sorted")

    monkeypatch.setattr(
        sorted_paf,
        "get_d3js_data",
        lambda: {"sorted": sorted_paf.sorted},
        raising=False,
    )
    assert sorted_paf.get_dotplot_data(sorted=True) == {"sorted": True}

    plain_dir = tmp_path / "plain-job"
    plain_dir.mkdir()
    plain_paf = Paf(
        str(plain_dir / "map.paf"),
        str(plain_dir / "query.idx"),
        str(plain_dir / "target.idx"),
        auto_parse=False,
    )
    sort_calls = []

    def fake_sort():
        sort_calls.append("sort")
        plain_paf.sorted = True

    monkeypatch.setattr(plain_paf, "sort", fake_sort, raising=False)
    monkeypatch.setattr(
        plain_paf, "get_d3js_data", lambda: {"sorted": plain_paf.sorted}, raising=False
    )
    assert plain_paf.get_dotplot_data(sorted=True) == {"sorted": True}
    assert sort_calls == ["sort"]

    out_json = plain_dir / "dotplot.json"
    monkeypatch.setattr(
        plain_paf,
        "get_d3js_data",
        lambda: {"lines": {"3": [[0, 1, 0, 1, 1.0, "q1", "t1"]]}},
        raising=False,
    )
    plain_paf.save_json(str(out_json))
    assert json.loads(out_json.read_text()) == {
        "lines": {"3": [[0, 1, 0, 1, 1.0, "q1", "t1"]]}
    }


def test_paf_parse_sampling_and_missing_target_or_query_inputs(tmp_path):
    from dgenies.lib.paf import Paf

    job_dir, _, _, paf_file, query_idx, target_idx = _build_small_paf_runtime(tmp_path)

    missing_target = Paf(
        str(paf_file),
        str(query_idx),
        str(job_dir / "missing-target.idx"),
        auto_parse=False,
    )
    assert missing_target.parse_paf() is False
    assert missing_target.error == "Index file does not exist for target!"

    bad_query_idx = job_dir / "bad-query.idx"
    bad_query_idx.write_text("Query\nmissing\t5\n")
    bad_query = Paf(
        str(paf_file), str(bad_query_idx), str(target_idx), auto_parse=False
    )
    assert bad_query.parse_paf() is False
    assert bad_query.error == "Invalid contig for query: q1"

    missing_paf = Paf(
        str(job_dir / "missing.paf"), str(query_idx), str(target_idx), auto_parse=False
    )
    assert missing_paf.parse_paf() is False
    assert missing_paf.error == "PAF file does not exist!"

    sampled = Paf(str(paf_file), str(query_idx), str(target_idx), auto_parse=False)
    sampled.max_nb_lines = 0
    sampled.parse_paf()
    assert sampled.parsed is True
    assert sampled.sampled is True
    assert sampled.lines == {"0": [], "1": [], "2": [], "3": []}


def test_paf_is_contig_well_oriented_edge_cases(tmp_path):
    from dgenies.lib.paf import Paf

    paf = Paf(
        str(tmp_path / "map.paf"),
        str(tmp_path / "query.idx"),
        str(tmp_path / "target.idx"),
        auto_parse=False,
    )
    paf.q_contigs = {"q1": 100}
    paf.t_contigs = {"t1": 100}

    multi_line = [
        [10, 100, 10, 0, 10, 0, 10, 10],
        [30, 100, 30, 10, 20, 10, 20, 10],
    ]
    assert paf.is_contig_well_oriented(multi_line, "q1", "t1") is True

    single_line = [[10, 100, 10, 0, 10, 0, 10, 10]]
    assert paf.is_contig_well_oriented(single_line, "q1", "t1") is True

    ignored_line = [[10, 0.1, 10, 0, 1, 0, 1, 0.5]]
    assert paf.is_contig_well_oriented(ignored_line, "q1", "t1") is True

    reversed_lines = [
        [10, 100, 30, 0, 10, 0, 10, 10],
        [30, 100, 10, 10, 20, 10, 20, 10],
    ]
    assert paf.is_contig_well_oriented(reversed_lines, "q1", "t1") is False


def test_paf_parse_categories_sort_transitions_and_summary_failures(
    monkeypatch, tmp_path
):
    from dgenies.lib.paf import Paf

    job_dir = tmp_path / "paf_edges"
    job_dir.mkdir()
    query_idx = job_dir / "query.idx"
    target_idx = job_dir / "target.idx"
    paf_file = job_dir / "map.paf"
    query_idx.write_text("Query\nq0\t10\nq1\t10\nq2\t10\nq3\t10\n")
    target_idx.write_text("Target\nt0\t10\nt1\t10\nt2\t10\nt3\t10\n")
    paf_file.write_text(
        "q0\t10\t0\t10\t+\tt0\t10\t0\t10\t1\t10\t255\n"
        "q1\t10\t0\t10\t+\tt1\t10\t0\t10\t4\t10\t255\n"
        "q2\t10\t0\t10\t+\tt2\t10\t0\t10\t6\t10\t255\n"
        "q3\t10\t0\t10\t+\tt3\t10\t0\t10\t9\t10\t255\n"
    )

    paf = Paf(str(paf_file), str(query_idx), str(target_idx), auto_parse=False)
    assert paf.parse_paf(merge_index=False, noise=True) is None
    assert paf.parsed is True
    assert len(paf.lines["0"]) == 1
    assert len(paf.lines["1"]) == 1
    assert len(paf.lines["2"]) == 1
    assert len(paf.lines["3"]) == 1

    large_paf = job_dir / "large.paf"
    repeated_line = "q0\t10\t0\t10\t+\tt0\t10\t0\t10\t9\t10\t255\n"
    large_paf.write_text(repeated_line * 1001)
    noisy = Paf(str(large_paf), str(query_idx), str(target_idx), auto_parse=False)
    remove_calls = []
    monkeypatch.setattr(
        "dgenies.lib.paf.plt.hist",
        lambda _values, bins: ([100.0, 1.0], [0.0, 5.0, 10.0], []),
        raising=False,
    )
    monkeypatch.setattr(
        Paf,
        "remove_noise",
        staticmethod(lambda lines, limit: remove_calls.append(limit) or lines),
        raising=False,
    )
    assert noisy.parse_paf(merge_index=False, noise=False) is None
    assert noisy.parsed is True
    assert remove_calls == [5.0]

    sortable = Paf(str(paf_file), str(query_idx), str(target_idx), auto_parse=False)
    monkeypatch.setattr(
        sortable, "parse_paf", lambda *_args, **_kwargs: None, raising=False
    )
    monkeypatch.setattr(
        sortable,
        "compute_gravity_contigs",
        lambda: ({"q0": {"t0": 5}}, {("q0", "t0"): [(5, 1, 5, 0, 10, 0, 10, 10)]}),
        raising=False,
    )
    monkeypatch.setattr(
        sortable,
        "is_contig_well_oriented",
        lambda *_args, **_kwargs: True,
        raising=False,
    )
    update_calls = []
    monkeypatch.setattr(
        sortable,
        "_update_query_index",
        lambda reoriented: update_calls.append(list(reoriented)),
        raising=False,
    )
    sortable.name_q = "Query"
    sortable.q_order = ["q0"]
    sortable.q_contigs = {"q0": 10}
    sortable.len_q = 10
    sortable.sort()
    assert update_calls == [[]]
    assert (job_dir / "map.paf.sorted").read_text() == paf_file.read_text()

    sorted_marker = job_dir / ".sorted"
    if sorted_marker.exists():
        sorted_marker.unlink()
    already_sorted = Paf(
        str(paf_file), str(query_idx), str(target_idx), auto_parse=False
    )
    monkeypatch.setattr(
        already_sorted, "parse_paf", lambda *_args, **_kwargs: None, raising=False
    )
    (job_dir / "map.paf.sorted").write_text("sorted\n")
    (job_dir / "query.idx.sorted").write_text("Query\nq0\t10\n")
    already_sorted.sort()
    assert already_sorted.paf.endswith(".sorted")

    sorted_job = job_dir / "sorted_job"
    sorted_job.mkdir()
    (sorted_job / ".sorted").write_text("")
    (sorted_job / "map.paf").write_text("sorted\n")
    (sorted_job / "query.idx").write_text("Query\nq0\t10\n")
    (sorted_job / "target.idx").write_text("Target\nt0\t10\n")
    sorted_instance = Paf(
        str(sorted_job / "map.paf"),
        str(sorted_job / "query.idx"),
        str(sorted_job / "target.idx"),
        auto_parse=False,
    )
    monkeypatch.setattr(
        sorted_instance, "parse_paf", lambda *_args, **_kwargs: None, raising=False
    )
    sorted_instance.sort()
    assert sorted_instance.sorted is False
    assert not (sorted_job / ".sorted").exists()

    reversed_instance = Paf(
        str(paf_file), str(query_idx), str(target_idx), auto_parse=False
    )
    monkeypatch.setattr(
        reversed_instance, "parse_paf", lambda *_args, **_kwargs: None, raising=False
    )
    reverse_calls = []
    monkeypatch.setattr(
        reversed_instance,
        "reorient_contigs_in_paf",
        lambda contigs: reverse_calls.append(list(contigs)),
        raising=False,
    )
    monkeypatch.setattr(
        reversed_instance,
        "_update_query_index",
        lambda contigs: reverse_calls.append(["idx"] + list(contigs)),
        raising=False,
    )
    reversed_instance.reverse_contig("q0")
    assert reverse_calls == [["q0"], ["idx", "q0"]]
    assert reversed_instance.idx_q.endswith(".sorted")

    failed_summary = Paf(
        str(job_dir / "summary_fail.paf"),
        str(query_idx),
        str(target_idx),
        auto_parse=False,
    )
    monkeypatch.setattr(
        failed_summary, "parse_paf", lambda *_args, **_kwargs: None, raising=False
    )
    failed_summary.parsed = False
    status_file = job_dir / ".summary.failme"
    status_file.write_text("running")
    assert failed_summary.build_summary_stats(str(status_file)) is None
    assert not status_file.exists()
    assert (job_dir / ".summary.failme.fail").exists()
    assert failed_summary.get_summary_stats() is None


def test_paf_association_file_overlap_branches_and_missing_query_fasta(
    monkeypatch, tmp_path
):
    from intervaltree import Interval

    from dgenies.lib.paf import Paf

    paf = Paf(
        str(tmp_path / "assoc.paf"),
        str(tmp_path / "query.idx"),
        str(tmp_path / "target.idx"),
        auto_parse=False,
    )
    monkeypatch.setattr(
        paf, "compute_gravity_contigs", lambda: ({"q1": {}}, {}), raising=False
    )
    assert paf.get_query_on_target_association() == {"q1": None}

    paf.q_contigs = {"q1": 10}
    paf.q_order = ["q1"]
    paf.q_reversed = {"q1": False}
    paf.t_contigs = {"t1": 20}
    monkeypatch.setattr(
        paf,
        "get_query_on_target_association",
        lambda with_coords=True: {"q1": ("t1", -1, -1, -1, -1)},
        raising=False,
    )
    assoc_file = paf.build_query_on_target_association_file()
    assert "q1\tt1\t+\t10\tna\tna\t20\tna\tna" in assoc_file

    percents = {"-1": 20, "0": 0, "1": 0, "2": 0, "3": 0}

    class FakeTree:
        def __init__(self):
            self.items = [Interval(2, 8, 2), Interval(0, 5, 1)]
            self.inserted = []

        def __len__(self):
            return len(self.items)

        def pop(self):
            return self.items.pop()

        def overlap(self, start, end):
            return [
                item for item in self.items if item.begin < end and start < item.end
            ]

        def containsi(self, start, end, cat):
            return any(
                item.begin == start and item.end == end and item.data == cat
                for item in self.items
            )

        def discard(self, item):
            if item in self.items:
                self.items.remove(item)

        def __setitem__(self, key, value):
            self.inserted.append((key.start, key.stop, value))
            self.items.append(Interval(key.start, key.stop, value))

    overlap_percents = paf._remove_overlaps(FakeTree(), percents.copy())
    assert overlap_percents["1"] == 2
    assert overlap_percents["2"] == 6
    assert overlap_percents["-1"] == 12

    reverse_tree = FakeTree()
    reverse_tree.items = [Interval(0, 5, 2), Interval(0, 8, 1)]
    overlap_percents = paf._remove_overlaps(reverse_tree, percents.copy())
    assert overlap_percents["1"] == 3
    assert overlap_percents["2"] == 5

    containing_tree = FakeTree()
    containing_tree.items = [Interval(1, 6, 2), Interval(0, 10, 1)]
    overlap_percents = paf._remove_overlaps(containing_tree, percents.copy())
    assert overlap_percents["1"] == 5
    assert overlap_percents["2"] == 5

    query_dir = tmp_path / "reference_missing"
    query_dir.mkdir()
    (query_dir / ".query").write_text(str(query_dir / "missing.fa"))
    reference_paf = Paf(
        str(query_dir / "map.paf"),
        str(query_dir / "query.idx"),
        str(query_dir / "target.idx"),
        auto_parse=False,
    )
    reference_paf.sorted = True
    assert reference_paf.build_query_chr_as_reference(compress=False) == "_._"


def test_paf_reverse_contig_and_remaining_overlap_cases(monkeypatch, tmp_path):
    from intervaltree import Interval

    from dgenies.lib.paf import Paf

    paf = Paf(
        str(tmp_path / "remaining.paf"),
        str(tmp_path / "query.idx"),
        str(tmp_path / "target.idx"),
        auto_parse=False,
    )
    reverse_calls = []
    monkeypatch.setattr(
        paf,
        "parse_paf",
        lambda *_args, **_kwargs: reverse_calls.append("parse"),
        raising=False,
    )
    monkeypatch.setattr(
        paf,
        "reorient_contigs_in_paf",
        lambda contigs: reverse_calls.append(tuple(contigs)),
        raising=False,
    )
    monkeypatch.setattr(
        paf,
        "_update_query_index",
        lambda contigs: reverse_calls.append(("update", tuple(contigs))),
        raising=False,
    )
    paf.reverse_contig("chr1")
    assert paf.idx_q.endswith(".sorted")
    assert paf.sorted is True
    assert reverse_calls[:3] == ["parse", ("chr1",), ("update", ("chr1",))]

    base_percents = {"-1": 20, "0": 0, "1": 0, "2": 0, "3": 0}

    class ScenarioTree:
        def __init__(self, items, forced_overlaps=None):
            self.items = list(items)
            self.forced_overlaps = forced_overlaps

        def __len__(self):
            return len(self.items)

        def pop(self):
            return self.items.pop()

        def overlap(self, start, end):
            if self.forced_overlaps is not None:
                return list(self.forced_overlaps)
            return [
                item for item in self.items if item.begin < end and start < item.end
            ]

        def containsi(self, start, end, cat):
            return any(
                item.begin == start and item.end == end and item.data == cat
                for item in self.items
            )

        def discard(self, item):
            if item in self.items:
                self.items.remove(item)

        def __setitem__(self, key, value):
            self.items.append(Interval(key.start, key.stop, value))

    def resolve(items, expected, *, forced_overlaps=None):
        percents = paf._remove_overlaps(
            ScenarioTree(items, forced_overlaps=forced_overlaps), base_percents.copy()
        )
        assert percents == expected

    resolve(
        [Interval(2, 8, 1), Interval(0, 5, 2)],
        {"-1": 12, "0": 0, "1": 3, "2": 5, "3": 0},
    )
    resolve(
        [Interval(2, 5, 1), Interval(0, 5, 2)],
        {"-1": 15, "0": 0, "1": 0, "2": 5, "3": 0},
    )
    resolve(
        [Interval(2, 8, 1), Interval(0, 5, 1)],
        {"-1": 12, "0": 0, "1": 8, "2": 0, "3": 0},
    )
    resolve(
        [Interval(2, 5, 1), Interval(0, 5, 1)],
        {"-1": 15, "0": 0, "1": 5, "2": 0, "3": 0},
    )
    resolve(
        [Interval(2, 5, 1), Interval(0, 8, 2)],
        {"-1": 12, "0": 0, "1": 0, "2": 8, "3": 0},
    )
    resolve(
        [Interval(0, 5, 1), Interval(0, 8, 2)],
        {"-1": 12, "0": 0, "1": 0, "2": 8, "3": 0},
    )
    resolve(
        [Interval(0, 8, 1), Interval(0, 5, 2)],
        {"-1": 12, "0": 0, "1": 3, "2": 5, "3": 0},
    )
    resolve(
        [Interval(0, 8, 1), Interval(0, 5, 1)],
        {"-1": 12, "0": 0, "1": 8, "2": 0, "3": 0},
    )
    resolve(
        [Interval(0, 8, 2), Interval(0, 5, 1)],
        {"-1": 12, "0": 0, "1": 0, "2": 8, "3": 0},
    )
    resolve(
        [Interval(0, 5, 1), Interval(0, 5, 2)],
        {"-1": 15, "0": 0, "1": 0, "2": 5, "3": 0},
    )
    resolve(
        [Interval(0, 5, 2), Interval(0, 5, 1)],
        {"-1": 15, "0": 0, "1": 0, "2": 5, "3": 0},
    )
    resolve(
        [Interval(0, 8, 1), Interval(2, 5, 2)],
        {"-1": 12, "0": 0, "1": 5, "2": 3, "3": 0},
    )
    resolve(
        [Interval(0, 8, 2), Interval(2, 5, 1)],
        {"-1": 12, "0": 0, "1": 0, "2": 8, "3": 0},
    )
    resolve(
        [Interval(0, 5, 1), Interval(2, 8, 1)],
        {"-1": 12, "0": 0, "1": 8, "2": 0, "3": 0},
    )
    resolve(
        [Interval(0, 5, 2), Interval(2, 8, 1)],
        {"-1": 12, "0": 0, "1": 3, "2": 5, "3": 0},
    )
    resolve(
        [Interval(0, 8, 2), Interval(1, 6, 3), Interval(2, 5, 1)],
        {"-1": 12, "0": 0, "1": 0, "2": 3, "3": 5},
    )
    resolve(
        [Interval(0, 5, 1)],
        {"-1": 15, "0": 0, "1": 5, "2": 0, "3": 0},
        forced_overlaps=[Interval(1, 3, 2)],
    )
