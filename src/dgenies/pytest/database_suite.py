"""Database initialization and session lifecycle tests."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest


def test_database_webserver_initialize_and_session_flow(monkeypatch, tmp_path):
    import dgenies
    config_reader_module = importlib.import_module("dgenies.config_reader")
    functions_module = importlib.import_module("dgenies.lib.functions")

    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    config = SimpleNamespace(
        upload_folder=str(upload_root),
        max_download_sessions=1,
        analytics_enabled=True,
        database_type="sqlite",
        database_url=str(tmp_path / "database.sqlite"),
        database_db="dgenies",
        database_port=3306,
        database_user="user",
        database_password="secret",
    )

    monkeypatch.setattr(dgenies, "MODE", "webserver", raising=False)
    monkeypatch.setattr(config_reader_module, "AppConfigReader", lambda: config, raising=False)
    monkeypatch.setattr(functions_module.Functions, "random_string", staticmethod(lambda length: "x" * length), raising=False)
    sys.modules.pop("dgenies.database", None)
    database = importlib.import_module("dgenies.database")

    database.initialize()

    with database.Job.connect():
        created = database.Job.create(id_job="job1", email="user@example.org", date_created=datetime.now())
        assert created.id_job == "job1"
        analytics = database.Analytics.create(
            id_job="job1",
            date_created=datetime.now(),
            target_size=12,
            query_size=6,
            mail_client="tester",
            runner_type="local",
        )
        assert analytics.id_job == "job1"

    session_id = database.Session.new(keep_active=True)
    assert session_id == "x" * 20
    session = database.Session.get(database.Session.s_id == session_id)
    assert session.keep_active is True
    assert session.ask_for_upload(change_status=True) is True
    assert session.status == "active"

    second = database.Session.create(
        s_id="second-session",
        date_created=datetime.now(),
        upload_folder="upload-2",
        last_ping=datetime.now(),
        status="reset",
    )
    assert second.ask_for_upload(change_status=True) is False
    assert second.status == "pending"
    second.status = "active"
    assert second.ask_for_upload(change_status=False) is True

    old_ping = session.last_ping
    session.last_ping = old_ping - timedelta(seconds=5)
    session.ping()
    assert session.last_ping > old_ping

    class BaseDatabase:
        def execute_sql(self, sql, params=None, commit=True):
            raise database.OperationalError("retry me")

    class DummyCursor:
        def execute(self, sql, params):
            self.sql = sql
            self.params = params

    class DummyRetryDB(database.RetryOperationalError, BaseDatabase):
        def __init__(self):
            self.closed = False
            self.committed = False
            self.cursor_calls = 0

        def is_closed(self):
            return self.closed

        def close(self):
            self.closed = True

        def cursor(self):
            self.cursor_calls += 1
            return DummyCursor()

        def in_transaction(self):
            return False

        def commit(self):
            self.committed = True

    retry_db = DummyRetryDB()
    retry_cursor = retry_db.execute_sql("SELECT 1", params=(1,))
    assert retry_db.closed is True
    assert retry_db.committed is True
    assert retry_db.cursor_calls == 1
    assert retry_cursor.params == (1,)

    config.database_type = "unsupported"
    with pytest.raises(Exception, match="Unsupported database type"):
        database.initialize()
    database.database_proxy.close()


def test_database_standalone_mode_exposes_noop_models(monkeypatch):
    import dgenies
    config_reader_module = importlib.import_module("dgenies.config_reader")

    monkeypatch.setattr(dgenies, "MODE", "standalone", raising=False)
    monkeypatch.setattr(config_reader_module, "AppConfigReader", lambda: SimpleNamespace(), raising=False)
    sys.modules.pop("dgenies.database", None)
    database = importlib.import_module("dgenies.database")

    with database.Job.connect():
        assert database.Database.nb_open == 0
    assert database.initialize() is None


def test_database_session_collision_and_mysql_initialize(monkeypatch, tmp_path):
    import dgenies

    config_reader_module = importlib.import_module("dgenies.config_reader")
    functions_module = importlib.import_module("dgenies.lib.functions")

    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    config = SimpleNamespace(
        upload_folder=str(upload_root),
        max_download_sessions=2,
        analytics_enabled=False,
        database_type="sqlite",
        database_url=str(tmp_path / "database.sqlite"),
        database_db="dgenies",
        database_port=3307,
        database_user="dbuser",
        database_password="secret",
    )

    monkeypatch.setattr(dgenies, "MODE", "webserver", raising=False)
    monkeypatch.setattr(config_reader_module, "AppConfigReader", lambda: config, raising=False)
    sys.modules.pop("dgenies.database", None)
    database = importlib.import_module("dgenies.database")
    database.initialize()

    database.Session.create(
        s_id="dup-session",
        date_created=datetime.now(),
        upload_folder="existing-folder",
        last_ping=datetime.now(),
        status="reset",
    )
    (upload_root / "dup-folder").mkdir()

    generated = iter(["dup-session", "fresh-session", "dup-folder", "fresh-folder"])
    monkeypatch.setattr(functions_module.Functions, "random_string", staticmethod(lambda _size: next(generated)), raising=False)
    new_session_id = database.Session.new()
    created = database.Session.get(database.Session.s_id == new_session_id)
    assert new_session_id == "fresh-session"
    assert created.upload_folder == "fresh-folder"
    database.database_proxy.close()

    created_tables = []
    initialized = {}
    config.database_type = "mysql"
    monkeypatch.setattr(database, "MyRetryDB", lambda **kwargs: kwargs, raising=False)
    monkeypatch.setattr(database, "database_proxy", SimpleNamespace(initialize=lambda db_obj: initialized.update(db=db_obj)), raising=False)
    monkeypatch.setattr(database.Job, "create_table", classmethod(lambda cls, safe=True: created_tables.append(("job", safe))), raising=False)
    monkeypatch.setattr(database.Gallery, "create_table", classmethod(lambda cls, safe=True: created_tables.append(("gallery", safe))), raising=False)
    monkeypatch.setattr(database.Session, "create_table", classmethod(lambda cls, safe=True: created_tables.append(("session", safe))), raising=False)

    database.initialize()
    assert initialized["db"]["database"] == "dgenies"
    assert initialized["db"]["host"] == config.database_url
    assert initialized["db"]["port"] == config.database_port
    assert initialized["db"]["user"] == config.database_user
    assert initialized["db"]["passwd"] == config.database_password
    assert created_tables == [("job", True), ("gallery", True), ("session", True)]
