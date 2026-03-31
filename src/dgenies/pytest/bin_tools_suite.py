"""Tests for helper binaries used by D-Genies."""

import argparse
import builtins
import io
import itertools
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# This file was split out from src/dgenies/test_dgenies_api.py.


def _run_module_fresh(module_name: str):
    sys.modules.pop(module_name, None)
    return runpy.run_module(module_name, run_name="__main__")

def test_bin_index_and_split_helpers(monkeypatch, tmp_path):
    import dgenies.bin.index as bin_index
    import dgenies.bin.split_fa as split_fa_module

    assert isinstance(bin_index.Index(), bin_index.Index)

    fasta_file = tmp_path / "query.fa"
    fasta_file.write_text(">chr1 description\nACGT\nACGT\n>chr2\nAAAA\n")
    index_file = tmp_path / "query.idx"
    copied_fasta = tmp_path / "copied.fa"

    success, nb_contigs, error = bin_index.index_file(str(fasta_file), "QuerySample", str(index_file), str(copied_fasta))
    assert success is True
    assert nb_contigs == 2
    assert error == ""
    assert copied_fasta.read_text() == fasta_file.read_text()

    name, order, contigs, reversed_c, abs_start, total_len = bin_index.Index.load(str(index_file))
    assert name == "QuerySample"
    assert order == ["chr1", "chr2"]
    assert contigs == {"chr1": 8, "chr2": 4}
    assert reversed_c == {"chr1": False, "chr2": False}
    assert abs_start == {"chr1": 0, "chr2": 8}
    assert total_len == 12

    split_index = tmp_path / "query_split.idx"
    split_index.write_text("QuerySample\nchr1_###_1\t4\t0\nchr1_###_2\t4\t1\nchr2\t4\t0\n")
    merged = bin_index.Index.load(str(split_index), merge_splits=True)
    assert merged[1] == ["chr1", "chr2"]
    assert merged[2]["chr1"] == 8
    assert merged[3]["chr1"] is True

    saved_index = tmp_path / "saved.idx"
    bin_index.Index.save(str(saved_index), "SavedSample", {"chrA": 5, "chrB": 7}, ["chrB", "chrA"], {"chrA": False, "chrB": True})
    assert saved_index.read_text() == "SavedSample\nchrB\t7\t1\nchrA\t5\t0\n"

    invalid_seq = tmp_path / "invalid.fa"
    invalid_seq.write_text(">chr1\nACGT\nXYZ\n")
    assert bin_index.index_file(str(invalid_seq), "Bad", str(tmp_path / "bad.idx")) == (False, 0, "Error: invalid sequence at line 3")

    empty_contig = tmp_path / "empty.fa"
    empty_contig.write_text(">chr1\n>chr2\nACGT\n")
    assert bin_index.index_file(str(empty_contig), "Bad", str(tmp_path / "empty.idx")) == (False, 0, "Error: contig is empty: chr1")

    no_header = tmp_path / "no_header.fa"
    no_header.write_text("ACGT\n")
    assert bin_index.index_file(str(no_header), "Bad", str(tmp_path / "no_header.idx")) == (False, 0, "")

    missing_header = tmp_path / "missing_header.fa"
    missing_header.write_text(">chr1\nACGT\n\nACGT\n")
    assert bin_index.index_file(str(missing_header), "Bad", str(tmp_path / "missing_header.idx")) == (
        False,
        0,
        "Error: new header line expected at line 4",
    )

    assert list(split_fa_module.Splitter.split_contig("chr1", "ACGT", 10).items()) == [("chr1", "ACGT")]
    assert list(split_fa_module.Splitter.split_contig("chr1", "ABCDEFGHI", 4).keys()) == ["chr1_###_1", "chr1_###_2", "chr1_###_3"]

    wrapped = tmp_path / "wrapped.fa"
    with open(wrapped, "w") as handle:
        split_fa_module.Splitter.write_contig("chrX", "A" * 65, handle)
    assert wrapped.read_text() == ">chrX\n" + ("A" * 60) + "\n" + ("A" * 5) + "\n\n"

    splitter_output = tmp_path / "split.fa"
    splitter = split_fa_module.Splitter(str(fasta_file), "QuerySample", str(splitter_output), size_c=4)
    split_success, split_error = splitter.split()
    assert split_success is True
    assert split_error == ""
    assert splitter.nb_contigs == 2
    split_index_content = (tmp_path / "query_split.idx").read_text()
    assert "chr1_###_1\t4" in split_index_content
    assert "chr1_###_2\t4" in split_index_content
    assert "chr2\t4" in split_index_content

    invalid_split_input = tmp_path / "invalid_split.fa"
    invalid_split_input.write_text(">chr1\nACGT\n\nACGT\n")
    invalid_splitter = split_fa_module.Splitter(str(invalid_split_input), "QuerySample", str(tmp_path / "invalid_split.out.fa"), size_c=4)
    assert invalid_splitter.split() == (False, "Error: new header line expected at line 4")

    empty_split_input = tmp_path / "empty_split.fa"
    empty_split_input.write_text(">chr1\n>chr2\nACGT\n")
    empty_splitter = split_fa_module.Splitter(str(empty_split_input), "QuerySample", str(tmp_path / "empty_split.out.fa"), size_c=4)
    assert empty_splitter.split() == (False, "Error: contig is empty: chr1")

    debug_messages = []
    monkeypatch.setattr(split_fa_module, "print", lambda *args, **kwargs: debug_messages.append("".join(str(arg) for arg in args)), raising=False)
    debug_splitter = split_fa_module.Splitter(str(fasta_file), "QuerySample", str(tmp_path / "debug_split.fa"), size_c=4, debug=True)
    debug_splitter.flush_contig("AAAA", "chrKeep", 10, io.StringIO(), io.StringIO())
    debug_splitter.flush_contig("ABCDEFGHI", "chrSplit", 4, io.StringIO(), io.StringIO())
    assert split_fa_module.Splitter(
        str(fasta_file),
        "QuerySample",
        str(tmp_path / "debug_parse_split.fa"),
        size_c=4,
        debug=True,
    ).split() == (True, "")
    assert any("Keeped!" in message for message in debug_messages)
    assert any("Splited in 3 contigs!" in message for message in debug_messages)

    invalid_sequence_split = tmp_path / "invalid_sequence_split.fa"
    invalid_sequence_split.write_text(">chr1\nACGT\nXYZ\n")
    invalid_sequence_runner = split_fa_module.Splitter(
        str(invalid_sequence_split),
        "QuerySample",
        str(tmp_path / "invalid_sequence_split.out.fa"),
        size_c=4,
    )
    assert invalid_sequence_runner.split() == (False, "Error: invalid sequence at line 3")

    printed = []
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(arg) for arg in args)), raising=False)
    monkeypatch.setattr(sys, "argv", ["index.py", "-i", str(fasta_file), "-n", "CliQuery", "-o", str(tmp_path / "cli.idx")], raising=False)
    _run_module_fresh("dgenies.bin.index")
    assert printed[-1] == "Success!"

    monkeypatch.setattr(sys, "argv", ["index.py", "-i", str(invalid_seq), "-n", "CliBad", "-o", str(tmp_path / "cli_bad.idx")], raising=False)
    _run_module_fresh("dgenies.bin.index")
    assert printed[-1] == "Error: invalid sequence at line 3"

    monkeypatch.setattr(sys, "argv", ["split_fa.py", "-i", str(fasta_file), "-n", "SplitCLI", "-s", "1", "-o", str(tmp_path / "cli_split.fa")], raising=False)
    with pytest.raises(SystemExit) as split_exit:
        _run_module_fresh("dgenies.bin.split_fa")
    assert split_exit.value.code == 0

    monkeypatch.setattr(sys, "argv", ["split_fa.py", "-i", str(fasta_file), "-n", "SplitCLI", "-s", "-1", "-o", str(tmp_path / "cli_split_invalid.fa")], raising=False)
    with pytest.raises(SystemExit):
        _run_module_fresh("dgenies.bin.split_fa")


