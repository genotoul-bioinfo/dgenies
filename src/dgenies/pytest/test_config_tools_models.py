import importlib
import os
import sys
import types
from types import SimpleNamespace

import pytest


def test_config_reader_parses_sizes_and_environment_paths(monkeypatch):
    from dgenies.config_reader import AppConfigReader

    config = AppConfigReader()
    assert config._parse_size("1M") == 1024 * 1024
    assert config._parse_size("1.5G") == int(1.5 * 1024 * 1024 * 1024)
    assert config._parse_size("-1") == -1
    with pytest.raises(ValueError):
        config._parse_size("10K")

    monkeypatch.setenv("CONFIG_DIR", "/tmp/dgenies-config")
    assert config._get_config_dir() == "/tmp/dgenies-config"
    assert "dgenies" in config._replace_vars("###PROGRAM###")


def test_allowed_extensions_exposes_formats_and_roles():
    from dgenies.allowed_extensions import AllowedExtensions

    allowed = AllowedExtensions()
    assert "fa" in allowed.get_extensions("fasta")
    assert allowed.get_description("idx") == "an index file"
    assert allowed.get_formats("plot", "align") == ["map"]
    assert set(allowed.get_roles("new")) == {"query", "target"}
    assert allowed.allowed_extensions_per_format["backup"] == ["tar", "tar.gz"]


def test_tool_options_defaults_and_unknown_option():
    from dgenies.lib.exceptions import DGeniesUnknownOptionError
    from dgenies.tools import Tool, Tools

    tool = Tool(
        name="mapper",
        exec="/bin/mapper",
        command_line="{exe} {target} {query} -o {out}",
        all_vs_all=None,
        max_memory=4,
        options=[
            {
                "group": "mode",
                "type": "radio",
                    "entries": [
                        {"key": "fast", "label": "Fast", "value": "--fast", "default": True},
                        {"key": "slow", "label": "Slow", "value": "--slow"},
                ],
            },
            {
                "group": "extra",
                "type": "checkbox",
                "entries": [{"key": "cigar", "label": "Cigar", "value": "-c"}],
            },
        ],
    )

    assert tool.label == "mapper"
    assert tool.resolve_option_keys(["mode:fast"]) == ["--fast"]
    assert tool.get_default_options([]) == ["mode:fast"]
    assert tool.get_default_options(["mode:slow"]) == []
    with pytest.raises(DGeniesUnknownOptionError):
        tool.resolve_option_keys(["mode:missing"])

    assert Tools().get_default() == "minimap2"
    with pytest.raises(ValueError):
        Tool("bad", "x", "{exe} {target}", None, 1)


def test_database_module_initializes_expected_webserver_models():
    import dgenies.database as database

    database.initialize()

    assert database.ID_JOB_LENGTH == 50
    assert hasattr(database, "Job")
    assert hasattr(database, "Session")


def test_package_set_logger_configures_without_error():
    import dgenies

    dgenies.set_logger("DEBUG")
    assert dgenies.VERSION == "1.5.0"


def test_datafile_create_clone_and_mutators():
    from dgenies.lib.datafile import DataFile

    datafile = DataFile.create("Query", "https://example.org/query.fa")
    assert datafile.get_type() == "URL"
    assert datafile.get_name() == "Query"
    assert not datafile.is_example()

    datafile.set_file_size(123)
    clone = datafile.clone()
    clone.set_path("/tmp/query.fa")
    clone.set_name("Query 2")
    clone.set_type("local")

    assert datafile.get_path() == "https://example.org/query.fa"
    assert clone.get_path() == "/tmp/query.fa"
    assert clone.get_file_size() == 123
    assert "DataFile(name=Query" in str(datafile)
    assert DataFile.create("Example", "example://query.fa").is_example()


def test_upload_file_serializes_upload_outcomes():
    from dgenies.lib.upload_file import UploadFile

    assert UploadFile("image.png", "image/png", 12).get_file()["url"] == "data/image.png"
    assert UploadFile("query.fa", "text/plain", 20).get_file()["name"] == "query.fa"
    assert UploadFile("bad.exe", "application/x-msdownload", 4, "not allowed").get_file() == {
        "error": "not allowed",
        "name": "bad.exe",
        "type": "application/x-msdownload",
        "size": 4,
    }
    assert UploadFile("existing.fa", size=42).get_file() == {
        "name": "existing.fa",
        "size": 42,
        "url": "data/existing.fa",
    }


def test_singleton_decorator_returns_same_instance():
    from dgenies.lib.decorators import Singleton

    calls = []

    @Singleton
    class Demo:
        def __init__(self, value):
            calls.append(value)
            self.value = value

    assert Demo("first") is Demo("second")
    assert Demo("ignored").value == "first"
    assert calls == ["first"]


def test_mailer_builds_message_or_reads_environment(monkeypatch):
    from dgenies.lib.mailer import Mailer

    app = SimpleNamespace(config={})
    monkeypatch.setenv("MAIL_SERVER", "smtp.example.org")
    monkeypatch.setenv("MAIL_PORT", "2525")
    Mailer.set_config_from_env(app)
    assert app.config["MAIL_SERVER"] == "smtp.example.org"
    assert app.config["MAIL_PORT"] == "2525"

    sent = []
    mailer = object.__new__(Mailer)
    mailer.config = SimpleNamespace(
        mail_org="D-Genies",
        mail_status_sender="status@example.org",
        mail_reply="reply@example.org",
        disable_mail=False,
    )
    mailer._send_async_email = sent.append
    mailer.send_mail(["user@example.org"], "Subject", "Body", "<p>Body</p>")

    assert sent[0].subject == "Subject"
    assert sent[0].recipients == ["user@example.org"]
    assert sent[0].sender == "D-Genies <status@example.org>"


