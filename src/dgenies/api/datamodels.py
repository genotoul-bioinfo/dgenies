from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field
from flask_openapi3 import FileStorage

from ..lib.functions import Functions
from ..tools import Tools

ToolName = Enum('ToolName', [(k, k) for k in Tools().tools.keys()])

class BaseResponse(BaseModel):
    code: int = Field(0, description="status code")
    message: str = Field("ok", description="exception information")


class Limits(BaseModel):
    number_of_jobs: int = Field(description="Maximum number of jobs allowed per run")
    upload_size: int = Field(description="Maximum file size allowed for upload")
    uncompressed_size_ava: int = Field(
        description="Maximum uncompressed file size (in bytes) allowed in target vs itself mode")
    uncompressed_size: int = Field(description="Maximum uncompressed file size (in bytes) allowed in query vs target mode")
    walltime_prepare: str = Field(description="Walltime (in hh:mm:ss) for sequence preparation step")
    walltime_align: str = Field(description="Walltime (in hh:mm:ss) for sequence alignment step")


class Config(BaseModel):
    id_job: str = Field(description="Suggested job id")
    email: bool = Field(True, description="if True, an email is required to submit a job")
    limits: Limits = Field(description="This instance limits")
    jobs: list[JobDescription] = Field(description="Configuration about jobs")


class ConfigResponse(BaseResponse):
    data: Config


class JobType(str, Enum):
    align = 'align'
    plot = 'plot'
    batch = 'batch'


class SubJobType(str, Enum):
    align = 'align'
    plot = 'plot'


class InputType(str, Enum):
    query = 'query'
    target = 'target'
    align = 'align'
    backup = 'backup'


class JobInput(BaseModel):
    type: InputType = Field(description="Type of input field")
    desc: str = Field(description="Description of input field")
    allowed_ext: list[str] | None = Field(description="Allowed extension type. Any if null or empty")


class OptionEntry(BaseModel):
    name: str = Field(description="name of option's entry")
    label: str = Field(description="Label of option's entry")
    desc: str = Field(description="Describes the option's entry")
    default: bool = Field(False, description="Entry is activated by default")


class ToolOption(BaseModel):
    name: str = Field(description="name of option")
    label: str = Field(description="Label of option")
    desc: str = Field(description="Describes the option")
    mutex: bool = Field(description="True if option's choices are mutually exclusives")
    entries: list[OptionEntry] = Field(min_length=1, description="Possible option values")


class ToolDescription(BaseModel):
    name: str | None  = Field(description="Name of the tool (if applicable).")
    label: str | None  = Field(description="Label of the tool. If no label given, will be hidden.")
    desc: str = Field(description="Description of input field")
    options: list[ToolOption]
    needs: list[list[InputType]] = Field(description="Combination of inputs that must be used with tool.")


class JobDescription(BaseModel):
    type: JobType = Field(description="Type of job.")
    label: str = Field(description="Label of job.")
    desc: str = Field(description="Describes the purpose of job.")
    tools: list[ToolDescription] = Field(description="Tools that can be used by job.")
    inputs: list[JobInput] = Field(description="Inputs that can be used with job")
    default: str = Field(description="Name of default tool.")


class Session(BaseModel):
    session: str = Field(description="Session id")

class SessionResponse(BaseResponse):
    data: Session


class AskUpload(BaseModel):
    allowed: bool = Field(False, description="Allowed to upload file")

class AskUploadQuery(Session):
    pass

class AskUploadResponse(BaseResponse):
    data: AskUpload


class JobMetadata(BaseModel):
    id_job: str = Field(description="Job id")
    if Functions.is_email_mandatory():
        email: str = Field(description="Email to warn you when job is finished")


class FileType(str, Enum):
    local = 'local'
    url = 'url'

class Job(JobMetadata):
    type: SubJobType = Field(SubJobType.align, description="Type of job (align, plot or batch)")

    query: str = Field(description="Query file. Can be either a filename or an url")
    query_type: FileType = Field(description="Type of query file. Either 'local' or 'url'")

    target: str = Field(description="Target file. Can be either a filename or an url")
    target_type: FileType = Field(description="Type of target file. Either 'local' or 'url'")

    align: str = Field(description="Align file. Can be either a filename or an url")
    align_type: FileType = Field(description="Type of align file. Either 'local' or 'url'")

    backup: str = Field(description="Backup file. Can be either a filename or an url")
    backup_type: FileType = Field(description="Type of backup file. Either 'local' or 'url'")

    tool: ToolName = Field(description="Tool file. Can be either 'minimap2' or 'mashmap'")
    tool_option: list[str] = Field([], description="List of options for chosen tool.")


class JobSubmissionQuery(Session, JobMetadata):
    nb_jobs: int = Field(description="Number of jobs submitted.")
    jobs: list[Job] = Field(description="List of jobs submitted")
    type: JobType = Field(JobType.align, description="Type of job (align, plot or batch)")


class JobId(BaseModel):
    jobid: str = Field(description="Job id")

class JobSubmissionResponse(BaseResponse):
    data: JobId

class UploadFileForm(BaseModel):
    s_id: str = Field(description="Session id")
    jobtype: set[JobType] = Field(description="Types of job the file is associated with", min_length=1)
    filetype: set[InputType] = Field(description="Types of file is associated with", min_length=1)
    file: FileStorage


class JobPath(BaseModel):
    jobid: str = Field(description='job id')

class Dotplot(BaseModel):
    y_len: int = Field(description="Cumulative query length (y-axis) in base-pairs")
    x_len: int = Field(description="Cumulative target length (x-axis) in base-pairs")
    min_idy: float = Field(0, description="Minimum identity/matching score")
    max_idy: float = Field(1, description="Maximum identity/matching score")
    lines: dict[int, list[tuple[int, int, int, int, float, str, str]]] = Field(
        description = """List of lines representing matches. Lines are grouped by classes such as:
        lines = { <int:class> : [(<int:x1>, <int:y1>, <int:x2>, <int:y2>, <float:0 <= identity-score <= 1>, <str:query-chr-name>, <str:target-chr-name>)]
        Where 'class' takes values in {0,1,2,3}, ('x1', 'y1') and ('x2', 'y2') are extremities of a line, 'identity-score' is the matching score \\in [0,1], 'query-chr-name' and 'target-chr-name' are respectively chromosome names on query and target.
        """
    )
    y_contigs: dict[str, int] = Field(description="Contig/chromosome size in query")
    y_order: list[str] = Field(description="Order of contigs on query (y-axis)")
    x_contigs: dict[str, int] = Field(description="Contig/chromosome size in target")
    x_order: list[str] = Field(description="Order of contigs on target (x-axis)")
    name_y: str = Field(description="Name of the query")
    name_x: str = Field(description="Name of the target")
    limit_idy: list[float] = Field([0.25, 0.5, 0.75], description="limits splitting class of identities")
    sorted: bool = Field(False, description="True if the contigs are sorted")
    sampled: bool = Field(False, description="True if matches (lines) are sampled")
    max_nb_lines: int = Field(description="Number of maximum matches (lines) displayed if contigs are sampled")


class DotplotResponse(BaseResponse):
    data: Dotplot