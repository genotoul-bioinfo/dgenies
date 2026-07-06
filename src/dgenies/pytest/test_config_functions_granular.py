import gzip
import os
from configparser import RawConfigParser
from pathlib import Path
from types import SimpleNamespace

import pytest


def _config_from_text(text):
    from dgenies.config_reader import AppConfigReader

    config = object.__new__(AppConfigReader.klass)
    config.reader = RawConfigParser()
    config.reader.read_string(text)
    return config


def test_config_reader_uses_defaults_for_missing_optional_sections(monkeypatch):
    config = _config_from_text("[global]\nupload_folder=/uploads\ndata_folder=/data\n[session]\n")
    monkeypatch.delenv("RUNNER_TYPE", raising=False)
    monkeypatch.delenv("WEB_URL", raising=False)
    monkeypatch.delenv("SEND_MAIL_URL", raising=False)
    monkeypatch.delenv("MAX_NB_LINES", raising=False)

    assert config._get_runner_type() == "local"
    assert config._get_web_url() == "http://localhost:5000"
    assert config._get_send_mail_url() == "http://localhost:5000"
    assert config._get_max_nb_lines() == 100000
    assert config._get_max_nb_jobs_in_batch_mode() == 10
    assert config._get_max_download_sessions() == 5


def test_config_reader_environment_overrides_file_values(monkeypatch):
    config = _config_from_text(
        "[global]\n"
        "runner_type=cluster\n"
        "web_url=http://file.example\n"
        "send_mail_url=http://mail-file.example\n"
        "max_upload_size=2M\n"
        "max_upload_size_ava=3M\n"
        "max_upload_file_size=4M\n"
        "max_nb_lines=12\n"
        "max_nb_jobs_in_batch_mode=2\n"
    )
    monkeypatch.setenv("RUNNER_TYPE", "local")
    monkeypatch.setenv("WEB_URL", "http://env.example")
    monkeypatch.setenv("SEND_MAIL_URL", "http://mail-env.example")
    monkeypatch.setenv("MAX_UPLOAD_SIZE", "5M")
    monkeypatch.setenv("MAX_UPLOAD_SIZE_AVA", "6M")
    monkeypatch.setenv("MAX_UPLOAD_FILE_SIZE", "7M")
    monkeypatch.setenv("MAX_NB_LINES", "42")
    monkeypatch.setenv("MAX_NB_JOBS_IN_BATCH_MODE", "9")

    assert config._get_runner_type() == "local"
    assert config._get_web_url() == "http://env.example"
    assert config._get_send_mail_url() == "http://mail-env.example"
    assert config._get_max_upload_size() == 5 * 1024 * 1024
    assert config._get_max_upload_size_ava() == 6 * 1024 * 1024
    assert config._get_max_upload_file_size() == 7 * 1024 * 1024
    assert config._get_max_nb_lines() == 42
    assert config._get_max_nb_jobs_in_batch_mode() == 9


def test_config_reader_rejects_config_variable_inside_config_dir(monkeypatch):
    config = _config_from_text("[global]\nconfig_dir=###CONFIG###/nested\n")
    monkeypatch.delenv("CONFIG_DIR", raising=False)

    with pytest.raises(Exception, match="CONFIG"):
        config._replace_vars("###CONFIG###/nested", config=True)


