import io
import json
import logging
import types

import pytest
from werkzeug.datastructures import FileStorage


def test_annotation_safe_job_dir_rejects_path_traversal_and_missing_job(tmp_path):
    from dgenies.lib.annotation_tracks import _safe_job_dir

    app_data = tmp_path / "data"
    (app_data / "job1").mkdir(parents=True)

    assert _safe_job_dir(str(app_data), "job1") == app_data / "job1"
    with pytest.raises(FileNotFoundError):
        _safe_job_dir(str(app_data), "../job1")
    with pytest.raises(FileNotFoundError):
        _safe_job_dir(str(app_data), "missing")


def test_annotation_load_manifest_ignores_corrupt_or_non_list_json(tmp_path):
    from dgenies.lib.annotation_tracks import _load_manifest, _manifest_path

    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    manifest = _manifest_path(job_dir)

    manifest.write_text("{bad json", encoding="utf-8")
    assert _load_manifest(job_dir) == []

    manifest.write_text(json.dumps({"id": "not-list"}), encoding="utf-8")
    assert _load_manifest(job_dir) == []

    manifest.write_text(json.dumps([{"id": "ok"}, "bad"]), encoding="utf-8")
    assert _load_manifest(job_dir) == [{"id": "ok"}]


def test_annotation_detect_format_prefers_longest_suffix():
    from dgenies.lib.annotation_tracks import _detect_format

    assert _detect_format("track.wiggle") == ("wig", "wiggle")
    assert _detect_format("track.WIG") == ("wig", "wig")
    assert _detect_format("track.bed") == ("bed", "bed")


def test_annotation_parse_numeric_helpers_report_field_names():
    from dgenies.lib.annotation_tracks import AnnotationTrackError, _parse_float, _parse_int

    assert _parse_int("12", 4, "start") == 12
    assert _parse_float("1.25", 5, "value") == 1.25
    with pytest.raises(AnnotationTrackError, match="start must be an integer"):
        _parse_int("x", 4, "start")
    with pytest.raises(AnnotationTrackError, match="value must be finite"):
        _parse_float("nan", 5, "value")


def test_annotation_validate_wig_accepts_fixedstep_variablestep_and_bedgraph(tmp_path):
    from dgenies.lib.annotation_tracks import _validate_wig

    fixed = tmp_path / "fixed.wig"
    fixed.write_text("fixedStep chrom=chr1 start=1 step=5\n1.0\n2.0\n")
    variable = tmp_path / "variable.wig"
    variable.write_text("variableStep chrom=chr1 span=2\n1 0.5\n3 1.5\n")
    bedgraph = tmp_path / "bedgraph.wig"
    bedgraph.write_text("chr1 0 10 0.5\nchr1 10 20 1.5\n")

    assert _validate_wig(fixed) == "wig"
    assert _validate_wig(variable) == "wig"
    assert _validate_wig(bedgraph) == "bedgraph"


@pytest.mark.parametrize(
    "contents, message",
    [
        ("fixedStep chrom=chr1 start=0 step=1\n1\n", "start must be greater than 0"),
        ("fixedStep chrom=chr1 start=1 step=0\n1\n", "step must be greater than 0"),
        ("variableStep chrom=chr1\n0 1.0\n", "position must be greater than 0"),
        ("track name=x\n", "does not contain any value"),
        ("1.0\n", "fixedStep or variableStep header"),
    ],
)
def test_annotation_validate_wig_rejects_malformed_data(tmp_path, contents, message):
    from dgenies.lib.annotation_tracks import AnnotationTrackError, _validate_wig

    wig = tmp_path / "bad.wig"
    wig.write_text(contents)

    with pytest.raises(AnnotationTrackError, match=message):
        _validate_wig(wig)


def test_annotation_save_track_truncates_display_name_and_sanitizes_filename(tmp_path):
    from dgenies.lib.annotation_tracks import AnnotationTracks

    app_data = tmp_path / "data"
    (app_data / "job1").mkdir(parents=True)
    uploaded = FileStorage(stream=io.BytesIO(b"chr1\t0\t10\n"), filename="../../unsafe name.bed")

    track = AnnotationTracks(str(app_data)).save_track("job1", "target", uploaded, "x" * 200)

    assert track["axis"] == "target"
    assert track["filename"] == "unsafe_name.bed"
    assert track["name"] == "x" * 120


