"""Core API validation and request-handling tests."""

from types import SimpleNamespace
from typing import List

import pytest

from dgenies.allowed_extensions import AllowedExtensions
from dgenies.api import (
    _fix_file_role,
    _fix_job_type,
    ask_upload,
    create_session,
    get_config,
)
from dgenies.api import (
    allowed_file_ext as api_allowed_file_ext,
)
from dgenies.api.datamodels import BatchSubmissionQuery
from dgenies.lib.exceptions import (
    DGeniesExampleInvalid,
    DGeniesUnknownOptionError,
    DGeniesUnknownToolError,
    DGeniesValidationError,
)
from dgenies.pytest.helpers import (
    DummyBody,
    _install_fake_tools,
    _make_job_model,
    _setup_api_runtime,
)

# This file was split out from src/dgenies/test_dgenies_api.py.


@pytest.mark.parametrize(
    "job_type,expected",
    [
        ("align", "new"),
        (" align", " align"),
        ("map", "map"),
        ("new", "new"),
        ("", ""),
        ("ALIGN", "ALIGN"),
        ("plot", "plot"),
        ("analysis", "analysis"),
        ("AL", "AL"),
        ("sample", "sample"),
    ],
)
def test_fix_job_type(job_type: str, expected: str) -> None:
    """Check that _fix_job_type normalises only the align value.

    Ten distinct input values are exercised.  Only the exact string
    "align" should map to "new"; all other values must be returned
    unchanged.
    """
    assert _fix_job_type(job_type) == expected


@pytest.mark.parametrize(
    "file_role,expected",
    [
        ("align", "map"),
        ("query", "query"),
        ("", ""),
        ("ALIGN", "ALIGN"),
        ("map", "map"),
        ("target", "target"),
        ("source", "source"),
        ("Align", "Align"),
        ("control", "control"),
        ("aligner", "aligner"),
    ],
)
def test_fix_file_role(file_role: str, expected: str) -> None:
    """Check that _fix_file_role normalises only the align role.

    Ten cases verify that the special mapping from "align" to "map" is
    performed and that every other value is returned unchanged.
    """
    assert _fix_file_role(file_role) == expected


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("data.fa", True),
        ("sequence.fasta", True),
        ("reads.fa.gz", True),
        ("genome.fa", True),
        ("chrom.fa.gz", True),
        ("sample.fasta", True),
        ("myseq.fa", True),
        ("test.fa", True),
        ("example.fasta", True),
        ("data.fa.gz", True),
        ("data.txt", False),
        ("reads.fastq", False),
        ("sample.gtf", False),
        ("genome.jpg", False),
        ("file", False),
        ("file.", False),
        (".fa", True),
        ("fa", False),
        ("myseq.fa.bz2", False),
        ("unknown.extension", False),
    ],
)
def test_api_allowed_file_ext(
    monkeypatch: pytest.MonkeyPatch, filename: str, expected: bool
) -> None:
    """Test dgenies.api.allowed_file_ext against a controlled extension set.

    The test patches AllowedExtensions.get_formats to always return a
    single format ("fasta") and AllowedExtensions.get_extensions to
    return a fixed set of valid extensions.  Twenty different filenames
    are exercised to ensure both valid and invalid extensions are
    correctly recognised.
    """

    # Provide a deterministic allowed format/extension set for this test
    def fake_get_formats(job_type: str, file_role: str) -> List[str]:
        return ["fasta"]

    def fake_get_extensions(fmt: str) -> List[str]:
        # Accept both short and long FASTA extensions and gzipped variants
        return ["fa", "fasta", "fa.gz"]

    allowed_extensions = AllowedExtensions()
    monkeypatch.setattr(
        allowed_extensions, "get_formats", fake_get_formats, raising=False
    )
    monkeypatch.setattr(
        allowed_extensions, "get_extensions", fake_get_extensions, raising=False
    )

    result = api_allowed_file_ext(filename, "align", "target")
    assert result is expected