def test_config_reader_database_mysql_fields(monkeypatch):
    config = _config_from_text(
        "[database]\n"
        "type=mysql\n"
        "url=db.example.org\n"
        "port=3307\n"
        "db=dgenies\n"
        "user=alice\n"
        "password=secret\n"
    )
    for key in (
        "DATABASE_TYPE",
        "DATABASE_URL",
        "DATABASE_PORT",
        "DATABASE_BASE",
        "DATABASE_USER",
        "DATABASE_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)

    assert config._get_database_type() == "mysql"
    assert config._get_database_url() == "db.example.org"
    assert config._get_database_port() == 3307
    assert config._get_database_db() == "dgenies"
    assert config._get_database_user() == "alice"
    assert config._get_database_password() == "secret"


def test_config_reader_database_mysql_requires_db_and_user(monkeypatch):
    config = _config_from_text("[database]\ntype=mysql\n")
    monkeypatch.delenv("DATABASE_BASE", raising=False)
    monkeypatch.delenv("DATABASE_USER", raising=False)

    with pytest.raises(Exception, match="db name"):
        config._get_database_db()
    with pytest.raises(Exception, match="database user"):
        config._get_database_user()


def test_config_reader_cron_time_valid_invalid_and_default():
    valid = _config_from_text("[cron]\nclean_time=23h59\nclean_freq=3\n")
    invalid = _config_from_text("[cron]\nclean_time=25h00\n")
    missing = _config_from_text("[global]\nupload_folder=/uploads\ndata_folder=/data\n")

    assert valid._get_cron_clean_time() == [23, 59]
    assert valid._get_cron_clean_freq() == 3
    assert invalid._get_cron_clean_time() == [1, 0]
    assert missing._get_cron_clean_time() == [1, 0]
    assert missing._get_cron_clean_freq() == 1


def test_config_reader_mail_debug_and_analytics_booleans(monkeypatch):
    config = _config_from_text(
        "[mail]\ndisable=false\nsend_mail_status=false\n"
        "[debug]\nenable=true\n"
        "[analytics]\nenable_logging_runs=true\ndisable_anonymous_analytics=true\nanonymous_analytics=FULL_HASH\n"
    )
    monkeypatch.delenv("DISABLE_MAIL", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.setenv("ANALYTICS", "true")
    monkeypatch.delenv("DISABLE_ANONYMOUS_ANALYTICS", raising=False)
    monkeypatch.delenv("ANONYMOUS_ANALYTICS", raising=False)

    assert config._get_disable_mail() is False
    assert config._get_send_mail_status() is False
    assert config._get_debug() is True
    assert config._get_analytics_enabled() is True
    assert config._get_disable_anonymous_analytics() is False
    assert config._get_anonymous_analytics() == "full_hash"


def test_config_reader_log_dir_is_created_and_file_path_is_rejected(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    config = _config_from_text(f"[debug]\nlog_dir={log_dir}\n")
    monkeypatch.delenv("LOG_DIR", raising=False)

    assert config._get_log_dir() == str(log_dir)
    assert log_dir.is_dir()

    log_file = tmp_path / "logfile"
    log_file.write_text("not a dir")
    config = _config_from_text(f"[debug]\nlog_dir={log_file}\n")

    with pytest.raises(TypeError, match="Log dir"):
        config._get_log_dir()


def test_config_reader_drmaa_path_required_for_non_local_runner(monkeypatch):
    config = _config_from_text("[global]\nrunner_type=slurm\n")
    monkeypatch.delenv("DRMAA_LIB_PATH", raising=False)
    monkeypatch.delenv("RUNNER_TYPE", raising=False)

    with pytest.raises(Exception, match="drmaa"):
        config._get_drmaa_lib_path()


def test_allowed_extensions_join_flattens_nested_yaml_sequences():
    from dgenies.allowed_extensions import AllowedExtensions

    class Loader:
        def construct_sequence(self, node):
            return [["fa", "fasta"], ["fna"], []]

    assert AllowedExtensions.klass.join(Loader(), object()) == ["fa", "fasta", "fna"]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"all_vs_all": "{exe} {target}"}, "all_vs_all"),
        ({"max_memory": "4"}, "max_memory"),
        ({"threads": "2"}, "threads must be"),
        ({"threads_cluster": "2"}, "threads_cluster"),
        ({"parser": "missing_parser"}, "parser missing_parser"),
        ({"split_before": "yes"}, "split_before"),
        ({"options": {"group": "bad"}}, "options must"),
        ({"options": [{"group": "g", "type": "radio"}]}, "Missing key entries"),
    ],
)
def test_tool_constructor_rejects_invalid_configuration(kwargs, message):
    from dgenies.tools import Tool

    base = {
        "name": "mapper",
        "exec": "/bin/mapper",
        "command_line": "{exe} {target} {query} -o {out}",
        "all_vs_all": None,
        "max_memory": 4,
    }
    base.update(kwargs)

    with pytest.raises(ValueError, match=message):
        Tool(**base)


