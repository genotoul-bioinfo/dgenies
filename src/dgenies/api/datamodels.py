from __future__ import annotations

from enum import Enum, StrEnum
from typing import Annotated, Optional, Literal
from pydantic import BaseModel, Field
from flask_openapi3 import FileStorage

import dgenies
from ..tools import Tools

ToolName = StrEnum('ToolName', [(k, k) for k in Tools().tools.keys()])

class BaseResponse(BaseModel):
    code: int = Field(0, description="status code")
    message: str = Field("ok", description="exception information")

class NotFoundResponse(BaseModel):
    code: int = Field(-1, description="Status Code")
    message: str = Field("Resource not found!", description="Exception Information")

class NotImplementedResponse(BaseResponse):
    code: int = Field(501, description="Status Code")
    message: str = Field("Not Implemented", description="Exception Information")

class Limits(BaseModel):
    number_of_jobs: int = Field(description="Maximum number of jobs allowed per run")
    file_size: int = Field(description="Maximum file size allowed for upload")
    uncompressed_size_self_align: int = Field(
        description="Maximum uncompressed file size (in bytes) allowed when self aligning a sequence (target)"
    )
    uncompressed_size: int = Field(description="Maximum uncompressed file size (in bytes) allowed in query vs target mode")
    walltime_prepare: str = Field(description="Walltime (in hh:mm:ss) for sequence preparation step")
    walltime_align: str = Field(description="Walltime (in hh:mm:ss) for sequence alignment step")


class Config(BaseModel):
    batch_id: str = Field(description="Suggested batch id")
    email: bool = Field(True, description="if True, an email is required to submit a job")
    limits: Limits = Field(description="This instance limits")
    jobs: list[JobDescription] = Field(description="Configuration about jobs")


class ConfigResponse(BaseResponse):
    data: Config


class JobType(str, Enum):
    align = 'align'
    plot = 'plot'


class InputType(str, Enum):
    query = 'query'
    target = 'target'
    align = 'align'
    backup = 'backup'


class ContigType(str, Enum):
    query = 'query'
    target = 'target'


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
    name: str = Field(description="Name of option")
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
    default: str|None = Field(description="Name of default tool.")


class Session(BaseModel):
    session_id: str = Field(description="Session id")


class SessionResponse(BaseResponse):
    data: Session


class AskUpload(BaseModel):
    allowed: bool = Field(False, description="Allowed to upload file")


class AskUploadQuery(Session):
    pass

class AskUploadResponse(BaseResponse):
    data: AskUpload


class FileType(str, Enum):
    local = 'local'
    url = 'url'


class JobId(BaseModel):
    job_id: str = Field(description="Job id")


class Job(JobId):
    type: JobType = Field(JobType.align, description="Type of job (align, plot or batch)")

    query: str = Field(description="Query file. Can be either a filename or an url")
    query_type: FileType = Field(description="Type of query file. Either 'local' or 'url'")

    target: str = Field(description="Target file. Can be either a filename or an url")
    target_type: FileType = Field(description="Type of target file. Either 'local' or 'url'")

    align: str = Field(description="Align file. Can be either a filename or an url")
    align_type: FileType = Field(description="Type of align file. Either 'local' or 'url'")

    backup: str = Field(description="Backup file. Can be either a filename or an url")
    backup_type: FileType = Field(description="Type of backup file. Either 'local' or 'url'")

    tool: ToolName | None = Field(description="Tool file. Can be either 'minimap2' or 'mashmap'")
    tool_options: Optional[list[str]] = Field([], description="List of options for chosen tool.")

class JobsSubmissionQuery(Session, Job):

    if dgenies.MODE == "webserver":
        email: str = Field(description="Email to warn you when job is finished")
    else:
        email: Optional[str] = Field(None, description="Email to warn you when job is finished")


class NeededFiles(BaseModel):
    needed_files: list[str]|None = Field(description="files needed to be uploaded")


class JobSubmissionResponseData(NeededFiles):
    job_id: str|None = Field(description="Job id, null if file upload is needed")
    session_id: str|None = Field(description="Session id, null if no file upload is needed")
    allowed_upload: bool = Field(False, description="Allowed to upload files, if false, use /ask-upload within 50s to ask again")


