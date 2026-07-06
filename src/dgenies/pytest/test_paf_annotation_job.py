import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

from werkzeug.datastructures import FileStorage


def write_minimal_dotplot_files(tmp_path):
    query_idx = tmp_path / "query.idx"
    target_idx = tmp_path / "target.idx"
    paf = tmp_path / "map.paf"
    query_idx.write_text("Query\nq1\t100\t0\nq2\t50\t1\n")
    target_idx.write_text("Target\nt1\t200\n")
    paf.write_text("q1\t100\t10\t60\t+\tt1\t200\t20\t70\t45\t50\t60\n")
    return paf, query_idx, target_idx


def test_paf_parses_dotplot_data_and_associations(tmp_path):
    from dgenies.lib.paf import Paf

    paf_file, query_idx, target_idx = write_minimal_dotplot_files(tmp_path)
    paf = Paf(str(paf_file), str(query_idx), str(target_idx))

    assert paf.parsed
    assert paf.get_d3js_data()["name_y"] == "Query"
    assert paf.lines["3"][0][:5] == [20, 70, 10, 60, 0.9]
    assert list(paf.build_query_on_target_association_records()) == [
        ("q1", "t1", "+", 100, 10, 60, 200, 20, 70),
        ("q2", None, "-", 50, None, None, None, None, None),
    ]
    assert paf.build_list_no_assoc("query") == {"q2"}


def test_paf_noise_summary_and_sort_markers(tmp_path):
    from dgenies.lib.paf import Paf

    paf_file, query_idx, target_idx = write_minimal_dotplot_files(tmp_path)
    paf = Paf(str(paf_file), str(query_idx), str(target_idx), auto_parse=False)

    lines = {"0": [[0, 1, 0, 1, 0.1]], "1": [], "2": [], "3": [[0, 20, 0, 20, 0.9]]}
    assert Paf.remove_noise(lines, 5) == {"0": [], "1": [], "2": [], "3": [[0, 20, 0, 20, 0.9]]}

    status = tmp_path / ".summarize"
    status.touch()
    percents = paf.build_summary_stats(str(status))
    assert percents["3"] > 0
    assert not status.exists()
    assert paf.get_summary_stats() == percents

    paf.set_sorted(True)
    assert (tmp_path / ".sorted").exists()
    paf.set_sorted(False)
    assert not (tmp_path / ".sorted").exists()


def test_annotation_tracks_save_list_and_get_file(tmp_path):
    from dgenies.lib.annotation_tracks import AnnotationTracks

    app_data = tmp_path / "data"
    job_dir = app_data / "job1"
    job_dir.mkdir(parents=True)
    uploaded = FileStorage(stream=io.BytesIO(b"chr1\t0\t10\n"), filename="track.bed")

    manager = AnnotationTracks(str(app_data))
    track = manager.save_track("job1", "query", uploaded, "Regions")
    tracks = manager.list_tracks("job1")
    stored_path, served = manager.get_track_file("job1", track["id"])

    assert track["format"] == "bed"
    assert tracks == [track]
    assert stored_path.read_text() == "chr1\t0\t10\n"
    assert served["filename"] == "track.bed"


def test_annotation_track_validation_errors(tmp_path):
    import pytest
    from dgenies.lib.annotation_tracks import AnnotationTrackError, AnnotationTracks, _detect_format, _validate_bed3

    app_data = tmp_path / "data"
    (app_data / "job1").mkdir(parents=True)
    manager = AnnotationTracks(str(app_data))

    with pytest.raises(AnnotationTrackError):
        _detect_format("track.gff")
    with pytest.raises(AnnotationTrackError):
        manager.save_track("job1", "sideways", FileStorage(stream=io.BytesIO(b"x"), filename="track.bed"))

    bad = tmp_path / "bad.bed"
    bad.write_text("chr1\t10\t1\n")
    with pytest.raises(AnnotationTrackError, match="end must be greater than start"):
        _validate_bed3(bad)


def test_job_manager_contexts_and_pure_helpers(tmp_path, monkeypatch):
    from dgenies.lib.datafile import DataFile
    from dgenies.lib.job_manager import DataFileContextManager, JobManager

    datafile = DataFile("query", str(tmp_path / "query.fa"), "local")

    class FakeJob:
        id_job = "job1"

        def get_job_type(self):
            return "new"

        def get_datafiles(self):
            return [("query", datafile)]

        def get_file_size_for_role(self, role):
            return 123

        def __repr__(self):
            return "FakeJob(job1)"

    manager = DataFileContextManager([FakeJob()])
    assert manager.get_datafiles() == [datafile]
    assert manager.get_distinct(datafile, "file_role", "size_limit") == {("query", 123)}
    removed = manager.remove(datafile, file_role="query")
    assert len(removed) == 1
    assert manager.get_datafiles() == []

    jm = JobManager("job-pure", target=DataFile("Target", "target.fa", "local"), query=datafile)
    assert jm.get_align_format("map.paf") == "paf"
    assert jm.is_ava() is False
    jm.set_role("align", DataFile("Map", "map.paf", "local"))
    assert jm.aln_format == "paf"
    jm.unset_role("align")
    assert jm.align is None

    jm.config.disable_anonymous_analytics = True
    jm.config.anonymous_analytics = "left_hash"
    anon = jm._anonymize_mail_client("user@example.org")
    assert anon.endswith("@example.org")
    assert anon != "user@example.org"

    log = tmp_path / "logs.txt"
    log.write_text("ok\n###ERR### bad thing\n")
    assert JobManager.find_error_in_log(str(log)) == "bad thing"


def test_job_manager_backup_filter_and_job_list_helpers():
    from dgenies.lib.job_manager import JobManager

    members = []
    for name in ("map.paf", "query.idx", "target.idx", "logs.txt", "extra.txt"):
        info = tarfile.TarInfo(name)
        info.size = 0
        members.append(info)

    kept = list(JobManager.allowed_backup_files(members, {"map.paf", "query.idx", "target.idx"}, {"logs.txt"}))
    assert [item.name for item in kept] == ["map.paf", "query.idx", "target.idx"]

    jobs = [{"type": "align", "target": "target.fa"}, {"type": "plot", "align": "map.paf"}]
    assert JobManager.to_job_list(jobs) == [
        ("align", {"target": "target.fa"}),
        ("plot", {"align": "map.paf"}),
    ]