def test_tools_load_yaml_uses_lowest_order_as_default(tmp_path):
    from dgenies.tools import Tools

    tool_yaml = tmp_path / "tools.yaml"
    tool_yaml.write_text(
        "slow:\n"
        "  exec: /bin/slow\n"
        "  command_line: '{exe} {target} {query} -o {out}'\n"
        "  all_vs_all: null\n"
        "  max_memory: 4\n"
        "  order: 20\n"
        "fast:\n"
        "  exec: /bin/fast\n"
        "  command_line: '{exe} {target} {query} -o {out}'\n"
        "  all_vs_all: null\n"
        "  max_memory: 2\n"
        "  order: 5\n"
    )
    manager = object.__new__(Tools.klass)
    manager.tools = {}
    manager.default = None

    manager.load_yaml(trusted=True, tool_config=str(tool_yaml))

    assert sorted(manager.tools) == ["fast", "slow"]
    assert manager.get_default() == "fast"


def test_functions_hardlink_or_copy_falls_back_to_copy(tmp_path, monkeypatch):
    from dgenies.lib.functions import Functions

    src = tmp_path / "source.txt"
    dest = tmp_path / "dest.txt"
    src.write_text("content")
    monkeypatch.setattr(os, "link", lambda source, target: (_ for _ in ()).throw(OSError("cross device")))

    Functions.hardlink_or_copy(str(src), str(dest))

    assert dest.read_text() == "content"


def test_functions_get_fasta_file_prefers_sorted_dotfile_and_sorted_sibling(tmp_path):
    from dgenies.lib.functions import Functions

    original = tmp_path / "query.fa"
    sibling_sorted = tmp_path / "query.fa.sorted"
    explicit_sorted = tmp_path / "explicit.sorted"
    original.write_text(">q\nA\n")
    sibling_sorted.write_text(">q\nA\n")
    explicit_sorted.write_text(">q\nA\n")
    (tmp_path / ".query").write_text(str(original))

    assert Functions.get_fasta_file(str(tmp_path), "query", False) == str(original)
    assert Functions.get_fasta_file(str(tmp_path), "query", True) == str(sibling_sorted)

    (tmp_path / ".query.sorted").write_text(str(explicit_sorted))

    assert Functions.get_fasta_file(str(tmp_path), "query", True) == str(explicit_sorted)


def test_functions_get_fasta_file_returns_none_when_dotfile_missing(tmp_path):
    from dgenies.lib.functions import Functions

    assert Functions.get_fasta_file(str(tmp_path), "query", False) is None


def test_functions_compress_uses_collision_suffix_and_overwrite(tmp_path):
    from dgenies.lib.functions import Functions

    plain = tmp_path / "data.txt"
    plain.write_text("first")
    existing = tmp_path / "data.txt.gz"
    existing.write_bytes(b"old")

    collided = Functions.compress(str(plain), remove=False)

    assert Path(collided).name == "2_data.txt.gz"
    assert plain.exists()

    plain.write_text("second")
    overwritten = Functions.compress(str(plain), overwrite=True, remove=False)

    assert overwritten == str(existing)
    assert gzip.open(existing, "rt").read() == "second"


def test_functions_uncompress_uses_collision_suffix(tmp_path):
    from dgenies.lib.functions import Functions

    plain = tmp_path / "data.txt"
    plain.write_text("already here")
    gz = tmp_path / "data.txt.gz"
    with gzip.open(gz, "wt") as handle:
        handle.write("compressed")

    uncompressed = Functions.uncompress(str(gz))

    assert Path(uncompressed).name == "2_data.txt"
    assert Path(uncompressed).read_text() == "compressed"