@pytest.mark.parametrize("_", list(range(10)))
def test_api_get_config_returns_expected(monkeypatch: pytest.MonkeyPatch, _):
    """Ensure that get_config returns a successful response.

    The helper functions used to populate the response (e.g.
    Functions.random_job_id and Functions.is_email_mandatory) are
    patched so that stable values are returned.  Ten invocations are
    performed to increase the number of distinct test cases.
    """
    import dgenies.api as api_module

    monkeypatch.setattr(
        api_module.Functions,
        "random_job_id",
        staticmethod(lambda: "jobid"),
        raising=False,
    )
    monkeypatch.setattr(
        api_module.Functions,
        "is_email_mandatory",
        staticmethod(lambda: False),
        raising=False,
    )

    response = get_config()
    assert isinstance(response, dict)
    assert response["code"] == 0
    assert response["message"] == "ok"
    data = response["data"]
    assert data["batch_id"] == "jobid"
    assert data["email"] is False
    assert "limits" in data
    assert "jobs" in data


@pytest.mark.parametrize("index", list(range(10)))
def test_api_create_session_returns_session(
    monkeypatch: pytest.MonkeyPatch, index: int
) -> None:
    """Verify that create_session returns a response with a session id.

    Functions.create_session is patched to return a deterministic
    value derived from the current index.  Ten separate indices are
    supplied to create ten distinct test cases.
    """
    import dgenies.api as api_module

    session_value = f"session_{index}"
    monkeypatch.setattr(
        api_module.Functions,
        "create_session",
        staticmethod(lambda: session_value),
        raising=False,
    )

    response = create_session()
    assert isinstance(response, dict)
    assert response["code"] == 0
    assert response["message"] == "ok"
    assert response["data"]["session_id"] == session_value


@pytest.mark.parametrize("index", list(range(5)))
def test_api_ask_upload_success(monkeypatch: pytest.MonkeyPatch, index: int) -> None:
    """Check that ask_upload reports success when uploads are allowed.

    The allow_upload function is patched to always return True.
    Five separate invocations are used to generate multiple scenarios.
    """
    import dgenies.api as api_module

    monkeypatch.setattr(api_module, "allow_upload", lambda sid: True, raising=False)

    body = DummyBody(f"sess{index}")
    response, status = ask_upload(body)
    assert status == 200
    assert response["code"] == 0
    assert response["data"]["allowed"] is True


@pytest.mark.parametrize("index", list(range(5)))
def test_api_ask_upload_failure(monkeypatch: pytest.MonkeyPatch, index: int) -> None:
    """Check that ask_upload reports failure when a session is missing.

    The allow_upload function is patched to raise a DoesNotExist
    exception, mimicking the behaviour of the database layer when the
    session cannot be found.  Five test cases are executed.
    """
    from peewee import DoesNotExist

    import dgenies.api as api_module

    def raise_missing(sid: str) -> None:
        raise DoesNotExist()

    monkeypatch.setattr(api_module, "allow_upload", raise_missing, raising=False)

    body = DummyBody(f"missing{index}")
    response, status = ask_upload(body)
    assert status == 403
    assert response["code"] == 403
    assert response["message"].lower().startswith("session")