def test_bin_filter_merge_and_sort_helpers(monkeypatch, tmp_path):
    import dgenies.bin.filter_contigs as filter_module
    import dgenies.bin.merge_splitted_chrms as merge_module
    import dgenies.bin.sort_paf as sort_paf_module
    from dgenies.bin.index import index_file as build_index

    filter_index = tmp_path / "filter.idx"
    filter_index.write_text("Query\n")
    filter_fasta = tmp_path / "filter.fa"
    filter_fasta.write_text(">chrA\nAAAA\n>chrB\nCCCC\n>chrTiny\nTT\n")
    saved_indexes = []

    def fake_load(index_file, merge_splits=False):
        if merge_splits:
            return "Query", ["chrA", "chrB", "chrTiny"], {"chrA": 100, "chrB": 90, "chrTiny": -1}, {"chrA": False, "chrB": False, "chrTiny": False}, {"chrA": 0, "chrB": 100, "chrTiny": 190}, 189
        return "Query", ["chrA", "chrB", "chrTiny"], {"chrA": 100, "chrB": 90, "chrTiny": -1}, {"chrA": False, "chrB": False, "chrTiny": False}, {"chrA": 0, "chrB": 100, "chrTiny": 190}, 189

    assert fake_load("ignored.idx", merge_splits=True)[1] == ["chrA", "chrB", "chrTiny"]

    monkeypatch.setattr(filter_module.Index, "load", staticmethod(fake_load), raising=False)
    monkeypatch.setattr(
        filter_module.Index,
        "save",
        staticmethod(lambda index_file, name, contigs, order, reversed_c: saved_indexes.append((index_file, name, contigs, order, reversed_c))),
        raising=False,
    )
    filterer = filter_module.Filter(str(filter_fasta), str(filter_index), "target", min_filtered=0, split=False)
    assert filterer._check_filter() == ["chrTiny"]
    assert (tmp_path / ".filter-target").read_text() == "chrTiny\n"
    assert saved_indexes[0][3] == ["chrA", "chrB"]

    split_load_calls = []

    def fake_split_load(index_file, merge_splits=False):
        split_load_calls.append(merge_splits)
        if merge_splits:
            return "Query", ["chrA", "chrB", "chrTiny"], {"chrA": 100, "chrB": 90, "chrTiny": -1}, {"chrA": False, "chrB": False, "chrTiny": False}, {"chrA": 0, "chrB": 100, "chrTiny": 190}, 189
        return (
            "Query",
            ["chrA_###_1", "chrA_###_2", "chrB", "chrTiny_###_1"],
            {"chrA_###_1": 50, "chrA_###_2": 50, "chrB": 90, "chrTiny_###_1": -1},
            {"chrA_###_1": False, "chrA_###_2": False, "chrB": False, "chrTiny_###_1": False},
            {"chrA_###_1": 0, "chrA_###_2": 50, "chrB": 100, "chrTiny_###_1": 190},
            189,
        )

    monkeypatch.setattr(filter_module.Index, "load", staticmethod(fake_split_load), raising=False)
    split_filterer = filter_module.Filter(str(filter_fasta), str(filter_index), "target", min_filtered=0, split=True)
    assert split_filterer._check_filter() == ["chrTiny_###_1"]
    assert split_load_calls == [True, False]

    monkeypatch.setattr(filter_module.Index, "load", staticmethod(fake_load), raising=False)
    assert filter_module.Filter(str(filter_fasta), str(filter_index), "target", min_filtered=5, split=False)._check_filter() == []

    many_small = {f"ctg{i}": 1 for i in range(101)}

    monkeypatch.setattr(
        filter_module.Index,
        "load",
        staticmethod(lambda index_file, merge_splits=False: ("Query", list(many_small.keys()), many_small, {k: False for k in many_small}, {k: i for i, k in enumerate(many_small)}, 101)),
        raising=False,
    )
    query_filterer = filter_module.Filter(str(filter_fasta), str(filter_index), "query", min_filtered=0, split=False)
    assert query_filterer._check_filter() == []
    assert (tmp_path / ".do-sort").exists()

    replace_fasta = tmp_path / "replace.fa"
    replace_fasta.write_text(">chr1\nAAAA\n>chr2\nCCCC\n")
    filter_out = filter_module.Filter(str(replace_fasta), str(filter_index), "query", out_fasta=str(tmp_path / "filtered.fa"), replace_fa=True)
    filter_out._filter_out(["chr2"])
    assert replace_fasta.read_text() == ">chr1\nAAAA\n"

    monkeypatch.setattr(filter_module.Filter, "_check_filter", lambda self: ["chr2"], raising=False)
    filtered_output = []
    monkeypatch.setattr(filter_module.Filter, "_filter_out", lambda self, f_outs: filtered_output.extend(f_outs), raising=False)
    assert filter_module.Filter(str(replace_fasta), str(filter_index), "query").filter() is True
    assert filtered_output == ["chr2"]
    monkeypatch.setattr(filter_module.Filter, "_check_filter", lambda self: [], raising=False)
    assert filter_module.Filter(str(replace_fasta), str(filter_index), "query").filter() is False

    query_in = tmp_path / "query_in.idx"
    query_in.write_text("QuerySample\nchr1_###_2\t4\nchr1_###_1\t3\nchr2\t5\n")
    paf_in = tmp_path / "input.paf"
    paf_in.write_text(
        "chr1_###_2\t4\t1\t4\t+\ttarget\t100\t10\t13\t3\t3\t255\n"
        "chr2\t5\t0\t5\t+\ttarget\t100\t20\t25\t5\t5\t255\n"
    )
    paf_out = tmp_path / "merged.paf"
    query_out = tmp_path / "query_out.idx"
    merger = merge_module.Merger(str(paf_in), str(paf_out), str(query_in), str(query_out), debug=True)
    merger.merge()
    merged_lines = paf_out.read_text().splitlines()
    assert merged_lines[0] == "chr1\t7\t4\t7\t+\ttarget\t100\t10\t13\t3\t3\t255"
    assert merged_lines[1] == "chr2\t5\t0\t5\t+\ttarget\t100\t20\t25\t5\t5\t255"
    assert query_out.read_text() == "QuerySample\nchr1\t7\nchr2\t5\n"

    sorter_input = tmp_path / "unsorted.paf"
    sorter_output = tmp_path / "sorted.paf"
    sorter_input.write_text(
        "q1\t100\t0\t10\t+\tt1\t100\t0\t10\t10\t10\t255\n"
        "q2\t100\t0\t30\t+\tt2\t100\t0\t30\t30\t30\t255\n"
    )
    sorter = sort_paf_module.Sorter(str(sorter_input), str(sorter_output))
    sorted_lines = sorter._get_sorted_paf_lines()
    assert sorted_lines[0][0] == "q2"
    sorter.sort()
    assert sorter_output.read_text().splitlines()[0].startswith("q2\t100\t0\t30")

    main_filter_fasta = tmp_path / "main_filter.fa"
    main_filter_fasta.write_text(">chr1\n" + ("A" * 120) + "\n>chr2\n" + ("C" * 110) + "\n>tiny\nTT\n")
    main_filter_index = tmp_path / "main_filter.idx"
    ok, _, error = build_index(str(main_filter_fasta), "MainFilter", str(main_filter_index))
    assert ok is True, error
    monkeypatch.setattr(
        sys,
        "argv",
        ["filter_contigs.py", "-f", str(main_filter_fasta), "-i", str(main_filter_index), "-t", "target", "-m", "0", "-r"],
        raising=False,
    )
    _run_module_fresh("dgenies.bin.filter_contigs")
    assert main_filter_fasta.read_text().startswith(">chr1")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "merge_splitted_chrms.py",
            "-pi",
            str(paf_in),
            "-po",
            str(tmp_path / "cli_merged.paf"),
            "-qi",
            str(query_in),
            "-qo",
            str(tmp_path / "cli_query_out.idx"),
        ],
        raising=False,
    )
    with pytest.raises(SystemExit) as merge_exit:
        _run_module_fresh("dgenies.bin.merge_splitted_chrms")
    assert merge_exit.value.code in {None, 0}

    import types

    fallback_index = types.ModuleType("index")
    fallback_index.Index = filter_module.Index
    real_import = builtins.__import__

    def fallback_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "dgenies.bin.index":
            raise ImportError("force fallback")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setitem(sys.modules, "index", fallback_index)
    monkeypatch.setattr(builtins, "__import__", fallback_import, raising=False)
    module_globals = runpy.run_path(filter_module.__file__, run_name="filter_contigs_fallback")
    assert module_globals["Index"] is filter_module.Index


