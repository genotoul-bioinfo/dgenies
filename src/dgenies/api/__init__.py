import os
import re
import shutil
import traceback
from pathlib import Path
from flask import current_app, url_for
from flask_openapi3 import APIBlueprint
from peewee import DoesNotExist

from dgenies import config_reader, APP_DATA, MODE, mailer
from ..lib.exceptions import DGeniesJobCheckError, DGeniesExampleInvalid
from ..lib.functions import Functions
from ..lib.job_manager import JobManager
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
    UploadFileForm,
    JobStatus,
    JobStatusResponse
)
from .job_descriptions import job_descriptions
from ..lib.upload_file import UploadFile


from ..views import check_file_type_and_resolv_options, update_files

if MODE == "webserver":
    import dgenies.database as db
    from peewee import DoesNotExist

import logging
logger = logging.getLogger(__name__)

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
    res = Session(s_id = Functions.create_session())
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
        with db.Session.connect():
            session = db.Session.get(s_id=form.s_id)
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
        with db.Session.connect():
            session = db.Session.get(s_id=form.s_id)
            session.ping()
    return {"code": 0, "message": "ok"}


def _fix_job_type(job_type: str) -> str:
    """
    Fix job type between api and dgenies inner type (will be normalized in future)

    :param job_type: the job type
    :type: str
    :return: fixed job type
    :rtype: str
    """
    if job_type == 'align':
        return 'new'
    return job_type

def _fix_file_role(file_role: str) -> str:
    """
    Fix the file role between api and dgenies inner type (will be normalized in future)

    :param file_role: the job type
    :type: str
    :return: fixed job type
    :rtype: str
    """
    if file_role == 'align':
        return 'map'
    return file_role

@api.post('/upload', responses={200: BaseResponse})
def upload_file(form: UploadFileForm):
    """
    Do upload of a file
    """
    try:
        if MODE == "webserver":
            try:
                with db.Session.connect():
                    session = db.Session.get(s_id=form.s_id)
                    if session.ask_for_upload(False):
                        folder = session.upload_folder
                    else:
                        return {"code": 403, "message": "Not allowed to upload!", "data": {"files": []}}
            except DoesNotExist:
                return {"code": 401, "message": "Session not initialized. Please ask for a session before", "data": {"files": []}}
        else:
            folder = form.s_id

        print(form.s_id)
        print(form.file.filename)
        print(form.jobtype)
        print(form.filetype)

        if form.file:
            filename = form.file.filename
            folder_files = os.path.join(current_app.config["UPLOAD_FOLDER"], folder)
            if not os.path.exists(folder_files):
                os.makedirs(folder_files)
            filename = Functions.get_valid_uploaded_filename(filename, folder_files)
            mime_type = form.file.content_type

            if not Functions.allowed_file_ext(
                    filename,
                    job_types=set([_fix_job_type(t.value) for t in form.jobtype]),
                    file_roles=set([_fix_file_role(t.value) for t in form.filetype])
                ):
                shutil.rmtree(folder_files)
                return {"code": 415, "message": "File type not allowed", "data": {"files": []}}

            else:
                # save file to disk
                uploaded_file_path = os.path.join(folder_files, filename)
                logger.info(f"Session '{form.s_id}' starts saving file {uploaded_file_path}")
                form.file.save(uploaded_file_path)
                logger.info(f"Session '{form.s_id}' has saved file {uploaded_file_path}")

                # get file size after saving
                size = os.path.getsize(uploaded_file_path)
                # return json for js call back
                result = UploadFile(name=filename, type_f=mime_type, size=size)

            return {"code": 0, "message": "ok", "data": {"files": [result.get_file()] }}
        return {"code": 404, "message": "No file provided", "data": {"files": [] }}

    except:  # Except all possible exceptions to prevent crashes
        traceback.print_exc()
        return {"code": 500, "message": "An unexpected error has occurred on upload. Please contact the support.",
                "data": {"files": [] }}


def parse_form(form):
    id_job, job_type, email, nb_jobs = form.id_job, form.type.value, form.email, form.nb_jobs
    jobs = list()
    for i in range(0, nb_jobs):
        jt = form.jobs[i]
        j = {
            "id_job": jt.id_job,
            "email": email,
            "type": jt.type.value,
            "query": jt.query if jt.query else None,
            "query_type": jt.query_type.value if jt.query else None,
            "target": jt.target if jt.target else None,
            "target_type": jt.target_type.value if jt.target else None,
            "align": jt.align if jt.align else None,
            "align_type": jt.align_type.value if jt.align else None,
            "backup": jt.backup if jt.backup else None,
            "backup_type": jt.backup_type.value if jt.backup else None,
            "tool": jt.tool.value if jt.tool else None
        }
        j["options"] = jt.tool_option if jt.tool_option else []
        jobs.append(j)
    return id_job, job_type, email, nb_jobs, jobs