def test_functions_compress_and_send_mail_updates_dotfile_and_unlocks(tmp_path, monkeypatch):
    from dgenies.lib.functions import Functions

    fasta = tmp_path / "Query.fasta"
    lock = tmp_path / ".lock"
    dotfile = tmp_path / ".query.sorted"
    fasta.write_text(">q\nACGT\n")
    lock.touch()
    sent = []
    monkeypatch.setattr(Functions, "send_fasta_ready", staticmethod(lambda *args, **kwargs: sent.append((args, kwargs))))

    Functions.compress_and_send_mail("job1", str(fasta), str(lock), object(), dot_file=str(dotfile))

    assert dotfile.read_text().endswith("Query.fasta.gz")
    assert not lock.exists()
    assert sent[0][0][1:4] == ("job1", "Query", True)


def test_functions_send_fasta_ready_renders_mail(monkeypatch):
    from dgenies.lib.functions import Functions

    class Mailer:
        def __init__(self):
            self.calls = []

        def send_mail(self, recipients, subject, message, message_html):
            self.calls.append((recipients, subject, message, message_html))

    mailer = Mailer()
    monkeypatch.setattr(Functions.config, "web_url", "http://dgenies.example")
    monkeypatch.setattr(Functions, "get_mail_for_job", staticmethod(lambda job_id: "user@example.org"))

    Functions.send_fasta_ready(mailer, "job1", "Query", compressed=True, path="fasta-query", ext="fa")

    recipients, subject, message, message_html = mailer.calls[0]
    assert recipients == ["user@example.org"]
    assert subject == "Job job1 - Download fasta"
    assert "http://dgenies.example/fasta-query/job1/Query.fasta.gz" in message
    assert "job1" in message_html


def test_functions_get_status_strips_placeholder_and_handles_missing_metrics(tmp_path):
    from dgenies.lib.functions import Functions

    job = SimpleNamespace(
        id_job="job1",
        logs=str(tmp_path / "missing.log"),
        status=lambda: {"status": "fail", "error": "#ID# failed"},
    )

    assert Functions.get_status(job) == {
        "status": "fail",
        "error": " failed",
        "has_logs": False,
        "id_job": "job1",
        "mem_peak": None,
        "time_elapsed": None,
    }


def test_validator_paf_n_max_stops_before_bad_line(tmp_path):
    from dgenies.lib import validators

    paf = tmp_path / "map.paf"
    good = "q\t10\t0\t5\t+\tt\t20\t1\t6\t5\t5\t60"
    paf.write_text(good + "\nbad\n")

    assert validators.paf(str(paf), n_max=1) is True
    assert validators.paf(str(paf)) is False


def test_validator_idx_allows_only_one_trailing_blank_region(tmp_path):
    from dgenies.lib import validators

    idx = tmp_path / "query.idx"
    idx.write_text("Query\nctg1\t10\n\n")
    assert validators.v_idx(str(idx)) is True

    idx.write_text("Query\nctg1\t10\n\nctg2\t5\n")
    assert validators.v_idx(str(idx)) is False


def test_validator_maf_accepts_two_sequence_block(tmp_path):
    from dgenies.lib import validators

    maf = tmp_path / "map.maf"
    maf.write_text("##maf version=1 scoring=none\n\na score=0\ns target 0 4 + 10 ACGT\ns query 1 4 + 20 ACCT\n")

    assert validators.maf(str(maf)) is True


def test_parser_maf_writes_forward_paf_coordinates(tmp_path):
    from dgenies.lib.parsers import maf

    source = tmp_path / "map.maf"
    out = tmp_path / "map.paf"
    source.write_text("##maf version=1 scoring=none\n\na score=0\ns target 0 4 + 10 ACGT\ns query 1 4 + 20 ACCT\n")

    assert maf(str(source), str(out)) is True
    assert out.read_text() == "query\t20\t1\t5\t+\ttarget\t10\t0\t4\t3\t4\t255\n"


def test_parser_maf_writes_reverse_paf_coordinates(tmp_path):
    from dgenies.lib.parsers import maf

    source = tmp_path / "map.maf"
    out = tmp_path / "map.paf"
    source.write_text("##maf version=1 scoring=none\n\na score=0\ns target 0 4 + 10 ACGT\ns query 1 4 - 20 ACCT\n")

    assert maf(str(source), str(out)) is True
    assert out.read_text() == "query\t20\t15\t19\t-\ttarget\t10\t0\t4\t3\t4\t255\n"