class JobSubmissionResponseDataAlt(NeededFiles, JobId, Session, AskUpload):
    pass


class JobSubmissionResponse(BaseResponse):
    data: JobSubmissionResponseData


class BatchId(BaseModel):
    batch_id: str = Field(description="Batch id")


class BatchSubmissionQuery(BatchId):
    email: str = Field(description="Email to warn you when job is finished")
    nb_jobs: int = Field(description="Number of jobs submitted.")
    jobs: list[Job] = Field(description="List of jobs submitted")


class BatchSubmissionResponseData(NeededFiles):
    batch_id: str|None = Field(description="Batch id, null if file upload is needed")
    job_ids: list[JobId]|None = Field(description="List of jobs ids, null if file upload is needed")
    session_id: str|None = Field(description="Session id, null if no file upload is needed")
    allowed_upload: bool = Field(False, description="Allowed to upload files, if false and files need to be uploaded, use /ask-upload within 50s to ask again")

class BatchSubmissionResponse(BaseResponse):
    data: BatchSubmissionResponseData

class UploadFileForm(Session):
#    job_types: set[JobType] = Field(description="Types of job the file is associated with", min_length=1)
#    file_roles: set[InputType] = Field(description="Roles of file is associated with", min_length=1)
    file: FileStorage


class UploadResponseData(NeededFiles):
    batch_id: str|None = Field(description="Job id, null until last upload is completed")
    job_ids: list[JobId]|None = Field(description="List of jobs ids, null if file upload is needed")
    file: str = Field(description="File name")


class UploadResponse(BaseResponse):
    data:UploadResponseData


class JobPath(JobId):
    pass

class JobFilePath(JobId):
    filename: str = Field(description="File name")

class JobStatus(JobId):
    percent: float = Field(description="Progression of job. Takes value between 0 and 100. When the value reaches 100, the job is complete regardless of its status (success or error).")
    status: str = Field(description="Status of job")
    error: str|None = Field(description="Error message")
    has_logs: bool = Field(description="True if a log file is available")
    mem_peak: str|None = Field(None, description="Consumed peak memory if available")
    time_elapsed: str|None = Field(None, description="Time elapsed if available")


class JobStatusResponse(BaseResponse):
    data: JobStatus|None = Field(description="The job status")

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


class SummaryResponse(BaseResponse):
    data: Optional[dict[
        Annotated[int, Field(ge=-1, description="Category")],
        Annotated[float, Field(ge=0, le=100, description="Percentage value for category")]
    ]]


class QTAssocRecord(BaseModel):
    query: str
    target: Optional[str]
    strand: str
    q_len: int
    q_start: Optional[int]
    q_stop: Optional[int]
    t_len: Optional[int]
    t_start: Optional[int]
    t_stop: Optional[int]

class QTAssoc(BaseModel):
    records: list[QTAssocRecord] = Field(description="Associations between query and target")
    count: int = Field(description="Number of records", ge=0)

class QTAssocResponse(BaseResponse):
    data: list[QTAssoc]


class NoAssocInput(BaseModel):
    which: Optional[ContigType] = Field(description="Which contigs type, ('query' if not set)")

class NoAssoc(BaseModel):
    which: ContigType = Field(description="Which contigs type")
    count: int = Field(description="Number of no matches", ge=0)
    contigs: list[str] = Field(description="List of contigs")

class NoAssocResponse(BaseResponse):
    data: NoAssoc

class GalleryData(BaseModel):
    name: str = Field(description="The name of the job")
    job_id: str = Field(description="The id of the job")
    picture: str = Field(description="The filename of the picture illustrating the job in gallery")
    query: str = Field(description="The query name")
    target: str = Field(description="The target name")
    mem_peak: str = Field(description="The max memory used for the run (human readable)")
    time_elapsed: str = Field(description="The time elapsed for the run (human readable)")

class GalleryResponse(BaseResponse):
    data: list[GalleryData]|None = Field(description="The list of entries in gallery")
