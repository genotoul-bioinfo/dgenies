"""Upload payload, parser, and validator tests."""

import pytest

# This file was split out from src/dgenies/test_dgenies_api.py.

def test_upload_file_validators_and_parsers_helpers(monkeypatch, tmp_path):
    import dgenies.lib.parsers as parsers_module
    import dgenies.lib.validators as validators_module
    from dgenies.lib.upload_file import UploadFile

    image_payload = UploadFile("plot.png", "image/png", 12).get_file()
    assert image_payload == {"name": "plot.png", "type": "image/png", "size": 12, "url": "data/plot.png"}
    normal_payload = UploadFile("reads.fa.gz", "application/gzip", 15).get_file()
    assert normal_payload == {"name": "reads.fa.gz", "type": "application/gzip", "size": 15, "url": "data/reads.fa.gz"}
    error_payload = UploadFile("bad.exe", "application/octet-stream", 7, not_allowed_msg="Not allowed").get_file()
    assert error_payload == {"error": "Not allowed", "name": "bad.exe", "type": "application/octet-stream", "size": 7}
    disk_payload = UploadFile("saved.fa", size=22).get_file()
    assert disk_payload == {"name": "saved.fa", "size": 22, "url": "data/saved.fa"}

    valid_parts = ["query", "100", "0", "50", "+", "target", "200", "10", "60", "45", "50", "255"]
    assert validators_module._good_paf_line(valid_parts) is True
    assert validators_module._good_paf_line(valid_parts[:-1]) is False
    assert validators_module._good_paf_line(valid_parts[:4] + ["?"] + valid_parts[5:]) is False

    paf_file = tmp_path / "input.paf"
    paf_file.write_text(
        "\t".join(valid_parts) + "\n" +
        "\t".join(["bad", "field"]) + "\n"
    )
    assert validators_module.paf(str(paf_file), n_max=1) is True
    assert validators_module.paf(str(paf_file)) is False

    index_valid = tmp_path / "query.idx"
    index_valid.write_text("Query\nchr1\t10\nchr2\t20\n")
    index_invalid = tmp_path / "query.invalid.idx"
    index_invalid.write_text("Query\tbad\nchr1\t10\n")
    assert validators_module.v_idx(str(index_valid)) is True
    assert validators_module.v_idx(str(index_invalid)) is False

    maf_file = tmp_path / "input.maf"
    maf_file.write_text("# comment\na score=1\ns target 0 4 + 100 ACGT\ns query 0 4 + 50 ACGT\ni ignored line\n")

    monkeypatch.setattr(validators_module.AlignIO, "parse", lambda *_args, **_kwargs: [[1, 2], [3, 4]], raising=False)
    assert validators_module.maf(str(maf_file)) is True
    maf_filtered = maf_file.read_text()
    assert "ignored line" not in maf_filtered
    assert maf_filtered.startswith("# comment")

    monkeypatch.setattr(validators_module.AlignIO, "parse", lambda *_args, **_kwargs: [[1], [1, 2]], raising=False)
    assert validators_module.maf(str(maf_file)) is False

    monkeypatch.setattr(
        validators_module.AlignIO,
        "parse",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad maf")),
        raising=False,
    )
    assert validators_module.maf(str(maf_file)) is False

    class FakeSeq:
        def __init__(self, seq_id, seq, annotations):
            self.id = seq_id
            self._seq = seq
            self.annotations = annotations

        def __getitem__(self, index):
            return self._seq[index]

        def __len__(self):
            return len(self._seq)

    class FakeParser:
        def __init__(self, groups):
            self.groups = groups
            self.closed = False

        def __iter__(self):
            return iter(self.groups)

        def close(self):
            self.closed = True

    target_seq = FakeSeq("target", "ACGT", {"srcSize": 100, "start": 10, "size": 4, "strand": 1})
    query_seq = FakeSeq("query", "ACGA", {"srcSize": 50, "start": 5, "size": 4, "strand": 1})
    fake_parser = FakeParser([[target_seq, query_seq]])
    out_paf = tmp_path / "parsed.paf"
    monkeypatch.setattr(parsers_module.AlignIO, "parse", lambda *_args, **_kwargs: fake_parser, raising=False)
    assert parsers_module.maf(str(maf_file), str(out_paf)) is True
    assert fake_parser.closed is True
    assert out_paf.read_text().strip() == "query\t50\t5\t9\t+\ttarget\t100\t10\t14\t3\t4\t255"

    monkeypatch.setattr(
        parsers_module.AlignIO,
        "parse",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("parse failed")),
        raising=False,
    )
    assert parsers_module.maf(str(maf_file), str(out_paf)) is False

    mashmap_input = tmp_path / "mashmap.out"
    mashmap_output = tmp_path / "mashmap.paf"
    mashmap_input.write_text("query 100 0 100 + target 200 10 110 98.5\n")
    parsers_module.mashmap2paf(str(mashmap_input), str(mashmap_output))
    assert mashmap_output.read_text().strip() == "query\t100\t0\t100\t+\ttarget\t200\t10\t110\t985\t1000\t255"


# ---------------------------------------------------------------------------
# Additional tests for job_manager.py and paf.py
#
