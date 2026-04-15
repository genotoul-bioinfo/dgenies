"""Tool loading, latest version, mailer, and DRMAA integration tests."""

import json
from types import SimpleNamespace

import pytest
from flask import Flask

from dgenies.lib.exceptions import DGeniesUnknownOptionError

# This file was split out from src/dgenies/test_dgenies_api.py.

"""
Verifies the Tool and Tools modules, focusing on object instantiation, parameter validation, and configuration discovery across different operating systems.

Ensure that:
1. The Tool class correctly resolves executable paths (handling both default and explicit placeholders) and parses complex command-line templates, including radio/checkbox options.
2. Strict input validation is enforced during Tool creation for all critical parameters, such as thread counts, memory limits, template syntax, and option structures.
3. The Tools loader successfully identifies tool definitions from both provided YAML files and user home directory defaults (e.g., ~/.dgenies/tools.yaml).
4. Platform-specific logic correctly adjusts executable pathing and architecture-dependent defaults when switching between Linux and Darwin environments.
"""
def test_tools_module_loading_and_validation(monkeypatch, tmp_path):
    import dgenies.tools as tools_module

    monkeypatch.setattr(tools_module.sys, "platform", "linux", raising=False)
    monkeypatch.setattr(tools_module.platform, "machine", lambda: "x86_64", raising=False)
    linux_tool = tools_module.Tool(
        name="minimap2",
        exec="default",
        command_line="{exe} -t {target} -q {query} -o {out}",
        all_vs_all="{exe} -t {target} -o {out}",
        max_memory=8,
        parser="maf",
        options=[
            {
                "group": "preset",
                "type": "radio",
                "entries": [
                    {"key": "asm", "value": "--asm", "default": True},
                    {"key": "map", "value": "--map", "default": True},
                ],
            },
            {
                "group": "extra",
                "type": "checkbox",
                "entries": [
                    {"key": "cigar", "value": "-c", "default": True},
                ],
            },
        ],
    )
    assert linux_tool.label == "minimap2"
    assert linux_tool.exec.endswith("/bin/minimap2")
    assert linux_tool.exec_cluster == "default"
    assert linux_tool.order == 1000
    assert set(linux_tool.get_options_keys()) == {"preset:asm", "preset:map", "extra:cigar"}
    assert linux_tool.resolve_option_keys(["preset:asm", "extra:cigar"]) == ["--asm", "-c"]
    assert linux_tool.get_default_options([]) == ["preset:asm", "preset:map", "extra:cigar"]
    assert linux_tool.get_default_options(["preset:map"]) == ["extra:cigar"]
    with pytest.raises(DGeniesUnknownOptionError):
        linux_tool.resolve_option_keys(["preset:missing"])

    monkeypatch.setattr(tools_module.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(tools_module.platform, "machine", lambda: "arm64", raising=False)
    fallback_tool = tools_module.Tool(
        name="mashmap",
        exec="default",
        command_line="{exe} -t {target} -q {query} -o {out}",
        all_vs_all=None,
        max_memory=None,
        threads=2,
        threads_cluster=4,
        split_before=True,
    )
    assert fallback_tool.exec == "mashmap"
    assert fallback_tool.threads_cluster == 4
    assert fallback_tool.split_before is True

    explicit_tool = tools_module.Tool(
        name="mapper",
        exec="###SYSEXEC###/mapper",
        exec_cluster="###SYSEXEC###/mapper-cluster",
        command_line="{exe} -t {target} -q {query} -o {out}",
        all_vs_all="{exe} -t {target} -o {out}",
        max_memory=4,
        label="Mapper",
        order=3,
    )
    assert explicit_tool.label == "Mapper"
    assert explicit_tool.exec.endswith("/mapper")
    assert explicit_tool.exec_cluster.endswith("/mapper-cluster")
    assert explicit_tool.order == 3

    with pytest.raises(ValueError, match="command_line"):
        tools_module.Tool("bad", "default", "{exe}", None, 1)
    with pytest.raises(ValueError, match="all_vs_all"):
        tools_module.Tool("bad", "default", "{exe} {target} {query} {out}", "{exe}", 1)
    with pytest.raises(ValueError, match="max_memory"):
        tools_module.Tool("bad", "default", "{exe} {target} {query} {out}", None, "4G")
    with pytest.raises(ValueError, match="threads must be an integer"):
        tools_module.Tool("bad", "default", "{exe} {target} {query} {out}", None, 1, threads="2")
    with pytest.raises(ValueError, match="threads_cluster"):
        tools_module.Tool("bad", "default", "{exe} {target} {query} {out}", None, 1, threads_cluster="4")
    with pytest.raises(ValueError, match="parser missing is not defines"):
        tools_module.Tool("bad", "default", "{exe} {target} {query} {out}", None, 1, parser="missing")
    with pytest.raises(ValueError, match="split_before"):
        tools_module.Tool("bad", "default", "{exe} {target} {query} {out}", None, 1, split_before="yes")
    with pytest.raises(ValueError, match="options must be a yaml list"):
        tools_module.Tool("bad", "default", "{exe} {target} {query} {out}", None, 1, options={"group": "x"})
    with pytest.raises(ValueError, match="Missing key value"):
        tools_module.Tool(
            "bad",
            "default",
            "{exe} {target} {query} {out}",
            None,
            1,
            options=[{"group": "preset", "type": "radio", "entries": [{"key": "asm"}]}],
        )

    yaml_file = tmp_path / "tools.yaml"
    yaml_file.write_text(
        "first:\n"
        "  exec: default\n"
        "  command_line: \"{exe} -t {target} -q {query} -o {out}\"\n"
        "  all_vs_all: \"{exe} -t {target} -o {out}\"\n"
        "  max_memory: 2\n"
        "  order: 5\n"
        "second:\n"
        "  exec: default\n"
        "  command_line: \"{exe} -t {target} -q {query} -o {out}\"\n"
        "  all_vs_all: null\n"
        "  max_memory: 1\n"
        "  order: 1\n"
    )
    monkeypatch.setattr(tools_module.Tools, "instance", None, raising=False)
    loaded_tools = tools_module.Tools(config_file=str(yaml_file))
    assert set(loaded_tools.tools) == {"first", "second"}
    assert loaded_tools.get_default() == "second"

    nt_home = tmp_path / "home"
    (nt_home / ".dgenies").mkdir(parents=True)
    nt_yaml = nt_home / ".dgenies" / "tools.yaml"
    nt_yaml.write_text(yaml_file.read_text())
    monkeypatch.setattr(tools_module.Path, "home", classmethod(lambda cls: nt_home), raising=False)
    monkeypatch.setattr(tools_module.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        tools_module.os.path,
        "exists",
        lambda path: str(path) == str(nt_yaml),
        raising=False,
    )
    monkeypatch.setattr(tools_module.Tools, "instance", None, raising=False)
    nt_tools = tools_module.Tools()
    assert nt_tools.get_default() == "second"

    monkeypatch.setattr(tools_module.Tools, "instance", None, raising=False)
    monkeypatch.setattr(tools_module.os.path, "exists", lambda _path: False, raising=False)
    with pytest.raises(FileNotFoundError, match="tools.yaml not found"):
        tools_module.Tools()

"""
Tests the functionality of version tracking, automated email notification, and DRMAA session management utilities.

Ensure that:
1. The Latest module accurately retrieves, parses, and caches software release metadata while remaining resilient to network connectivity issues during background updates.
2. The Mailer service correctly implements SMTP configuration from environment variables and supports both direct message dispatch as well as suppressed or entirely disabled sending modes.
3. DRMAA session management follows the expected lifecycle of initialization and termination.
"""
def test_latest_mailer_and_drmaa_helpers(monkeypatch, tmp_path, capsys):
    import dgenies.lib.drmaasession as drmaa_module
    import dgenies.lib.latest as latest_module
    import dgenies.lib.mailer as mailer_module

    monkeypatch.setattr(latest_module, "AppConfigReader", lambda: SimpleNamespace(config_dir=str(tmp_path)), raising=False)

    class FakeResponse:
        def __init__(self, payload):
            self.ok = True
            self.content = json.dumps(payload).encode("utf-8")

    release_calls = []
    monkeypatch.setattr(
        latest_module.requests,
        "get",
        lambda _url: release_calls.append("called") or FakeResponse({
            "tag_name": "v2.1.0",
            "assets": [
                {"name": "dgenies-macos.tar.gz", "browser_download_url": "https://example.org/macos"},
                {"name": "dgenies-win32.exe", "browser_download_url": "https://example.org/win32.exe"},
            ],
        }),
        raising=False,
    )
    latest = latest_module.Latest()
    assert latest.latest == "2.1.0"
    assert latest.win32 == "https://example.org/win32.exe"
    assert (tmp_path / ".latest").read_text() == "2.1.0\nhttps://example.org/win32.exe"
    assert release_calls == ["called"]

    timers = []

    class FakeTimer:
        def __init__(self, interval, func):
            self.interval = interval
            self.func = func
            timers.append(self)

        def start(self):
            timers.append("started")

    monkeypatch.setattr(latest_module.threading, "Timer", FakeTimer, raising=False)
    release_calls.clear()
    second_latest = latest_module.Latest()
    assert second_latest.latest == "2.1.0"
    assert timers[0].interval == 1
    assert timers[0].func == second_latest.update
    assert "started" in timers
    assert release_calls == []

    (tmp_path / ".latest").write_text("2.1.0\n")
    release_calls.clear()
    repaired_latest = latest_module.Latest()
    assert repaired_latest.win32 == "https://example.org/win32.exe"
    assert release_calls == ["called"]

    monkeypatch.setattr(
        latest_module.requests,
        "get",
        lambda _url: (_ for _ in ()).throw(ConnectionError("offline")),
        raising=False,
    )
    repaired_latest.update()
    assert repaired_latest.latest == "2.1.0"

    sent_messages = []

    class FakeMail:
        def __init__(self, app):
            self.app = app

        def send(self, msg):
            sent_messages.append(msg)

    class FakeMessage:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setattr(mailer_module, "Mail", FakeMail, raising=False)
    monkeypatch.setattr(mailer_module, "Message", FakeMessage, raising=False)
    monkeypatch.setattr(
        mailer_module,
        "AppConfigReader",
        lambda: SimpleNamespace(
            mail_org="DGenies",
            mail_status_sender="sender@example.org",
            mail_reply="reply@example.org",
            disable_mail=False,
        ),
        raising=False,
    )
    monkeypatch.setenv("MAIL_SERVER", "smtp.example.org")
    monkeypatch.setenv("MAIL_SUPPRESS_SEND", "1")
    app = Flask(__name__)
    enabled_mailer = mailer_module.Mailer(app)
    assert app.config["MAIL_SERVER"] == "smtp.example.org"
    assert app.config["MAIL_SUPPRESS_SEND"] == "1"

    fake_msg = FakeMessage(subject="Direct", recipients=["a@example.org"], body="body", html=None, sender=None, reply_to=None)
    enabled_mailer._send_async_email(fake_msg)
    assert sent_messages[-1].subject == "Direct"

    enabled_mailer.send_mail(["to@example.org"], "Subject", "Plain body", "<b>html</b>")
    assert sent_messages[-1].subject == "Subject"
    assert sent_messages[-1].sender == ("DGenies", "sender@example.org")
    assert sent_messages[-1].reply_to == "reply@example.org"

    monkeypatch.setattr(
        mailer_module,
        "AppConfigReader",
        lambda: SimpleNamespace(
            mail_org=None,
            mail_status_sender="sender@example.org",
            mail_reply="reply@example.org",
            disable_mail=True,
        ),
        raising=False,
    )
    disabled_mailer = mailer_module.Mailer(Flask(__name__))
    disabled_mailer.send_mail(["to@example.org"], "Disabled", "Body", "<p>Body</p>")
    captured = capsys.readouterr().out
    assert "SEND MAILS DISABLED BY CONFIGURATION" in captured
    assert "Disabled" in captured

    drmaa_calls = []

    class FakeDrmaaSession:
        def initialize(self):
            drmaa_calls.append("initialize")

        def exit(self):
            drmaa_calls.append("exit")

    monkeypatch.setattr(drmaa_module, "drmaa", SimpleNamespace(Session=lambda: drmaa_calls.append("session") or FakeDrmaaSession()), raising=False)
    monkeypatch.setattr(drmaa_module.DrmaaSession, "instance", None, raising=False)
    drmaa_session = drmaa_module.DrmaaSession()
    assert drmaa_calls == ["session", "initialize"]
    drmaa_session.exit()
    assert drmaa_calls == ["session", "initialize", "exit"]
