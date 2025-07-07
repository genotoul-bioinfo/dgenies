import os
from pathlib import Path
from flask_openapi3 import APIBlueprint
from peewee import DoesNotExist

from dgenies import config_reader, APP_DATA, MODE
from ..lib.functions import Functions
from ..lib.paf import Paf

from .datamodels import (
    AskUploadQuery,
    AskUploadResponse,
    BaseResponse,
    Config,
    ConfigResponse,
    DotplotResponse,
    JobPath,
    JobSubmissionResponse,
    JobSubmissionQuery,
    Limits,
    Session,
    SessionResponse,
    UploadFileForm
)
from .job_descriptions import job_descriptions


api = APIBlueprint('dgenies', __name__, url_prefix=f"{os.environ.get('URL_PREFIX', '')}/api/v1")

limits = Limits(
    number_of_jobs=config_reader.max_nb_jobs_in_batch_mode,
    upload_size=config_reader.max_upload_size,
    uncompressed_size_ava=config_reader.max_upload_size_ava,
    uncompressed_size=config_reader.max_upload_file_size,
    walltime_prepare=config_reader.cluster_walltime_prepare,
    walltime_align=config_reader.cluster_walltime_align
)

@api.get('/config', responses={200: ConfigResponse})
def get_config():
    """
    Get this D-Genies instance configuration and limits
    """
    res = Config(
        id_job=Functions.random_job_id(),
        email=Functions.is_email_mandatory(),
        limits=limits,
        #allowed_extensions=allowed_extensions,
        jobs=job_descriptions
    )
    return {"code": 0, "message": "ok", "data": res.model_dump()}

@api.get('/session', responses={200: SessionResponse})
def get_session():
    """
    Ask for a session to upload files and submit a job
    """
    res = Session(session = Functions.get_session())
    return {"code": 0, "message": "ok", "data": res.model_dump()}

@api.post('/ask-upload', responses={200: AskUploadResponse})
def ask_upload(form: AskUploadQuery):
    """
    Ask for upload files. A session must be asked before. Keep asking until allowed to upload.
    """
    allowed = False
    if MODE != "webserver":
        return {"code": 0, "message": "ok", "data": {"allowed": True}}
    try:
        with Session.connect():
            session = Session.get(s_id=form.s_id)
            allowed = session.ask_for_upload(True)
        return {"code": 0, "message": "ok", "data": {"allowed": allowed}}
    except DoesNotExist:
        return {"code": 1, "message": "Session not initialized. Please GET a session", "data": {"allowed": False}}

@api.post('/ping-upload', responses={200: BaseResponse})
def ping_upload(form: Session):
    """
    When upload waiting, ping to be kept in the waiting line
    """
    if MODE == "webserver":
        with Session.connect():
            session = Session.get(s_id=form.s_id)
            session.ping()
    return {"code": 0, "message": "ok"}

@api.post('/upload', responses={200: BaseResponse})
def upload_file(form: UploadFileForm):
    return NotImplemented
    #return {"code": 0, "message": "ok"}

@api.post('/job', responses={200: JobSubmissionResponse})
def post_jobs(form: JobSubmissionQuery):
    return NotImplemented
    #return {"code": 0, "message": "ok"}

@api.get('/result/<jobid>/dotplot', responses={200: DotplotResponse})
def get_dotplot(path: JobPath):
    """
    Get dotplot data for a job id
    """
    id_f = path.jobid
    paf = os.path.join(APP_DATA, id_f, "map.paf")
    idx1 = os.path.join(APP_DATA, id_f, "query.idx")
    idx2 = os.path.join(APP_DATA, id_f, "target.idx")

    paf = Paf(paf, idx1, idx2)

    if paf.parsed:
        valid = os.path.join(APP_DATA, id_f, ".valid")
        if not os.path.exists(valid):
            Path(valid).touch()
        return {"code": 0, "message": "ok", "data" : paf.get_d3js_data()}
    return {"code": 1, "message": paf.error, "data" : None}