"""Configuration reader regression tests."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


def _reset_config_singleton(monkeypatch, module) -> None:
    monkeypatch.setattr(module.AppConfigReader, "instance", None, raising=False)

"""
Verifies that the AppConfigReader correctly parses complex configuration properties and integrates environment variable overrides.

Ensure that:
1. Configuration values from various sections (global, database, cluster, etc.) are accurately loaded as their intended types (e.g., integers, booleans, paths, or time durations).
2. Environment variables successfully override or supplement the settings defined in the properties file.
3. Placeholder replacement logic correctly resolves relative paths using the application's configuration directory.
4. The parser robustly handles error cases, such as unsupported size units or invalid tag usage, by raising appropriate exceptions.
"""
def test_config_reader_reads_explicit_values_and_env_overrides(monkeypatch, tmp_path):
    config_reader_module = importlib.import_module("dgenies.config_reader")

    config_dir = tmp_path / "config"
    upload_dir = tmp_path / "uploads"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    upload_dir.mkdir()
    data_dir.mkdir()
    log_dir = tmp_path / "logs"
    legal_page = tmp_path / "terms.md"
    legal_page.write_text("# Terms\n")

    config_file = tmp_path / "application.properties"
    config_file.write_text(
        "[global]\n"
        f"config_dir={config_dir}\n"
        f"upload_folder={upload_dir}\n"
        f"data_folder={data_dir}\n"
        "runner_type=cluster\n"
        "web_url=https://config.example.org\n"
        "send_mail_url=https://notify.example.org\n"
        "max_upload_size=2G\n"
        "max_upload_size_ava=3G\n"
        "max_upload_file_size=4G\n"
        "max_nb_lines=123\n"
        "max_nb_jobs_in_batch_mode=7\n"
        "\n"
        "[session]\n"
        "max_download_sessions=2\n"
        "delete_allowed_session_delay=60\n"
        "reset_pending_session_delay=40\n"
        "delete_session_delay=120\n"
        "\n"
        "[database]\n"
        "type=mysql\n"
        "url=db.example.org\n"
        "port=3307\n"
        "db=dgenies\n"
        "user=dbuser\n"
        "password=dbpass\n"
        "\n"
        "[mail]\n"
        "status=status@example.org\n"
        "reply=reply@example.org\n"
        "org=INRAE\n"
        "send_mail_status=false\n"
        "disable=true\n"
        "\n"
        "[cron]\n"
        "clean_time=23h15\n"
        "clean_freq=3\n"
        "\n"
        "[jobs]\n"
        "run_local=4\n"
        "data_prepare=6\n"
        "max_concurrent_dl=8\n"
        "\n"
        "[cluster]\n"
        "drmaa_lib_path=/opt/libdrmaa.so\n"
        "native_specs=-pe smp 4\n"
        "max_run_local=9\n"
        "max_wait_local=11\n"
        "min_query_size=2G\n"
        "min_target_size=3G\n"
        "prepare_script=###PROGRAM###/prep.py\n"
        "python3_exec=###SYSEXEC###/python3\n"
        "memory=64\n"
        "memory_ava=96\n"
        "walltime=05:00:00\n"
        "walltime_prepare=01:00:00\n"
        "walltime_align=06:00:00\n"
        "\n"
        "[debug]\n"
        "enable=true\n"
        f"log_dir={log_dir}\n"
        "allowed_ip_tests=192.168.0.1,10.0.0.1\n"
        "\n"
        "[example]\n"
        "query=query.fa.gz\n"
        "target=target.fa.gz\n"
        "\n"
        "[analytics]\n"
        "disable_anonymous_analytics=false\n"
        "anonymous_analytics=full\n"
        "\n"
        "[analytics_groups]\n"
        "staff=.*@example.org\n"
        "\n"
        "[legal]\n"
        f"cookie_wall={tmp_path / 'cookie.md'}\n"
        f"terms={legal_page}\n"
    )

    monkeypatch.setenv("EXAMPLE_BACKUP", "backup.tar.gz")
    monkeypatch.setenv("EXAMPLE_BATCH", "batch.txt")
    monkeypatch.setenv("ANALYTICS", "true")
    _reset_config_singleton(monkeypatch, config_reader_module)
    reader = config_reader_module.AppConfigReader([str(config_file)])

    assert reader.config_dir == str(config_dir)
    assert reader.upload_folder == str(upload_dir)
    assert reader.app_data == str(data_dir)
    assert reader.runner_type == "cluster"
    assert reader.web_url == "https://config.example.org"
    assert reader.send_mail_url == "https://notify.example.org"
    assert reader.max_upload_size == 2 * 1024 * 1024 * 1024
    assert reader.max_upload_size_ava == 3 * 1024 * 1024 * 1024
    assert reader.max_upload_file_size == 4 * 1024 * 1024 * 1024
    assert reader.max_nb_lines == 123
    assert reader.max_nb_jobs_in_batch_mode == 7
    assert reader.max_download_sessions == 2
    assert reader.database_type == "mysql"
    assert reader.database_url == "db.example.org"
    assert reader.database_port == 3307
    assert reader.database_db == "dgenies"
    assert reader.database_user == "dbuser"
    assert reader.database_password == "dbpass"
    assert reader.mail_status_sender == "status@example.org"
    assert reader.mail_reply == "reply@example.org"
    assert reader.mail_org == "INRAE"
    assert reader.send_mail_status is False
    assert reader.disable_mail is True
    assert reader.cron_clean_time == [23, 15]
    assert reader.cron_clean_freq == 3
    assert reader.local_nb_runs == 4
    assert reader.nb_data_prepare == 6
    assert reader.max_concurrent_dl == 8
    assert reader.drmaa_lib_path == "/opt/libdrmaa.so"
    assert reader.drmaa_native_specs == "-pe smp 4"
    assert reader.max_run_local == 9
    assert reader.max_wait_local == 11
    assert reader.min_query_size == 2 * 1024 * 1024 * 1024
    assert reader.min_target_size == 3 * 1024 * 1024 * 1024
    assert reader.cluster_prepare_script.endswith("/prep.py")
    assert reader.cluster_python_exec.endswith("/python3")
    assert reader.cluster_memory == 64
    assert reader.cluster_memory_ava == 96
    assert reader.cluster_walltime == "05:00:00"
    assert reader.cluster_walltime_prepare == "01:00:00"
    assert reader.cluster_walltime_align == "06:00:00"
    assert reader.debug is True
    assert reader.log_dir == str(log_dir)
    assert "192.168.0.1" in reader.allowed_ip_tests
    assert reader.example_query == "query.fa.gz"
    assert reader.example_target == "target.fa.gz"
    assert reader.example_backup == "backup.tar.gz"
    assert reader.example_batch == "batch.txt"
    assert reader.analytics_enabled is True
    assert reader.disable_anonymous_analytics is True
    assert reader.anonymous_analytics == "full"
    assert reader.analytics_groups == [("staff", ".*@example.org")]
    assert reader.cookie_wall.endswith("cookie.md")
    assert reader.legal == {"terms": str(legal_page)}
    assert "database_password" not in str(reader)
    assert reader._replace_vars("###CONFIG###/logs/test.txt").endswith("config/logs/test.txt")

    with pytest.raises(Exception, match="tag not allowed"):
        reader._replace_vars("###CONFIG###", config=True)

    assert reader._parse_size("-1") == -1
    with pytest.raises(ValueError, match="Max size unit"):
        reader._parse_size("5T")

"""
Tests the fallback mechanisms and error-handling paths of the AppConfigReader.

