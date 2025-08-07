from __future__ import annotations

import json
import os
import re
import shutil
import traceback
from logging import raiseExceptions
from pathlib import Path
from typing import Iterator

import itertools as it

from flask import current_app
from flask_openapi3 import APIBlueprint
from pydantic import ValidationError

from dgenies import config_reader, APP_DATA, MODE, mailer
from ..allowed_extensions import AllowedExtensions
from ..lib.exceptions import DGeniesJobCheckError, DGeniesExampleInvalid, DGeniesUnknownToolError
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
    BatchSubmissionResponse,
    BatchSubmissionQuery,
    Limits,
    Session,
    SessionResponse,
    UploadFileForm,
    JobStatus,
    JobStatusResponse, JobDescription, Job, JobType, UploadResponseData
)
from .job_descriptions import job_descriptions
from ..lib.upload_file import UploadFile
from ..tools import Tools

from ..views import check_file_type_and_resolv_options, update_files

if MODE == "webserver":
    import dgenies.database as db
    from peewee import DoesNotExist

import logging
logger = logging.getLogger(__name__)

api = APIBlueprint('dgenies', __name__, url_prefix=f"{os.environ.get('URL_PREFIX', '')}/api/v1")

limits = Limits(
    number_of_jobs=config_reader.max_nb_jobs_in_batch_mode,
    file_size=config_reader.max_upload_size,
    uncompressed_size_self_align=config_reader.max_upload_size_ava,
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
        batch_id=Functions.random_job_id(),
        email=Functions.is_email_mandatory(),
        limits=limits,
        #allowed_extensions=allowed_extensions,
        jobs=job_descriptions
    )
    return {"code": 0, "message": "ok", "data": res.model_dump()}

@api.get('/session', responses={200: SessionResponse})
def create_session():
    """
    Ask for a session to upload files and submit a job
    """
    res = Session(session_id = Functions.create_session())
    return {"code": 0, "message": "ok", "data": res.model_dump()}


def delete_session(session_id: str):
    """
    Delete a session
    """
    if MODE == "webserver":
        with db.Session.connect():
            session = db.Session.get(s_id=session_id)
            session.delete_instance()


def allow_upload(session_id: str) -> bool:
    if MODE != "webserver":
        return True
    else:
        with db.Session.connect():
            session = db.Session.get(s_id=session_id)
            return session.ask_for_upload(True)

@api.post('/ask-upload', responses={200: AskUploadResponse})
def ask_upload(form: AskUploadQuery):
    """
    Ask to upload files. A session must be asked before be allowed to use /upload route.
    You must ask regularly until allowed.
    """
    try:
        return {"code": 0, "message": "ok", "data": {"allowed": allow_upload(form.session_id)}}
    except DoesNotExist:
        return {"code": 1, "message": "Session not initialized. Please GET a session", "data": {"allowed": False}}


@api.post('/ping-upload', responses={200: BaseResponse})
def ping_upload(form: Session):
    """
    When upload waiting, ping to be kept in the waiting line
    """
    if MODE == "webserver":
        with db.Session.connect():
            session = db.Session.get(s_id=form.session_id)
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
    # TODO: to normalize and remove
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
    # TODO: to normalize and remove
    if file_role == 'align':
        return 'map'
    return file_role


def get_upload_folder(session_id: str):
    if MODE == "webserver":
        with db.Session.connect():
            session = db.Session.get(s_id=session_id)
            return session.upload_folder
    else:
        return session_id


def allowed_file_ext(filename: str, job_type: str, file_role: str) -> bool:
    """
    Check whether a filename has a valid extension based on job types and file roles it is implied with

    :param filename: the filename
    :type: str
    :param job_type: type of job
    :type: str
    :param file_role: role the file takes
    :type: str
    :return: True if valid format, else False
    :rtype: bool
    """
    allowed_extensions = AllowedExtensions()
    # Get extensions allowed with file role
    extensions = set()
    for fmt in allowed_extensions.get_formats(job_type, file_role):
        extensions.update(allowed_extensions.get_extensions(fmt))
    # Check if format is valid
    return any((filename.endswith(f'.{ext}') for ext in extensions))


