"""Tests covering package bootstrap and app launch flows."""

from __future__ import annotations

import logging
import importlib
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_set_logger_and_launch_cover_bootstrap_paths(monkeypatch, tmp_path):
    import dgenies
    tools_module = importlib.import_module("dgenies.tools")

    dgenies.set_logger("DEBUG")
    assert logging.getLogger("dgenies").handlers

    class FakeConfig(dict):
        def from_pyfile(self, path):
            self["FROM_PYFILE"] = path

    class FakeOpenAPI:
        def __init__(self, name, static_url_path):
            self.name = name
            self.static_url_path = static_url_path
            self.config = FakeConfig()
            self.registered_api = None

        def register_api(self, api):
            self.registered_api = api

    fake_flask_openapi3 = ModuleType("flask_openapi3")
    fake_flask_openapi3.OpenAPI = FakeOpenAPI
    monkeypatch.setitem(sys.modules, "flask_openapi3", fake_flask_openapi3)

    fake_api_module = ModuleType("dgenies.api")
    fake_api_module.api = "fake-api"
    monkeypatch.setitem(sys.modules, "dgenies.api", fake_api_module)
    monkeypatch.setitem(sys.modules, "dgenies.views", ModuleType("dgenies.views"))

    tools_calls = []
    monkeypatch.setattr(tools_module, "Tools", lambda config_file=None: tools_calls.append(config_file), raising=False)

    data_root = tmp_path / "data"
    log_dir = tmp_path / "logs"
    upload_root = tmp_path / "uploads"
    config_object = SimpleNamespace(
        upload_folder=str(upload_root),
        app_data=str(data_root),
        max_upload_file_size=12345,
        debug=True,
        log_dir=str(log_dir),
    )
    monkeypatch.setattr(dgenies, "AppConfigReader", lambda config: config_object, raising=False)

    app = dgenies.launch(
        mode="standalone",
        config=["application.properties"],
        tools_config="tools.yaml",
        flask_config="flask_config.py",
        debug=True,
    )

    assert isinstance(app, FakeOpenAPI)
    assert app.static_url_path == "/static"
    assert app.config["UPLOAD_FOLDER"] == str(upload_root)
    assert app.config["MAX_CONTENT_LENGTH"] == 12345
    assert app.config["FROM_PYFILE"] == "flask_config.py"
    assert app.registered_api == "fake-api"
    assert tools_calls == ["tools.yaml"]
    assert data_root.exists()
    assert log_dir.exists()
    assert dgenies.MODE == "standalone"
    assert dgenies.DEBUG is True
    assert dgenies.app is app
    assert dgenies.APP_DATA == str(data_root)
    assert dgenies.app_title.startswith("D-GENIES")

    database_calls = []
    database_module = importlib.import_module("dgenies.database")
    monkeypatch.setattr(database_module, "initialize", lambda: database_calls.append("initialize"), raising=False)

    mailer_module = importlib.import_module("dgenies.lib.mailer")
    mailer_calls = []
    monkeypatch.setattr(mailer_module, "Mailer", lambda app_instance: mailer_calls.append(app_instance) or "mailer", raising=False)

    cron_calls = []

    class FakeCrons:
        def __init__(self, base_dir, debug):
            cron_calls.append((base_dir, debug))

        def start_all(self):
            cron_calls.append("started")

    monkeypatch.setattr(dgenies, "Crons", FakeCrons, raising=False)
    monkeypatch.setenv("LOGS", "True")
    monkeypatch.delenv("DISABLE_CRONS", raising=False)

    web_config = SimpleNamespace(
        upload_folder=str(upload_root),
        app_data=str(data_root),
        max_upload_file_size=67890,
        debug=False,
        log_dir="stdout",
    )
    monkeypatch.setattr(dgenies, "AppConfigReader", lambda config: web_config, raising=False)

    web_app = dgenies.launch(mode="webserver", config=["application.properties"])

    assert database_calls == ["initialize"]
    assert mailer_calls == [web_app]
    assert cron_calls[0][0] == dgenies.app_folder
    assert cron_calls[0][1] is True
    assert cron_calls[1] == "started"
    assert dgenies.mailer == "mailer"