Ensure that:
1. Default values are correctly applied for all missing configuration properties across various sections (global, database, session, etc.).
2. The application raises appropriate exceptions when encountering malformed data or invalid directory paths (e.g., log directory pointing to a file).
3. Critical errors are triggered when essential parameters, such as the database port, are missing from both the configuration file and environment variables.
4. Environment variable overrides with empty or invalid values are handled according to the expected logic.
"""
def test_config_reader_fallbacks_and_error_paths(monkeypatch, tmp_path):
    config_reader_module = importlib.import_module("dgenies.config_reader")

    config_file = tmp_path / "application.properties"
    config_file.write_text(
        "[global]\n"
        f"upload_folder={tmp_path / 'uploads'}\n"
        f"data_folder={tmp_path / 'data'}\n"
        "\n"
        "[session]\n"
        "\n"
        "[database]\n"
        "type=sqlite\n"
        "\n"
        "[cron]\n"
        "clean_time=bad-format\n"
        "\n"
        "[debug]\n"
        f"log_dir={tmp_path / 'not-a-dir'}\n"
    )
    (tmp_path / "not-a-dir").write_text("file")
    monkeypatch.setenv("DATABASE_PASSWORD", "")
    monkeypatch.setenv("DATABASE_PORT", "-1")

    _reset_config_singleton(monkeypatch, config_reader_module)
    reader = config_reader_module.AppConfigReader([str(config_file)])

    assert reader.runner_type == "local"
    assert reader.web_url == "http://localhost:5000"
    assert reader.send_mail_url == "http://localhost:5000"
    assert reader.max_upload_size == -1
    assert reader.max_upload_size_ava == -1
    assert reader.max_upload_file_size == 1024 * 1024 * 1024
    assert reader.max_download_sessions == 5
    assert reader.delete_allowed_session_delay == 50
    assert reader.reset_pending_session_delay == 30
    assert reader.delete_session_delay == 86400
    assert reader.database_type == "sqlite"
    assert reader.database_port == "-1"
    assert reader.database_db == ""
    assert reader.database_user == ""
    assert reader.database_password == ""
    assert reader.mail_status_sender == "status@dgenies"
    assert reader.mail_reply == "status@dgenies"
    assert reader.mail_org is None
    assert reader.send_mail_status is True
    assert reader.disable_mail is False
    assert reader.cron_clean_time == [1, 0]
    assert reader.cron_clean_freq == 1
    assert reader.local_nb_runs == 1
    assert reader.nb_data_prepare == 2
    assert reader.max_concurrent_dl == 5
    assert reader.drmaa_native_specs == "###DEFAULT###"
    assert reader.max_run_local == 10
    assert reader.max_wait_local == 5
    assert reader.min_query_size == 0
    assert reader.min_target_size == 0
    assert reader.cluster_prepare_script.endswith("/bin/all_prepare.py")
    assert reader.cluster_python_exec == "python3"
    assert reader.cluster_memory == 32
    assert reader.cluster_memory_ava == 32
    assert reader.cluster_walltime == "02:00:00"
    assert reader.cluster_walltime_prepare == "02:00:00"
    assert reader.cluster_walltime_align == "02:00:00"
    assert reader.debug is False
    assert reader.allowed_ip_tests == {"127.0.0.1"}
    assert reader.example_query == ""
    assert reader.example_target == ""
    assert reader.example_backup == ""
    assert reader.example_batch == ""
    assert reader.analytics_enabled is False
    assert reader.anonymous_analytics == "groups"
    assert reader.analytics_groups == []
    assert reader.cookie_wall is None
    assert reader.legal == {}

    with pytest.raises(TypeError, match="Log dir must be a directory"):
        reader._get_log_dir()

    cluster_file = tmp_path / "cluster.properties"
    cluster_file.write_text(
        "[global]\n"
        f"upload_folder={tmp_path / 'uploads-cluster'}\n"
        f"data_folder={tmp_path / 'data-cluster'}\n"
        "runner_type=cluster\n"
    )
    _reset_config_singleton(monkeypatch, config_reader_module)
    cluster_reader = config_reader_module.AppConfigReader([str(cluster_file)])
    with pytest.raises(Exception, match="drmaa library"):
        cluster_reader._get_drmaa_lib_path()

    bad_db_file = tmp_path / "bad-db.properties"
    bad_db_file.write_text(
        "[global]\n"
        f"upload_folder={tmp_path / 'uploads-db'}\n"
        f"data_folder={tmp_path / 'data-db'}\n"
        "\n"
        "[database]\n"
        "type=mysql\n"
        "url=db.example.org\n"
    )
    monkeypatch.delenv("DATABASE_PORT", raising=False)
    _reset_config_singleton(monkeypatch, config_reader_module)
    with pytest.raises(Exception, match="database port"):
        config_reader_module.AppConfigReader([str(bad_db_file)])._get_database_port()


def test_config_reader_missing_file_raises(monkeypatch):
    config_reader_module = importlib.import_module("dgenies.config_reader")

    _reset_config_singleton(monkeypatch, config_reader_module)
    with pytest.raises(FileNotFoundError, match="application.properties not found"):
        config_reader_module.AppConfigReader(["/missing/application.properties"])

"""
Tests the error handling of private methods in AppConfigReader regarding path resolution and database configuration.