@api.post('/upload', responses={200: UploadResponseData})
def upload_file(form: UploadFileForm):
    """
    Do upload of a file
    """
    try:
        upload_folder = os.path.join(current_app.config["UPLOAD_FOLDER"], get_upload_folder(form.session_id))

        if form.file:
            # TODO: sanitize filename earlier
            filename = form.file.filename
            upload_folder = os.path.join(current_app.config["UPLOAD_FOLDER"], upload_folder)
            if not os.path.exists(upload_folder):
                raise BaseException(f'Missing upload folder for session: {form.session_id}')

            # Get list of jobs
            batch_file = os.path.join(upload_folder, 'jobs.json')
            with open(batch_file, 'r') as infile:
                data = json.load(infile)
                batch = BatchSubmissionQuery.model_validate(data)

            # Get missing files for jobs
            needed_files = set(it.chain.from_iterable((get_file_role(job, file_types=['local']) for job in batch.jobs)))
            needed_files = [fn for fn, _ in needed_files if not os.path.exists(os.path.join(upload_folder, fn))]
            print(needed_files)
            # Check if file already exists
            if filename not in needed_files:
                return {
                    "code": 999, "message": "Unneeded file or already uploaded file", "data": {
                        "filename": filename,
                        "job_id": None,
                        "needed_files": needed_files
                    }
                }

            # Get roles for the uploaded file
            roles = set()
            for job in batch.jobs:
                file_roles = get_file_role(job, file_types=['local'])
                roles.update(((job.type, fn, role) for fn, role in file_roles if fn == filename))

            # Sanitize filename
            #filename = Functions.get_valid_uploaded_filename(filename, upload_folder)

            # Validate file roles
            mime_type = form.file.content_type

            if not all((allowed_file_ext(fn, _fix_job_type(job_type.value), role) for job_type, fn, role in roles)):
                logger.info(f"Session {form.session_id}: Filetype not allowed for '{filename}': {', '.join(['(' + jt + ', ' + r + ')' for jt, _, r in roles])}")
                #UploadFile(name=filename, type_f=mime_type, size=0, not_allowed_msg="File type not allowed")
                #shutil.rmtree(upload_folder)
                return {"code": 415, "message": "File type not allowed", "data": {"files": []}}

            else:
                # Save file to disk
                uploaded_file_path = os.path.join(upload_folder, filename)
                logger.info(f"Session '{form.session_id}' starts saving file {uploaded_file_path}")
                form.file.save(uploaded_file_path)
                logger.info(f"Session '{form.session_id}' has saved file {uploaded_file_path}")

                # get file size after saving
                size = os.path.getsize(uploaded_file_path)
                # Check file size
                # TODO

                # return json for js call back
                result = UploadFile(name=filename, type_f=mime_type, size=size)
                needed_files.remove(filename)

                if needed_files:
                    return {
                        "code": 0, "message": "ok", "data": {
                            "needed_files": needed_files,
                            "batch_id": None,
                            "job_ids": None,
                            "file": result.get_file()
                        }
                    }
                else:
                    delete_session(form.session_id)
                    # Create & Launch jobs
                    job_manager = launch_batch(form.session_id, batch.batch_id, batch.email, batch.nb_jobs, batch.jobs)

                    logger.info(f"Session: '{form.session_id}' - Starting job {batch.batch_id}")
                    return {
                        "code": 0, "message": "ok", "data": {
                            "batch_id": job_manager.id_job,
                            "job_ids": job_manager.get_subjob_ids(),
                            "needed_files": [],
                            "file": result.get_file()
                        }
                    }

        return {"code": 404, "message": "No file provided", "data": {"files": [] }}

    except:  # Except all possible exceptions to prevent crashes
        traceback.print_exc()
        return {"code": 500, "message": "An unexpected error has occurred on upload. Please contact the support.",
                "data": {"files": [] }}


def valid_email(email: str|None):
    """
    Validate email
    """
    if Functions.is_email_mandatory():
        if not email:
            ValidationError("Email not given")
        elif not re.match(r"^.+@.+\..+$", email):
            # The email regex is simple because checking email address is not simple (RFC3696).
            # Sending an email to the address is the most reliable way to check if the email address is correct.
            # The only constraints we set on the email address are:
            # - to have at least one @ in it, with something before and something after
            # - to have something.tdl syntax for email server, as it will be used over Internet (not mandatory in RFC)
            ValidationError("Email is invalid")


