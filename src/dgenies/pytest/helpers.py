"""Shared helpers for the split D-Genies API test suite."""

import shlex
import shutil
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from werkzeug.datastructures import FileStorage

from dgenies.api.datamodels import BatchSubmissionQuery, Job

REPO_ROOT = Path(__file__).resolve().parents[3]
TESTS_DIR = REPO_ROOT / "tests"
TESTS_DATA_DIR = TESTS_DIR / "data"
TESTS_ENSEMBL_DIR = TESTS_DATA_DIR / "ensembl_104"

__all__ = [
    'DummyBody',
    'DummyJobManager',
    'REPO_ROOT',
    'TESTS_DIR',
    'TESTS_DATA_DIR',
    'TESTS_ENSEMBL_DIR',
    '_build_align_job_from_script',
    '_build_job_from_test_api_script',
    '_build_plot_backup_job_from_script',
    '_create_query_job_dir',
    '_install_fake_launch',
    '_install_fake_tools',
    '_make_job_model',
    '_make_upload_form',
    '_read_cli_script',
    '_read_shell_assignments',
    '_resolve_test_path',
    '_setup_api_runtime',
]

class DummyBody:
    """Simple container used to simulate request bodies for API tests."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

class DummyJobManager:
    """Minimal job manager used to short-circuit job launches in API tests."""

    def __init__(self, id_job: str, subjob_ids: list[str] | None = None) -> None:
        self.id_job = id_job
        self._subjob_ids = subjob_ids or []

    def get_subjob_ids(self) -> list[str]:
        return self._subjob_ids


def _read_shell_assignments(script_path: Path) -> dict[str, str]:
    """Read simple KEY=value assignments from a shell script."""
    assignments = {}
    for raw_line in script_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if not key.isupper():
            continue
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        assignments[key] = value
    return assignments


def _read_cli_script(script_path: Path) -> tuple[str, list[str], dict[str, str]]:
    """Parse a small dgenies-api shell script into command, positionals and options."""
    content = script_path.read_text().replace("\\\n", " ")
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
    tokens = shlex.split(" ".join(lines))
    command = tokens[1]
    positionals = []
    options = {}
    idx = 2
    while idx < len(tokens):
        token = tokens[idx]
        if token.startswith("--"):
            key = token[2:].replace("-", "_")
            idx += 1
            options[key] = tokens[idx]
        else:
            positionals.append(token)
        idx += 1
    return command, positionals, options


def _resolve_test_path(script_path: Path, value: str) -> Path:
    """Resolve a test fixture path from a shell script."""
    return (script_path.parent / value).resolve()


def _build_align_job_from_script(script_name: str, job_id: str) -> tuple[Job, dict[str, Path]]:
    """Translate a local `dgenies-api align` shell script into a job payload."""
    script_path = TESTS_DIR / script_name
    command, _, options = _read_cli_script(script_path)
    assert command == "align"

    uploads = {}
    target_value = options["target"]
    query_value = options.get("query")
    target_path = _resolve_test_path(script_path, target_value)
    uploads["target"] = target_path
    if query_value is not None:
        query_path = _resolve_test_path(script_path, query_value)
        uploads["query"] = query_path
        query = query_path.name
    else:
        query = ""

    job = Job(
        job_id=job_id,
        type="align",
        query=query,
        query_type="local",
        target=target_path.name,
        target_type="local",
        align="",
        align_type="local",
        backup="",
        backup_type="local",
        tool=options.get("tool"),
        tool_options=options.get("options", "").split(",") if options.get("options") else [],
    )
    return job, uploads


def _build_plot_backup_job_from_script(script_name: str, job_id: str) -> tuple[Job, Path]:
    """Translate `dgenies-api plot backup` into a job payload."""
    script_path = TESTS_DIR / script_name
    command, positionals, _ = _read_cli_script(script_path)
    assert command == "plot"
    assert positionals[0] == "backup"
    backup_path = _resolve_test_path(script_path, positionals[1])
    job = Job(
        job_id=job_id,
        type="plot",
        query="",
        query_type="local",
        target="",
        target_type="local",
        align="",
        align_type="local",
        backup=backup_path.name,
        backup_type="local",
        tool=None,
        tool_options=[],
    )
    return job, backup_path


def _build_job_from_test_api_script() -> tuple[BatchSubmissionQuery, dict[str, Path]]:
    """Translate the curl-based `tests/test_api.sh` scenario into Python objects."""
    variables = _read_shell_assignments(TESTS_DIR / "test_api.sh")
    query_path = _resolve_test_path(TESTS_DIR / "test_api.sh", variables["QUERY"])
    target_path = _resolve_test_path(TESTS_DIR / "test_api.sh", variables["TARGET"])
    job = Job(
        job_id=variables["JOB_NAME"],
        type="align",
        query=query_path.name,
        query_type="local",
        target=target_path.name,
        target_type="local",
        align="",
        align_type="local",
        backup="",
        backup_type="local",
        tool="minimap2",
        tool_options=["repeat:few"],
    )
    batch = BatchSubmissionQuery(
        batch_id=variables["JOB_NAME"],
        email=variables["EMAIL"],
        nb_jobs=1,
        jobs=[job],
    )
    return batch, {"query": query_path, "target": target_path}


def _setup_api_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    """Create an isolated app/data environment for direct API function tests."""
    import dgenies
    import dgenies.api as api_module

    app = Flask(__name__)
    upload_root = tmp_path / "uploads"
    data_root = tmp_path / "jobs"
    upload_root.mkdir()
    data_root.mkdir()
    app.config["UPLOAD_FOLDER"] = str(upload_root)

    monkeypatch.setattr(dgenies, "MODE", "standalone", raising=False)
    monkeypatch.setattr(api_module, "MODE", "standalone", raising=False)
    monkeypatch.setattr(dgenies, "APP_DATA", str(data_root), raising=False)
    monkeypatch.setattr(api_module, "APP_DATA", str(data_root), raising=False)
    monkeypatch.setattr(dgenies, "app", app, raising=False)

    return SimpleNamespace(app=app, upload_root=upload_root, data_root=data_root, api=api_module)


def _make_upload_form(session_id: str, file_path: Path, content_type: str = "application/gzip") -> SimpleNamespace:
    """Create the minimal upload form object expected by `upload_file`."""
    return SimpleNamespace(
        session_id=session_id,
        file=FileStorage(
            stream=BytesIO(file_path.read_bytes()),
            filename=file_path.name,
            content_type=content_type,
        ),
    )


def _install_fake_launch(monkeypatch: pytest.MonkeyPatch, api_module) -> dict:
    """Patch the final job launch step to keep tests fast and inspect inputs."""
    launched = {}

    def fake_launch_batch(session_id, batch_id, email, nb_jobs, jobs):
        launched["session_id"] = session_id
        launched["batch_id"] = batch_id
        launched["email"] = email
        launched["nb_jobs"] = nb_jobs
        launched["jobs"] = jobs
        final_id = batch_id if nb_jobs > 1 else jobs[0].job_id
        return DummyJobManager(final_id, [final_id])

    monkeypatch.setattr(api_module, "launch_batch", fake_launch_batch, raising=False)
    return launched


def _create_query_job_dir(job_dir: Path, source_query: Path) -> Path:
    """Copy a real query file into a job directory and create its pointer file."""
    copied_query = job_dir / source_query.name
    shutil.copy(source_query, copied_query)
    (job_dir / ".query").write_text(source_query.name)
    return copied_query


def _make_job_model(**overrides) -> Job:
    """Create a default job payload and override selected fields."""
    payload = {
        "job_id": "job",
        "type": "align",
        "query": "query.fa.gz",
        "query_type": "local",
        "target": "target.fa.gz",
        "target_type": "local",
        "align": "",
        "align_type": "local",
        "backup": "",
        "backup_type": "local",
        "tool": "minimap2",
        "tool_options": ["repeat:few"],
    }
    payload.update(overrides)
    return Job(**payload)


def _install_fake_tools(monkeypatch: pytest.MonkeyPatch, api_module) -> None:
    """Replace tool loading with a deterministic in-memory tool set."""

    class DummyToolDefinition:
        def get_options_keys(self):
            return ["repeat:few", "preset:default", "annot:cigar"]

        def get_default_options(self, chosen):
            return [] if "preset:default" in chosen else ["preset:default"]

        def resolve_option_keys(self, chosen):
            return [f"--{option}" for option in chosen]

    class DummyTools:
        def __init__(self, *_args, **_kwargs):
            self.tools = {
                "minimap2": DummyToolDefinition(),
                "mashmap": DummyToolDefinition(),
            }

        def get_default(self):
            return "minimap2"

    monkeypatch.setattr(api_module, "Tools", DummyTools, raising=False)