def test_annotation_list_tracks_skips_manifest_entries_without_files(tmp_path):
    from dgenies.lib.annotation_tracks import AnnotationTracks, _manifest_path

    app_data = tmp_path / "data"
    job_dir = app_data / "job1"
    tracks_dir = job_dir / "annotation_tracks"
    tracks_dir.mkdir(parents=True)
    stored = tracks_dir / "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.bed"
    stored.write_text("chr1\t0\t1\n")
    _manifest_path(job_dir).write_text(
        json.dumps(
            [
                {
                    "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "axis": "query",
                    "format": "bed",
                    "name": "present",
                    "filename": "present.bed",
                    "stored_filename": stored.name,
                    "size": 9,
                    "created_at": "2026-01-01T00:00:00Z",
                },
                {
                    "id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "axis": "query",
                    "format": "bed",
                    "name": "missing",
                    "filename": "missing.bed",
                    "stored_filename": "missing.bed",
                    "size": 9,
                    "created_at": "2026-01-01T00:00:00Z",
                },
            ]
        )
    )

    tracks = AnnotationTracks(str(app_data)).list_tracks("job1")

    assert [track["id"] for track in tracks] == ["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]


def test_annotation_get_track_file_rejects_non_hex_id(tmp_path):
    from dgenies.lib.annotation_tracks import AnnotationTracks

    app_data = tmp_path / "data"
    (app_data / "job1").mkdir(parents=True)

    with pytest.raises(FileNotFoundError):
        AnnotationTracks(str(app_data)).get_track_file("job1", "not-hex")


class _FakeSchedule:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def every(self, value):
        self.calls.append(("every", value))

    def on(self, value):
        self.calls.append(("on", value))


class _FakeCronJob:
    def __init__(self, command, comment):
        self.command = command
        self.comment = comment
        self.day = _FakeSchedule("day")
        self.hour = _FakeSchedule("hour")
        self.minute = _FakeSchedule("minute")


class _FakeCronTab:
    def __init__(self):
        self.jobs = []
        self.removed = []
        self.writes = 0

    def new(self, command, comment):
        job = _FakeCronJob(command, comment)
        self.jobs.append(job)
        return job

    def remove_all(self, comment):
        self.removed.append(comment)

    def write(self):
        self.writes += 1


def _make_crons(monkeypatch, tmp_path, debug=False):
    import dgenies.lib.crons as crons

    fake_tab = _FakeCronTab()
    fake_config = types.SimpleNamespace(
        config_dir=str(tmp_path),
        cron_clean_time=[2, 30],
        cron_clean_freq=4,
        log_dir=str(tmp_path / "logs"),
    )
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(crons, "CronTab", lambda user=True: fake_tab)
    monkeypatch.setattr(crons, "AppConfigReader", lambda: fake_config)
    return crons.Crons("/srv/dgenies", debug=debug), fake_tab


def test_crons_clear_removes_crons_and_terminates_scheduler(tmp_path, monkeypatch):
    import dgenies.lib.crons as crons

    manager, fake_tab = _make_crons(monkeypatch, tmp_path)
    pid_file = tmp_path / ".local_scheduler_pid"
    pid_file.write_text("123\n")
    terminated = []
    monkeypatch.setattr(crons.psutil, "pid_exists", lambda pid: pid == 123)
    monkeypatch.setattr(crons.psutil, "Process", lambda pid: types.SimpleNamespace(terminate=lambda: terminated.append(pid)))

    manager.clear()

    assert fake_tab.removed == ["dgenies"]
    assert fake_tab.writes == 1
    assert terminated == [123]
    assert not pid_file.exists()


def test_crons_clear_keeps_pid_file_when_removal_disabled(tmp_path, monkeypatch):
    import dgenies.lib.crons as crons

    manager, fake_tab = _make_crons(monkeypatch, tmp_path)
    pid_file = tmp_path / ".local_scheduler_pid"
    pid_file.write_text("123\n")
    monkeypatch.setattr(crons.psutil, "pid_exists", lambda pid: True)

    manager.clear(remove_pid_file=False)

    assert fake_tab.removed == ["dgenies"]
    assert pid_file.exists()


def test_crons_init_clean_cron_builds_expected_schedule(tmp_path, monkeypatch):
    manager, fake_tab = _make_crons(monkeypatch, tmp_path)

    manager.init_clean_cron()

    job = fake_tab.jobs[0]
    assert "/srv/dgenies/bin/clean_jobs.py" in job.command
    assert job.comment == "dgenies"
    assert job.day.calls == [("every", 4)]
    assert job.hour.calls == [("on", 2)]
    assert job.minute.calls == [("on", 30)]


def test_crons_init_launch_local_cron_uses_debug_log_file(tmp_path, monkeypatch):
    manager, fake_tab = _make_crons(monkeypatch, tmp_path, debug=True)

    manager.init_launch_local_cron()

    job = fake_tab.jobs[0]
    assert "start_local_scheduler.sh /srv/dgenies" in job.command
    assert str(tmp_path / "logs" / "local_scheduler.log") in job.command
    assert job.minute.calls == [("every", 1)]


def test_crons_init_clean_cron_requires_base_dir(tmp_path, monkeypatch):
    manager, _ = _make_crons(monkeypatch, tmp_path)
    manager.base_dir = None

    with pytest.raises(Exception, match="base_dir"):
        manager.init_clean_cron()


def test_mailer_disabled_branch_prints_message_without_sending(capsys):
    from dgenies.lib.mailer import Mailer

    mailer = object.__new__(Mailer)
    mailer.config = types.SimpleNamespace(
        mail_org=None,
        mail_status_sender="status@example.org",
        mail_reply="reply@example.org",
        disable_mail=True,
    )
    mailer._send_async_email = lambda msg: pytest.fail("mail should not be sent")

    mailer.send_mail(["user@example.org"], "Subject", "Body", "<p>Body</p>")

    out = capsys.readouterr().out
    assert "SEND MAILS DISABLED" in out
    assert "Subject: Subject" in out


def test_mailer_send_async_email_uses_app_context():
    from dgenies.lib.mailer import Mailer

    events = []

    class Context:
        def __enter__(self):
            events.append("enter")

        def __exit__(self, exc_type, exc, tb):
            events.append("exit")

    mailer = object.__new__(Mailer)
    mailer.app = types.SimpleNamespace(app_context=lambda: Context())
    mailer.mail = types.SimpleNamespace(send=lambda msg: events.append(("send", msg)))

    mailer._send_async_email("message")

    assert events == ["enter", ("send", "message"), "exit"]


def test_database_context_tracks_nested_connections(monkeypatch):
    import dgenies.database as database

    events = []
    fake_proxy = types.SimpleNamespace(
        connect=lambda: events.append("connect"),
        close=lambda: events.append("close"),
    )
    monkeypatch.setattr(database, "database_proxy", fake_proxy)
    database.Database.nb_open = 0

    with database.Database():
        with database.Database():
            assert database.Database.nb_open == 2
        assert database.Database.nb_open == 1

    assert events == ["connect", "connect", "close"]


def test_database_initialize_rejects_unsupported_type(monkeypatch):
    import dgenies.database as database

    monkeypatch.setattr(database.config, "database_type", "postgres")
    monkeypatch.setattr(database.config, "database_db", "dgenies")

    with pytest.raises(Exception, match="Unsupported database type"):
        database.initialize()


def test_latest_write_update_skips_empty_values(tmp_path):
    from dgenies.lib.latest import Latest

    latest = object.__new__(Latest)
    latest.latest = ""
    latest.win32 = ""
    latest._save_latest = str(tmp_path / ".latest")

    latest._write_update()

    assert not (tmp_path / ".latest").exists()


def test_latest_load_missing_cache_calls_update(tmp_path, monkeypatch):
    from dgenies.lib.latest import Latest

    calls = []
    latest = object.__new__(Latest)
    latest.latest = ""
    latest.win32 = ""
    latest._save_latest = str(tmp_path / ".latest")
    monkeypatch.setattr(Latest, "update", lambda self: calls.append("update"))

    latest.load()

    assert calls == ["update"]


def test_latest_update_async_starts_timer(monkeypatch):
    from dgenies.lib.latest import Latest
    import dgenies.lib.latest as latest_module

    calls = []

    class Timer:
        def __init__(self, delay, callback):
            calls.append(("timer", delay, callback.__name__))

        def start(self):
            calls.append("start")

    monkeypatch.setattr(latest_module.threading, "Timer", Timer)

    Latest.update_async(object.__new__(Latest))

    assert calls == [("timer", 1, "update"), "start"]


def test_latest_update_does_not_change_values_when_response_has_no_tag(tmp_path, monkeypatch):
    from dgenies.lib.latest import Latest

    latest = object.__new__(Latest)
    latest.latest = "1.0.0"
    latest.win32 = "old.exe"
    latest._save_latest = str(tmp_path / ".latest")
    response = types.SimpleNamespace(ok=True, content=json.dumps({"assets": []}).encode("utf-8"))
    monkeypatch.setattr("dgenies.lib.latest.requests.get", lambda url: response)

    latest.update()

    assert latest.latest == "1.0.0"
    assert latest.win32 == "old.exe"
    assert (tmp_path / ".latest").read_text() == "1.0.0\nold.exe"


def test_datamodels_dotplot_and_annotation_track_dump(launched_app):
    from dgenies.api import datamodels as dm

    dotplot = dm.Dotplot(
        y_len=10,
        x_len=20,
        lines={3: [(0, 1, 2, 3, 0.9, "q", "t")]},
        y_contigs={"q": 10},
        y_order=["q"],
        x_contigs={"t": 20},
        x_order=["t"],
        name_y="Query",
        name_x="Target",
        max_nb_lines=100,
    )
    track = dm.AnnotationTrack(
        id="a" * 32,
        job_id="job1",
        axis=dm.AnnotationTrackAxis.query,
        format=dm.AnnotationTrackFormat.bedgraph,
        name="Coverage",
        filename="coverage.wig",
        size=12,
        created_at="2026-01-01T00:00:00Z",
    )

    assert dotplot.model_dump()["sorted"] is False
    assert track.model_dump()["format"] == dm.AnnotationTrackFormat.bedgraph


def test_datamodels_validate_non_negative_counts(launched_app):
    from pydantic import ValidationError

    from dgenies.api import datamodels as dm

    with pytest.raises(ValidationError):
        dm.QTAssoc(records=[], count=-1)
    with pytest.raises(ValidationError):
        dm.NoAssoc(which=dm.ContigType.query, count=-1, contigs=[])


def test_datamodels_prepare_fasta_and_summary_responses(launched_app):
    from dgenies.api import datamodels as dm

    prepare = dm.PrepareFastaResponse(data=dm.PrepareFasta(status=dm.PrepareFastaEnum.done, gzip=True, mail=False))
    summary = dm.SummaryResponse(data={-1: 0.0, 3: 100.0})

    assert prepare.data.status == dm.PrepareFastaEnum.done
    assert summary.data == {-1: 0.0, 3: 100.0}


def test_job_descriptions_generate_option_entries_from_tool():
    from dgenies.api.job_descriptions import generate_tool_options_description
    from dgenies.tools import Tool

    tool = Tool(
        name="mapper",
        exec="/bin/mapper",
        command_line="{exe} {target} {query} -o {out}",
        all_vs_all="{exe} {target} -o {out}",
        max_memory=4,
        options=[
            {
                "group": "mode",
                "label": "Mode",
                "help": "Choose a mode",
                "type": "radio",
                "entries": [
                    {"key": "fast", "label": "Fast", "help": "Fast mode", "value": "--fast", "default": True},
                    {"key": "slow", "label": "Slow", "value": "--slow"},
                ],
            }
        ],
    )

    options = generate_tool_options_description(tool)

    assert options[0].name == "mode"
    assert options[0].mutex is True
    assert options[0].entries[0].name == "mode:fast"
    assert options[0].entries[0].default is True


def test_package_set_logger_registers_expected_loggers():
    import dgenies

    dgenies.set_logger("WARNING")

    assert logging.getLogger("dgenies").level == logging.WARNING
    assert logging.getLogger("werkzeug").level == logging.WARNING