Ensure that:
1. Internal helpers raise appropriate exceptions when critical directories (e.g., upload or data folders) are missing or invalid.
2. The database URL can still be correctly extracted even if its parent directory structure is non-existent or uncreatable.
"""
def test_config_reader_private_error_branches_for_paths_and_database_url(monkeypatch, tmp_path):
    config_reader_module = importlib.import_module("dgenies.config_reader")

    config_file = tmp_path / "private-errors.properties"
    config_file.write_text(
        "[global]\n"
        f"config_dir={tmp_path / 'config'}\n"
        "\n"
        "[database]\n"
        "type=sqlite\n"
        f"url={tmp_path / 'missing-parent' / 'db' / 'database.sqlite'}\n"
    )

    _reset_config_singleton(monkeypatch, config_reader_module)
    reader = config_reader_module.AppConfigReader([str(config_file)])

    with pytest.raises(Exception, match="upload folder"):
        reader._get_upload_folder()

    with pytest.raises(Exception, match="data folder"):
        reader._get_app_data()

    real_exists = config_reader_module.os.path.exists
    missing_parent = os.path.dirname(str(tmp_path / "missing-parent" / "db" / "database.sqlite"))
    monkeypatch.setattr(
        config_reader_module.os.path,
        "exists",
        lambda path: False if path == missing_parent else real_exists(path),
        raising=False,
    )
    monkeypatch.setattr(
        config_reader_module.os,
        "makedirs",
        lambda _path: (_ for _ in ()).throw(FileNotFoundError("missing parent")),
        raising=False,
    )
    assert reader._get_database_url().endswith("database.sqlite")

"""
Verifies the configuration discovery mechanism across different operating systems, specifically targeting Windows path resolution logic.