def valid_job(job: Job):
    """
    Check if a job description is valid according to its type.
    """
    if job.type == JobType.align:
        # Valid input files (type, syntax)

        # Valid tool + options
        pass

    elif job.type == JobType.plot:
        # Valid input files (type, syntax)

        pass

    else:
        raise ValidationError(f"Job type '{job.type}' is not supported")

def valid_form(form: BatchSubmissionQuery):
    """
    Check if a job description is valid according to its type.
    """
    if len(form.jobs) != form.nb_jobs:
        raise ValidationError()
    valid_email(form.email)
    if form.nb_jobs < 1:
        raise ValidationError("No job provided")
    elif form.nb_jobs == 1:
        # Batch id is ignored when running 1 job only
        valid_job(form.jobs[0])
    else :
        if form.batch_id == "":
            raise ValidationError("Batch id is required")
        for job in form.jobs:
            valid_job(job)
    pass


def get_file_role(job: Job, file_types: list[str] = ['local', 'url']) -> Iterator[tuple[str, str]]:
    """
    Get list of files from list of jobs. Can be filtered according to their type (local or url)

    :param job: the job
    :type job: Job
    :param file_types: the type of files to filter, can be 'local' or 'url'
    :type file_types: list[str]
    :return: a tuple:
        -[0] the file name
        -[1] the file role
    :rtype: Iterator[tuple[str, list[str]]]
    """
    roles = []
    if job.type == JobType.align:
        roles = ["query", "target"]
    elif job.type == JobType.plot:
        if job.backup:
            roles = ["query", "target", "align"]
        else:
            roles = ["backup"]
    for role in roles:
        file_type = getattr(job, role + '_type')
        if file_type in file_types:
            yield getattr(job, role), role


@api.post('/job', responses={200: BatchSubmissionResponse})
def post_jobs(form: BatchSubmissionQuery):
    """
    Launch the job
    """

    try:
        valid_form(form)
        form_pass = True
    except ValidationError as e:
        message = e.message
        form_pass = False

    # Check batch form
    # We get the distinct client's message elements
    #batch_id, email, nb_jobs, jobs = parse_form(form)
    """
    # We check each job parameters
    for j in jobs:
        try:
            check_file_type_and_resolv_options(j)
        except DGeniesJobCheckError as e:
            form_pass = False
            errors.append(e.message)
    """

    if form_pass:
        try:
            # Create a session
            session_id = Functions.create_session()

            # Serialize the batch job into the upload folder
            upload_folder = os.path.join(current_app.config["UPLOAD_FOLDER"], get_upload_folder(session_id))
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            batch_file =  os.path.join(upload_folder, 'jobs.json')
            logger.info(f'writing jobs to {batch_file}')
            with open(batch_file, 'w') as outfile:
                json.dump(form.model_dump(), outfile)

            # Get files from jobs in form
            needed_files = set(it.chain.from_iterable((get_file_role(job, file_types=['local']) for job in form.jobs)))

            if needed_files:
                return {"code": 0, "message": "ok", "data": {
                    "batch_id": None,
                    "job_ids": None,
                    "session_id": session_id,
                    "needed_files": [f for f, _ in needed_files],
                    "allowed_upload": allow_upload(session_id)
                }}
            else:
                delete_session(session_id)

                # Create & Launch jobs
                job_manager = launch_batch(session_id, form.batch_id, form.email, form.nb_jobs, form.jobs)

                return {"code": 0, "message": "ok", "data": {
                    "batch_id": job_manager.id_job,
                    "job_ids": job_manager.get_subjob_ids(),
                    "session_id": None,
                    "needed_files": None,
                    "allowed_upload": False
                }}

        except DGeniesExampleInvalid as e:
            return {"code": 404, "message": e.message}

        except Exception:
            traceback.print_exc()
            return {"code": 500, "message": "Something went wrong during job creation!"}

    else:
        return {"code": 406, "message": "Incorrect form {message}"}

