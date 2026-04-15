"""Model, configuration, and exception coverage tests."""

import importlib
import os
from types import SimpleNamespace

import pytest

from dgenies.lib.datafile import DataFile

# This file was split out from src/dgenies/test_dgenies_api.py.
"""
Tests the DataFile model, covering attribute manipulation, cloning, and factory-based instantiation.

Ensure that:
1. Getter and setter methods correctly manage file metadata such as name, path, type, and size.
2. The clone() method creates an independent duplicate of the object with identical attributes.
3. The string representation accurately reflects the object's state.
4. Factory methods (create) properly initialize DataFile instances for "local", "remote" (URL), and "example" types.
"""
def test_datafile_model_and_factory_helpers():
    datafile = DataFile(name="sample", path="/tmp/query.fa", type_f="local", example=False)
    assert datafile.get_name() == "sample"
    assert datafile.get_path() == "/tmp/query.fa"
    assert datafile.get_type() == "local"
    assert datafile.is_example() is False
    assert datafile.get_file_size() == -1

    datafile.set_name("renamed")
    datafile.set_path("/tmp/query.sorted.fa")
    datafile.set_type("URL")
    datafile.set_file_size(42)
    cloned = datafile.clone()

    assert cloned.get_name() == "renamed"
    assert cloned.get_path() == "/tmp/query.sorted.fa"
    assert cloned.get_type() == "URL"
    assert cloned.get_file_size() == 42
    assert "DataFile(name=renamed" in str(cloned)

    created_local = DataFile.create("local", "/tmp/input.fa")
    created_url = DataFile.create("remote", "https://example.org/input.fa.gz")
    created_example = DataFile.create("example", "example://input.fa.gz")

    assert created_local.get_type() == "local"
    assert created_url.get_type() == "URL"
    assert created_example.is_example() is True

"""
Tests the loading, parsing, and retrieval logic for the AllowedExtensions module using a simulated YAML configuration.

Ensure that:
1. File extensions, descriptions, and job roles (query/target) are correctly extracted from the parsed configuration.
2. The join method accurately processes node-based structures to identify required formats.
3. A descriptive exception is raised when the expected configuration file cannot be found on the filesystem.
"""
def test_allowed_extensions_loading_helpers_and_missing_config(monkeypatch, tmp_path):
    import dgenies.allowed_extensions as allowed_extensions_module

    home_dir = tmp_path / "home"
    config_dir = home_dir / ".dgenies"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "allowed_extensions.yaml"
    config_file.write_text(
        "formats:\n"
        "  fasta:\n"
        "    extensions: [fa, fasta, fa.gz]\n"
        "    description: FASTA data\n"
        "  backup:\n"
        "    extensions: [tar.gz]\n"
        "job:\n"
        "  align:\n"
        "    query: [fasta, backup]\n"
        "    target: [fasta]\n"
    )

    real_exists = os.path.exists
    real_isfile = os.path.isfile
    monkeypatch.setattr(allowed_extensions_module.Path, "home", classmethod(lambda cls: home_dir), raising=False)
    monkeypatch.setattr(
        allowed_extensions_module.os.path,
        "exists",
        lambda path: real_exists(path) if str(path) == str(config_file) else False,
        raising=False,
    )
    monkeypatch.setattr(
        allowed_extensions_module.os.path,
        "isfile",
        lambda path: real_isfile(path) if str(path) == str(config_file) else False,
        raising=False,
    )
    monkeypatch.setattr(allowed_extensions_module.AllowedExtensions, "instance", None, raising=False)
    allowed = allowed_extensions_module.AllowedExtensions()

    assert allowed.allowed_extensions_per_format["fasta"] == ["fa", "fasta", "fa.gz"]
    assert allowed.get_extensions("backup") == ["tar.gz"]
    assert allowed.get_description("fasta") == "FASTA data"
    assert allowed.get_description("backup") == "a valid file"
    assert allowed.get_formats("align", "query") == ["fasta", "backup"]
    assert list(allowed.get_roles("align")) == ["query", "target"]
    assert allowed.join(SimpleNamespace(construct_sequence=lambda _node: [["fasta"], ["backup"]]), object()) == ["fasta", "backup"]

    monkeypatch.setattr(allowed_extensions_module.AllowedExtensions, "instance", None, raising=False)
    monkeypatch.setattr(allowed_extensions_module.os.path, "exists", lambda _path: False, raising=False)
    monkeypatch.setattr(allowed_extensions_module.os.path, "isfile", lambda _path: False, raising=False)
    with pytest.raises(Exception, match="Configuration file allowed_extensions.yaml not found"):
        allowed_extensions_module.AllowedExtensions()

