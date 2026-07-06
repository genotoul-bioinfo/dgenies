from __future__ import annotations

from enum import Enum, StrEnum

from pydantic import BaseModel, Field

from ..lib.functions import Functions
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


class AnnotationTrackAxis(str, Enum):
    query = 'query'
    target = 'target'


class AnnotationTrackFormat(str, Enum):
    bed = 'bed'
    wig = 'wig'
    bedgraph = 'bedgraph'


class PrepareFastaEnum(str, Enum):
    done = 'Done'
    in_progress = 'In progress'


class Limits(BaseModel):
    number_of_jobs: int = Field(description="Maximum number of jobs allowed per run")
    file_size: int = Field(description="Maximum file size allowed for upload")
    uncompressed_size_self_align: int = Field(
        description="Maximum uncompressed file size (in bytes) allowed when self aligning a sequence (target)"
    )
    uncompressed_size: int = Field(description="Maximum uncompressed file size (in bytes) allowed in query vs target mode")
    walltime_prepare: str = Field(description="Walltime (in hh:mm:ss) for sequence preparation step")
    walltime_align: str = Field(description="Walltime (in hh:mm:ss) for sequence alignment step")


class InforunType(str, Enum):
    info = "info"
    warn = "warn"
    critical = "critical"
    success = "success"


class Inforun(BaseModel):
    message: str = Field(description="Banner message"),
    type: InforunType = Field(description="Message type")


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


class Config(BaseModel):
    banner: Inforun|None = Field(description="Banner message if any")
    batch_id: str = Field(description="Suggested batch id")
    email: bool = Field(Functions.is_email_mandatory(), description="if True, an email is required to submit a job")
    limits: Limits = Field(description="This instance limits")
    jobs: list[JobDescription] = Field(description="Configuration about jobs")


class ConfigResponse(BaseResponse):
    data: Config