@api.post('/job', responses={200: JobSubmissionResponse})
def post_jobs(form: JobSubmissionQuery):
    """
    Launch the job
    """
    if MODE == "webserver":
        try:
            with db.Session.connect():
                session = db.Session.get(s_id=form.s_id)
        except DoesNotExist:
            return {"code": 404, "message": "Session has expired."}
        upload_folder = session.upload_folder
        # Delete session:
        session.delete_instance()
    else:
        upload_folder = form.s_id

    # We get the distinct client's message elements
    id_job, job_type, email, nb_jobs, jobs = parse_form(form)

    # Check form
    # Client side must have sent correct message depending on the job type.
    # Here we check that everything was correctly transmitted.
    # Convention:
    # - an element set to None is not checked
    # - an element set to "" is checked but empty.
    form_pass = True
    errors = []

    # We check job header (id + email)
    if id_job == "":
        errors.append("Id of job not given")
        form_pass = False

    # An email is required in webserver mode
    if Functions.is_email_mandatory():
        if email == "":
            errors.append("Email not given")
            form_pass = False
        elif not re.match(r"^.+@.+\..+$", email):
            # The email regex is simple because checking email address is not simple (RFC3696).
            # Sending an email to the address is the most reliable way to check if the email address is correct.
            # The only constraints we set on the email address are:
            # - to have at least one @ in it, with something before and something after
            # - to have something.tdl syntax for email server, as it will be used over Internet (not mandatory in RFC)
            errors.append("Email is invalid")
            form_pass = False

    # We check each job parameters

    for j in jobs:
        try:
            check_file_type_and_resolv_options(j)
        except DGeniesJobCheckError as e:
            form_pass = False
            errors.append(e.message)

    # Form pass
    if form_pass:
        # Get final job id (sanitize and avoid collision):
        id_job = re.sub(r'[^A-Za-z0-9_\-]+', '', id_job.replace(" ", "_"))
        id_job_orig = id_job
        i = 2
        while os.path.exists(os.path.join(APP_DATA, id_job)):
            id_job = id_job_orig + ("_%d" % i)
            i += 1

        folder_files = os.path.join(APP_DATA, id_job)
        os.makedirs(folder_files)

        # Transform files path into datafiles:
        try:
            update_files(jobs, upload_folder)
            # Launch job:
            print(id_job, job_type, email)
            print(jobs[0:nb_jobs])

            job = JobManager.create(id_job=id_job, job_type=job_type, jobs=jobs, email=email, mailer=mailer)
            if MODE == "webserver":
                job.launch()
            else:
                job.launch_standalone()
            return {"code": 0, "message": "ok", "data": {"job_id": id_job}}

        except DGeniesExampleInvalid as e:
            return {"code": 404, "message": e.message}

        except Exception:
            traceback.print_exc()
            return {"code": 500, "message": "Something went wrong during job creation!"}
    else:
        return {"code": 406, "message": "Incorrect form", "data": {"errors": errors}}


def create_job_status(answer: dict) -> JobStatus:
    subjob_status: list[JobStatus] = []
    if "batch" in answer:
        for j in answer["batch"]:
            subjob_status.append(create_job_status(Functions().get_status(JobManager(j["id_job"]))))
    res = JobStatus(
            jobid=answer["id_job"],
            status=answer.get("status", 'unknown'),
            error=answer.get("error", None),
            has_logs=answer.get("has_logs", False),
            mem_peak=answer.get("mem_peak", None),
            time_elapsed=answer.get("time_elapsed", None),
            batch=subjob_status if subjob_status else None
    )
    return res


@api.get('/status/<jobid>', responses={200: JobStatusResponse})
def get_status(path: JobPath):
    """
    Get status for a job id
    """
    job = JobManager(path.jobid)
    answer = Functions().get_status(job)
    try:
        if answer["status"] == "unknown":
            return {"code": 404, "message": "Job does not exists", "data": None}
        return {"code": 0, "message": "ok", "data" : create_job_status(answer).model_dump()}
    except KeyError:
        return {"code": 500, "message": "Unknown error, please contact support", "data": None}


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