"""
Verifies the integrity of custom exception messages and internal attributes within the dgenies.lib.exceptions module.

Ensure that:
1. String representations (__str__) for all custom exceptions provide clear, accurate, and user-friendly error messages.
2. The clear_job flag is correctly assigned to specific exception types that require job cleanup (e.g., file check or URL errors).
3. Error messages containing dynamic data—such as file sizes, lists of batch errors, or HTML formatting—are formatted exactly as expected.
4. Domain-specific error logic (e.g., unsupported file types, invalid URLs, or missing parsers) triggers the correct descriptive text and metadata.
"""
def test_exceptions_messages_and_flags_cover_remaining_branches():
    import dgenies.lib.exceptions as exc

    base = exc.DGeniesMessageException()
    assert base.message == ""
    assert base.clear_job is False

    file_check = exc.DGeniesFileCheckError(clear_job=True)
    assert file_check.clear_job is True
    assert str(exc.DGeniesUnknownOptionError("preset:bad")) == "Option unavailable: preset:bad"
    assert str(exc.DGeniesUnknownToolError("tool-x")) == "Tool unavailable: tool-x"

    not_gz = exc.DGeniesNotGzipFileError("query.fa.gz")
    assert not_gz.clear_job is True
    assert str(not_gz) == "query.fa.gz file is not a correct gzip file"

    size_uncompressed = exc.DGeniesUploadedFileSizeLimitError("query.fa", 10, unit="Mb", compressed=False)
    size_compressed = exc.DGeniesUploadedFileSizeLimitError("query.fa.gz", 12, unit="Gb", compressed=True)
    assert str(size_uncompressed) == "query.fa file exceed size limit of 10 Mb (uncompressed)"
    assert str(size_compressed) == "query.fa.gz file exceed size limit of 12 Gb (compressed)"

    assert str(exc.DGeniesAlignmentFileUnsupported()) == "Alignment file format not supported"
    alignment_invalid = exc.DGeniesAlignmentFileInvalid()
    assert alignment_invalid.message == "Alignment file is invalid. Please check your file."

    idx_invalid = exc.DGeniesIndexFileInvalid("query")
    assert idx_invalid.message == "query index file is invalid. Please check your file."

    fasta_invalid = exc.DGeniesFastaFileInvalid("query", "bad sequence")
    assert fasta_invalid.message == "query fasta file is invalid:<br/>bad sequence<br/>Please check your input file and try again."

    url_error = exc.DGeniesURLError(clear_job=True)
    assert url_error.clear_job is True
    url_invalid = exc.DGeniesURLInvalid("https://bad.example")
    assert "Url https://bad.example is not valid" == str(url_invalid)
    assert "<b>https://bad.example</b>" in url_invalid.message

    distant = exc.DGeniesDistantFileTypeUnsupported("remote.dat", "https://example.org/remote.dat", ["fasta", "maf"])
    assert str(distant) == "File remote.dat downloaded from https://example.org/remote.dat is not fasta nor maf!"
    assert "fasta nor maf" in distant.message

    assert exc.DGeniesDownloadError().message == "Error while downloading input files. Please contact the support to report the bug."
    assert exc.DGeniesBackupUnpackError().message == "Backup file is not valid. If it is unattended, please contact the support."
    assert str(exc.DGeniesBatchFileError(["line 2", "missing target"])) == "You provided a malformed batch file; line 2; missing target"

    job_check = exc.DGeniesJobCheckError(["error 1", "error 2"])
    assert str(job_check) == "error 1; error 2"
    assert job_check.message == "Server error: error 1; error 2. Please contact the support."

    run_error = exc.DGeniesRunError("runner failed")
    assert str(run_error) == "runner failed"
    assert str(exc.DGeniesClusterRunError("cluster failed")) == "cluster failed"
    assert str(exc.DGeniesLocalRunError("local failed")) == "local failed"

    missing_parser = exc.DGeniesMissingParserError("maf")
    assert missing_parser.message == "No parser found for format maf. Please contact the support."
    assert str(exc.DGeniesMissingJobError()) == "Job does not exists"
    assert str(exc.DgeniesMissingSubjobsError()) == "Batch mode: no subjob found"
    assert str(exc.DGeniesExampleNotAvailable()) == ""
    assert str(exc.DGeniesExampleInvalid("sample.fa.gz")) == "Invalid example: example://sample.fa.gz"
    assert str(exc.DGeniesDeleteGalleryJobForbidden()) == "Deleting a job that is in gallery is forbidden"
    assert exc.DGeniesValidationError("bad input").message == "bad input"

"""
Tests the JobsSubmissionQuery data model's behavior when email input is optional.

Ensure that:
1. The model can be successfully instantiated with a None value for the email field when the mandatory email requirement is disabled.
2. The attribute correctly retains its null state without triggering validation errors under this specific configuration branch.
"""
def test_datamodels_jobs_submission_optional_email_branch(monkeypatch):
    import dgenies.api.datamodels as datamodels_module

    original_is_email_mandatory = datamodels_module.Functions.is_email_mandatory
    monkeypatch.setattr(datamodels_module.Functions, "is_email_mandatory", staticmethod(lambda: False), raising=False)
    reloaded = importlib.reload(datamodels_module)
    model = reloaded.JobsSubmissionQuery(
        session_id="session",
        job_id="job",
        type="align",
        query="query.fa.gz",
        query_type="local",
        target="target.fa.gz",
        target_type="local",
        align="",
        align_type="local",
        backup="",
        backup_type="local",
        tool="minimap2",
        tool_options=[],
        email=None,
    )
    assert model.email is None
    reloaded.Functions.is_email_mandatory = original_is_email_mandatory
    importlib.reload(reloaded)