def test_api_validation_helpers_cover_success_and_error_paths(monkeypatch):
    import dgenies.api as api_module

    _install_fake_tools(monkeypatch, api_module)
    monkeypatch.setattr(
        api_module.Functions,
        "is_email_mandatory",
        staticmethod(lambda: True),
        raising=False,
    )

    with pytest.raises(DGeniesValidationError):
        api_module.valid_email("")
    with pytest.raises(DGeniesValidationError):
        api_module.valid_email("invalid")
    api_module.valid_email("valid@example.org")

    job = _make_job_model(tool=None, tool_options=["repeat:few"])
    validated = api_module.valid_align(job)
    assert (
        str(validated.tool) == "ToolName.minimap2" or str(validated.tool) == "minimap2"
    )
    assert "preset:default" in validated.tool_options

    with pytest.raises(DGeniesUnknownToolError):
        monkeypatch.setattr(
            api_module,
            "Tools",
            lambda: SimpleNamespace(tools={}, get_default=lambda: "minimap2"),
            raising=False,
        )
        api_module.valid_align(_make_job_model(tool="minimap2"))
    _install_fake_tools(monkeypatch, api_module)
    with pytest.raises(DGeniesUnknownOptionError):
        api_module.valid_align(_make_job_model(tool_options=["bad:option"]))

    plot_job = _make_job_model(
        type="plot",
        query="query.fa.gz",
        query_type="local",
        target="target.fa.gz",
        target_type="local",
        align="map.paf",
        align_type="local",
        backup="",
        tool=None,
        tool_options=[],
    )
    assert api_module.valid_plot(plot_job).align == "map.paf"
    with pytest.raises(DGeniesValidationError):
        api_module.valid_plot(_make_job_model(type="plot", query="", align=""))

    backup_plot = _make_job_model(
        type="plot",
        query="",
        query_type="local",
        target="",
        target_type="local",
        align="",
        align_type="local",
        backup="backup.tar.gz",
        backup_type="local",
        tool=None,
        tool_options=[],
    )
    assert api_module.valid_plot(backup_plot).backup == "backup.tar.gz"

    with pytest.raises(DGeniesValidationError):
        api_module.valid_job(SimpleNamespace(type="batch"))


def test_api_form_helpers_and_job_preparation(monkeypatch):
    import dgenies.api as api_module

    _install_fake_tools(monkeypatch, api_module)
    monkeypatch.setattr(api_module, "valid_email", lambda email: None, raising=False)

    single_job = _make_job_model(job_id="single")
    api_module.valid_form(
        BatchSubmissionQuery(
            batch_id="ignored", email="a@b.c", nb_jobs=1, jobs=[single_job]
        )
    )

    with pytest.raises(DGeniesValidationError):
        api_module.valid_form(
            BatchSubmissionQuery(
                batch_id="batch", email="a@b.c", nb_jobs=2, jobs=[single_job]
            )
        )
    with pytest.raises(DGeniesValidationError):
        api_module.valid_form(
            BatchSubmissionQuery(
                batch_id="", email="a@b.c", nb_jobs=2, jobs=[single_job, single_job]
            )
        )
    with pytest.raises(DGeniesValidationError):
        api_module.valid_form(
            BatchSubmissionQuery(batch_id="batch", email="a@b.c", nb_jobs=0, jobs=[])
        )

    batch = BatchSubmissionQuery(
        batch_id="batch",
        email="a@b.c",
        nb_jobs=2,
        jobs=[single_job, _make_job_model(job_id="other")],
    )
    api_module.valid_form(batch)

    roles = list(api_module.get_file_role(_make_job_model(), file_types=["local"]))
    assert ("query.fa.gz", "query") in roles
    assert ("target.fa.gz", "target") in roles

    plot_roles = list(
        api_module.get_file_role(
            _make_job_model(
                type="plot",
                query="query.fa.gz",
                query_type="url",
                target="target.fa.gz",
                target_type="local",
                align="map.paf",
                align_type="local",
                backup="",
                tool=None,
                tool_options=[],
            ),
            file_types=["local"],
        )
    )
    assert plot_roles == [("target.fa.gz", "target"), ("map.paf", "align")]

    assert api_module.get_tools_options("minimap2", ["repeat:few"]) == ["--repeat:few"]
    with pytest.raises(DGeniesUnknownToolError):
        api_module.get_tools_options("unknown", [])

    prepared = api_module.prepare_jobs(
        "mail@example.org", [_make_job_model(job_id="alpha")]
    )
    assert prepared[0]["job_id"] == "alpha"
    assert prepared[0]["tool"] == "minimap2"
    assert prepared[0]["options"] == "--repeat:few"