def test_crons_python_exec_normalizes_site_packages_bin(monkeypatch):
    from dgenies.lib.crons import Crons

    monkeypatch.setattr(sys, "executable", "/opt/env/lib/python3.14/site-packages/bin/python")
    assert Crons._get_python_exec() == "/opt/env/bin/python3.14"

    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    assert Crons._get_python_exec() == "/usr/bin/python3"


def test_drmaa_session_uses_drmaa_module_when_available(monkeypatch):
    fake_drmaa = types.ModuleType("drmaa")
    events = []

    class FakeSession:
        def initialize(self):
            events.append("initialize")

        def exit(self):
            events.append("exit")

    fake_drmaa.Session = FakeSession
    monkeypatch.setitem(sys.modules, "drmaa", fake_drmaa)
    sys.modules.pop("dgenies.lib.drmaasession", None)

    module = importlib.import_module("dgenies.lib.drmaasession")
    module.DrmaaSession.instance = None
    session = module.DrmaaSession()
    session.exit()

    assert events == ["initialize", "exit"]


def test_latest_loads_cache_and_updates_from_release_api(tmp_path, monkeypatch):
    import json
    from dgenies.lib.latest import Latest

    latest = object.__new__(Latest)
    latest._save_latest = str(tmp_path / ".latest")
    latest.latest = ""
    latest.win32 = ""
    (tmp_path / ".latest").write_text("1.2.3\nhttps://example.org/dgenies.exe\n")
    async_calls = []
    monkeypatch.setattr(Latest, "update_async", lambda self: async_calls.append((self.latest, self.win32)))

    latest.load()

    assert latest.latest == "1.2.3"
    assert latest.win32 == "https://example.org/dgenies.exe"
    assert async_calls == [("1.2.3", "https://example.org/dgenies.exe")]

    class Response:
        ok = True
        content = json.dumps(
            {
                "tag_name": "v2.0.0",
                "assets": [
                    {"name": "dgenies.tar.gz", "browser_download_url": "tar"},
                    {"name": "dgenies.exe", "browser_download_url": "exe-url"},
                ],
            }
        ).encode("utf-8")

    monkeypatch.setattr("dgenies.lib.latest.requests.get", lambda url: Response())
    latest.update()

    assert latest.latest == "2.0.0"
    assert latest.win32 == "exe-url"
    assert (tmp_path / ".latest").read_text() == "2.0.0\nexe-url"


@pytest.mark.parametrize(
    "factory, expected, clear_job",
    [
        (lambda e: e.DGeniesUnknownOptionError("x"), "Option unavailable: x", False),
        (lambda e: e.DGeniesUnknownToolError("mapper"), "Tool unavailable: mapper", False),
        (lambda e: e.DGeniesNotGzipFileError("query.gz"), "query.gz file is not a correct gzip file", True),
        (
            lambda e: e.DGeniesUploadedFileSizeLimitError("query.fa", 10),
            "query.fa file exceed size limit of 10 Mb (uncompressed)",
            True,
        ),
        (lambda e: e.DGeniesAlignmentFileUnsupported(), "Alignment file format not supported", False),
        (lambda e: e.DGeniesIndexFileInvalid("Query"), "Query index file is invalid", False),
        (lambda e: e.DGeniesFastaFileInvalid("Query", "bad"), "Query fasta file is invalid:<br/>bad", False),
        (lambda e: e.DGeniesURLInvalid("http://bad"), "Url http://bad is not valid", False),
        (lambda e: e.DGeniesBatchFileError(["line 1"]), "You provided a malformed batch file; line 1", False),
        (lambda e: e.DGeniesMissingParserError("sam"), "No parser found for format sam", False),
        (lambda e: e.DGeniesExampleInvalid("query.fa"), "Invalid example: example://query.fa", False),
    ],
)
def test_exception_messages(factory, expected, clear_job):
    import dgenies.lib.exceptions as exc

    error = factory(exc)
    assert str(error) == expected
    assert error.message
    assert error.clear_job is clear_job


def test_datamodels_and_job_descriptions_construct_defaults(launched_app):
    from dgenies.api import datamodels
    from dgenies.api.job_descriptions import generate_tool_description, job_descriptions
    from dgenies.tools import Tools

    assert datamodels.BaseResponse().model_dump() == {"code": 0, "message": "ok"}
    assert datamodels.NotFoundResponse().message == "Resource not found!"
    job = datamodels.Job(
        job_id="job1",
        type=datamodels.JobType.align,
        target="target.fa",
        target_type=datamodels.FileType.local,
    )
    assert job.tool_options == []

    desc = generate_tool_description(Tools().tools["minimap2"])
    assert desc.name == "minimap2"
    assert desc.needs[0] == [datamodels.InputType.query, datamodels.InputType.target]
    assert {j.type for j in job_descriptions} == {datamodels.JobType.align, datamodels.JobType.plot}