Ensure that:
1. The AppConfigReader correctly identifies default configuration files located relative to the Python executable directory on Windows.
2. Local override files (e.g., .local extensions) are successfully detected within the search path.
3. Global user-level configurations within the home directory (e.g., ~/.dgenies) are properly discovered and included in the loading sequence.
"""
def test_config_reader_discovers_default_and_windows_paths(monkeypatch, tmp_path):
    config_reader_module = importlib.import_module("dgenies.config_reader")

    home_config_dir = tmp_path / ".dgenies"
    home_config_dir.mkdir()
    discovered = home_config_dir / "application.properties"
    discovered.write_text("[global]\n")
    captured = {}
    expected_windows_config = str(tmp_path / "python.exe" / ".." / "application.properties")
    expected_windows_local = str(tmp_path / "python.exe" / ".." / "application.properties.local")
    expected_home_config = str(discovered)
    monkeypatch.setattr(config_reader_module.os, "name", "nt", raising=False)
    monkeypatch.setattr(config_reader_module.sys, "executable", str(tmp_path / "python.exe"), raising=False)
    monkeypatch.setattr(config_reader_module.Path, "home", lambda: tmp_path, raising=False)
    monkeypatch.setattr(
        config_reader_module.inspect,
        "getfile",
        lambda _klass: str(tmp_path / "virtual-package" / "config_reader.py"),
        raising=False,
    )
    monkeypatch.setattr(
        config_reader_module.os.path,
        "exists",
        lambda path: str(path) in {expected_windows_config, expected_windows_local, expected_home_config},
        raising=False,
    )
    monkeypatch.setattr(
        config_reader_module.AppConfigReader.klass,
        "reset_config",
        lambda self, config_files: captured.setdefault("config_files", list(config_files)),
        raising=False,
    )

    _reset_config_singleton(monkeypatch, config_reader_module)
    config_reader_module.AppConfigReader([])
    assert captured["config_files"] == [expected_windows_config, expected_windows_local, expected_home_config]
