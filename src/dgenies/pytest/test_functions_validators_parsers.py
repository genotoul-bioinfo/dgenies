import gzip
from pathlib import Path
from types import SimpleNamespace


def test_functions_file_names_extensions_and_jobs(tmp_path, monkeypatch):
    from dgenies.lib.functions import Functions
    import dgenies.lib as lib_package

    assert lib_package.__name__ == "dgenies.lib"
    assert Functions.allowed_file("query.fa")
    assert Functions.allowed_file("archive.tar.gz", ("backup",))
    assert not Functions.allowed_file("notes.txt", ("fasta",))
    assert Functions.allowed_file_ext("map.paf", {"plot"}, {"align"})
    assert not Functions.allowed_file_ext("map.exe", {"plot"}, {"align"})

    (tmp_path / "query.fa").write_text("x")
    assert Functions.get_valid_uploaded_filename("query.fa", str(tmp_path)) == "2_query.fa"
    assert len(Functions.random_string(12)) == 12

    job_dir = tmp_path / "jobA"
    job_dir.mkdir()
    for name in ("map.paf", "target.idx", "query.idx", ".valid", ".query", "logs.txt"):
        (job_dir / name).write_text("x")
    monkeypatch.setattr(Functions.config, "app_data", str(tmp_path))

    assert Functions.get_list_all_jobs("standalone") == ["jobA"]
    assert Functions.query_fasta_file_exists(str(job_dir))
    assert Functions.has_logs(str(job_dir))


def test_functions_compression_index_and_status_helpers(tmp_path):
    from dgenies.lib.functions import Functions

    index = tmp_path / "query.idx"
    index.write_text("Sample Name!\nctg1\t10\t1\nctg2\t5\n")
    parsed, name = Functions.read_index(str(index))
    assert name == "Sample_Name"
    assert parsed["ctg1"] == {"length": 10, "to_reverse": True}
    assert parsed["ctg2"] == {"length": 5, "to_reverse": False}

    plain = tmp_path / "data.txt"
    plain.write_text("hello")
    compressed = Functions.compress(str(plain), remove=False)
    assert compressed.endswith(".gz")
    assert Functions.is_gz_file(compressed)
    uncompressed = Functions.uncompress(compressed)
    assert Path(uncompressed).read_bytes() == b"hello"

    assert Functions.get_readable_size(2048) == "2.0 KiB"
    assert Functions.get_readable_time(3661) == "1 h 1 min 1 s"

    logs = tmp_path / "logs.txt"
    logs.write_text("log")
    job = SimpleNamespace(
        id_job="job1",
        logs=str(logs),
        status=lambda: {"status": "success", "error": "", "mem_peak": 2 * 1024 * 1024, "time_elapsed": 61},
    )
    assert Functions.get_status(job) == {
        "status": "success",
        "error": "",
        "has_logs": True,
        "id_job": "job1",
        "mem_peak": "2.0 G",
        "time_elapsed": "1 min 1 secs",
    }


def test_functions_sort_fasta_reorders_and_reverses_sequences(tmp_path):
    from dgenies.lib.functions import Functions

    fasta = tmp_path / "query.fa"
    fasta.write_text(">ctg1\nACGT\n>ctg2\nAAGG\n")
    index = tmp_path / "query.idx"
    index.write_text("Sorted Sample\nctg2\t4\t1\nctg1\t4\t0\n")
    lock = tmp_path / ".lock"
    lock.touch()
    dot = tmp_path / ".query.sorted"

    Functions.sort_fasta("job1", str(fasta), str(index), str(lock), dot_file=str(dot), mode="standalone")

    sorted_fasta = tmp_path / "Sorted_Sample.fasta"
    assert sorted_fasta.exists()
    assert sorted_fasta.read_text().splitlines()[0] == ">ctg2"
    assert dot.read_text() == str(sorted_fasta)
    assert not lock.exists()


def test_validators_accept_and_reject_paf_and_idx(tmp_path):
    from dgenies.lib import validators

    good_parts = ["q", "100", "1", "10", "+", "t", "200", "2", "11", "9", "10", "60"]
    assert validators._good_paf_line(good_parts)
    assert not validators._good_paf_line(good_parts[:-1])
    assert not validators._good_paf_line(good_parts[:4] + ["?"] + good_parts[5:])

    paf = tmp_path / "map.paf"
    paf.write_text("\t".join(good_parts) + "\n")
    assert validators.paf(str(paf))
    paf.write_text("bad\n")
    assert not validators.paf(str(paf))

    idx = tmp_path / "query.idx"
    idx.write_text("Query\nctg1\t10\nctg2\t20\n")
    assert validators.v_idx(str(idx))
    idx.write_text("Query\tbad\nctg1\t10\n")
    assert not validators.v_idx(str(idx))


def test_validator_maf_filters_comments_and_rejects_malformed_file(tmp_path):
    from dgenies.lib import validators

    maf = tmp_path / "bad.maf"
    maf.write_text("# comment\nignored metadata\na score=0\ns seq1 0 4 + 4 ACGT\n")
    assert not validators.maf(str(maf))
    assert "ignored metadata" not in maf.read_text()


def test_mashmap_parser_converts_space_delimited_output(tmp_path):
    from dgenies.lib.parsers import mashmap2paf

    source = tmp_path / "mashmap.out"
    source.write_text("q 100 0 10 + t 200 5 15 97.6\n")
    target = tmp_path / "map.paf"

    mashmap2paf(str(source), str(target))

    assert target.read_text() == "q\t100\t0\t10\t+\tt\t200\t5\t15\t976\t1000\t255\n"


def test_is_gz_file_detects_real_gzip(tmp_path):
    from dgenies.lib.functions import Functions

    gz = tmp_path / "data.gz"
    with gzip.open(gz, "wb") as handle:
        handle.write(b"hello")
    assert Functions.is_gz_file(str(gz))
