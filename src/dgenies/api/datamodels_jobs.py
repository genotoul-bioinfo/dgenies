from __future__ import annotations

from enum import Enum
from typing import Optional

from flask_openapi3 import FileStorage
from pydantic import BaseModel, Field

from ..lib.functions import Functions
from .datamodels_common import (
    AnnotationTrackAxis,
    BaseResponse,
    JobType,
    ToolName,
)


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

    query: Optional[str] = Field(None, description="Query file. Can be either a filename or an url")
    query_type: Optional[FileType] = Field(None, description="Type of query file. Either 'local' or 'url'")

    target: Optional[str] = Field(None, description="Target file. Can be either a filename or an url")
    target_type: Optional[FileType] = Field(None, description="Type of target file. Either 'local' or 'url'")

    align: Optional[str] = Field(None, description="Align file. Can be either a filename or an url")
    align_type: Optional[FileType] = Field(None, description="Type of align file. Either 'local' or 'url'")

    backup: Optional[str] = Field(None, description="Backup file. Can be either a filename or an url")
    backup_type: Optional[FileType] = Field(None, description="Type of backup file. Either 'local' or 'url'")

    tool: ToolName | None = Field(None, description="Tool file. Can be either 'minimap2' or 'mashmap'")
    tool_options: list[str] = Field(default_factory=list, description="List of options for chosen tool.")


class JobsSubmissionQuery(Session, Job):
    if Functions.is_email_mandatory():
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


class AnnotationTrackUploadForm(BaseModel):
    axis: AnnotationTrackAxis = Field(description="Axis the track is associated with")
    name: Optional[str] = Field(None, description="Display name for the track")
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


class AnnotationTrackPath(JobPath):
    track_id: str = Field(description="Annotation track id")