def test_bin_sort_cli_and_large_input_strategy(monkeypatch, tmp_path):
    import dgenies.bin.sort_paf as sort_paf_module

    sorter_input = tmp_path / "large_unsorted.paf"
    sorter_output = tmp_path / "large_sorted.paf"
    line = "q1\t100\t0\t20\t+\tt1\t100\t0\t20\t20\t20\t255\n"

    class RepeatReader:
        def __init__(self, repeated_line, count):
            self.repeated_line = repeated_line
            self.count = count

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def __iter__(self):
            return itertools.repeat(self.repeated_line, self.count)

    sorter = sort_paf_module.Sorter(str(sorter_input), str(sorter_output))
    monkeypatch.setattr(sort_paf_module, "open", lambda *_args, **_kwargs: RepeatReader(line, 4_000_000), raising=False)
    paf_lines = sorter._sort_lines(itertools.repeat(line, 1_000_001))
    assert len(paf_lines) == 500_001
    assert paf_lines[0][0] == "q1"

    cli_input = tmp_path / "cli_input.paf"
    cli_input.write_text(line)
    version_prints = []

    class SortCliArgs(SimpleNamespace):
        def __getitem__(self, key):
            if key == "--version":
                return self.version
            raise KeyError(key)

    args_values = iter(
        [
            SortCliArgs(version=True, input=str(cli_input), output=str(tmp_path / "version.paf")),
            SortCliArgs(version=False, input=str(cli_input), output=str(tmp_path / "cli_out.paf")),
            SortCliArgs(version=False, input=str(tmp_path / "missing_input.paf"), output=str(tmp_path / "missing_out.paf")),
        ]
    )
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", lambda self: next(args_values), raising=False)
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: version_prints.append(" ".join(str(arg) for arg in args)), raising=False)

    with pytest.raises(KeyError):
        SortCliArgs(version=False, input="in", output="out")["missing"]

    _run_module_fresh("dgenies.bin.sort_paf")
    assert any("Sort_paf" in line for line in version_prints)

    _run_module_fresh("dgenies.bin.sort_paf")
    assert (tmp_path / "cli_out.paf").exists()

    with pytest.raises(Exception, match="does not exists"):
        _run_module_fresh("dgenies.bin.sort_paf")
