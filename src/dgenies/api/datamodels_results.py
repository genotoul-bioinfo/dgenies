from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from .datamodels_common import (
    AnnotationTrackAxis,
    AnnotationTrackFormat,
    BaseResponse,
    ContigType,
    PrepareFastaEnum,
)
from .datamodels_jobs import JobId


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
    x_order: list[str] = Field(description="Order of contigs on target")
    name_y: str = Field(description="Name of the query")
    name_x: str = Field(description="Name of the target")
    limit_idy: list[float] = Field([0.25, 0.5, 0.75], description="limits splitting class of identities")
    sorted: bool = Field(False, description="True if the contigs are sorted")
    sampled: bool = Field(False, description="True if matches (lines) are sampled")
    max_nb_lines: int = Field(description="Number of maximum matches (lines) displayed if contigs are sampled")


class DotplotResponse(BaseResponse):
    data: Dotplot


class AnnotationTrack(BaseModel):
    id: str = Field(description="Annotation track id")
    job_id: str = Field(description="The id of the job")
    axis: AnnotationTrackAxis = Field(description="Axis the track is associated with")
    format: AnnotationTrackFormat = Field(description="Track file format")
    name: str = Field(description="Display name")
    filename: str = Field(description="Original uploaded filename")
    size: int = Field(description="Track file size in bytes")
    created_at: str = Field(description="Track upload timestamp")


class AnnotationTracksList(BaseModel):
    tracks: list[AnnotationTrack] = Field(description="Annotation tracks available for the job")


class AnnotationTrackResponse(BaseResponse):
    data: AnnotationTrack


class AnnotationTracksResponse(BaseResponse):
    data: AnnotationTracksList


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
    data: NoAssoc = Field(description="No association")


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


class ExampleFile(BaseModel):
    uri: str = Field(description="The URI of the file")


class ExampleFilesResponse(BaseResponse):
    data: list[ExampleFile] = Field(description="Exemple Files")


class PrepareFasta(BaseModel):
    status: PrepareFastaEnum = Field(description="Status of the preparation")
    gzip: Optional[bool] = Field(description="Whether the file is gzipped")
    mail: bool = Field(description="An email will be sent")


class PrepareFastaResponse(BaseResponse):
    data: PrepareFasta = Field(description="Prepared fasta data")


class PrepareFastaInput(BaseModel):
    gzip: bool = Field(description="Ask for a gzipped the file. If set to false,"
                                   "but the query file on server is already gzipped, this option will be ignored.")