def get_tools_options(tool_name, chosen_options):
    """
    Transform options chosen from client side into option values

    :param tool_name: the tool name
    :type tool_name: str
    :param chosen_options: the list of option ids
    :type chosen_options: list of str
    :return: return options value
    :rtype: list
    """
    tools = Tools().tools
    if tool_name is None or tool_name not in tools:
        raise DGeniesUnknownToolError(tool_name)
    return tools[tool_name].resolve_option_keys(chosen_options)


def prepare_jobs(email: str, jobs: list[Job]) -> list[dict]:
    # convert to legacy job dict
    result = []
    for job in jobs:
        result.append({
            "job_id": job.job_id,
            "email": email,
            "query": job.query if job.query else None,
            "query_type": job.query_type.value if job.query else None,
            "target": job.target if job.target else None,
            "target_type": job.target_type.value if job.target else None,
            "tool": job.tool.value if job.tool else None,
            "align":  job.align if job.align else None,
            "align_type": job.align_type.value if job.align else None,
            "backup": job.backup if job.backup else None,
            "backup_type": job.backup_type.value if job.backup else None,
            "options": " ".join(get_tools_options(job.tool.value, job.tool_option)) if job.tool_option else None
        })
    return result

#def launch_batch(session_id: str, form: BatchSubmissionQuery) -> JobManager:
def launch_batch(session_id: str, batch_id: str, email: str, nb_jobs: int, jobs: list[Job]) -> JobManager:

    #batch_id, email, nb_jobs, jobs = form.batch_id, form.email, form.nb_jobs, form.jobs
    upload_folder = os.path.join(current_app.config["UPLOAD_FOLDER"], get_upload_folder(session_id))

    if nb_jobs > 1:
        job_id = batch_id
        job_type = 'batch'
    elif nb_jobs == 1:
        job_id = jobs[0].job_id
        job_type = jobs[0].type.value
    else:
        raise BaseException(f'Session {session_id}: No job provided')

    # Get final job id (sanitize and avoid collision):
    job_id = re.sub(r'[^A-Za-z0-9_\-]+', '', job_id.replace(" ", "_"))
    job_id_orig = job_id
    i = 2
    while os.path.exists(os.path.join(APP_DATA, job_id)):
        job_id = job_id_orig + ("_%d" % i)
        i += 1

    # Prepare job workspace
    folder_files = os.path.join(APP_DATA, job_id)
    os.makedirs(folder_files)

    legacy_jobs = prepare_jobs(email, jobs[0:nb_jobs])
    # Transform files path into datafiles:
    update_files(legacy_jobs, upload_folder)

    print(legacy_jobs)
    # Launch job:
    job = JobManager.create(id_job=job_id, job_type=job_type, jobs=legacy_jobs, email=email, mailer=mailer)
    if MODE == "webserver":
        job.launch()
    else:
        job.launch_standalone()

    return job


def create_job_status(answer: dict) -> JobStatus:
    subjob_status: list[JobStatus] = []
    if "batch" in answer:
        for j in answer["batch"]:
            subjob_status.append(create_job_status(Functions().get_status(JobManager(j["job_id"]))))
    res = JobStatus(
            job_id=answer["id_job"],
            status=answer.get("status", 'unknown'),
            error=answer.get("error", None),
            has_logs=answer.get("has_logs", False),
            mem_peak=answer.get("mem_peak", None),
            time_elapsed=answer.get("time_elapsed", None),
            batch=subjob_status if subjob_status else None
    )
    return res


@api.get('/status/<job_id>', responses={200: JobStatusResponse})
def get_status(path: JobPath):
    """
    Get status for a job id
    """
    job = JobManager(id_job=path.job_id)
    answer = Functions().get_status(job)
    try:
        if answer["status"] == "unknown":
            return {"code": 404, "message": "Job does not exists", "data": None}
        return {"code": 0, "message": "ok", "data" : create_job_status(answer).model_dump()}
    except KeyError:
        return {"code": 500, "message": "Unknown error, please contact support", "data": None}


@api.get('/result/<job_id>/dotplot', responses={200: DotplotResponse})
def get_dotplot(path: JobPath):
    """
    Get dotplot data for a job id
    """
    id_f = path.job_id
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