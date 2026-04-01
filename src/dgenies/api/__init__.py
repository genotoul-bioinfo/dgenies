from __future__ import annotations

import json
import os
import re
import traceback
from http import HTTPStatus
from pathlib import Path
from typing import (
    Any,
    Iterator
)

import itertools as it

from flask import current_app, make_response
from flask_openapi3 import APIBlueprint
from werkzeug.exceptions import RequestEntityTooLarge

from dgenies import config_reader, APP_DATA, MODE, mailer
from ..allowed_extensions import AllowedExtensions
from ..lib.exceptions import (
    DGeniesDeleteGalleryJobForbidden,
    DGeniesExampleInvalid,
    DGeniesMissingJobError,
    DGeniesNotGzipFileError,
    DGeniesUnknownOptionError,
    DGeniesUnknownToolError,
    DGeniesUploadedFileSizeLimitError,
    DGeniesValidationError,
)
from ..lib.functions import Functions
from ..lib.job_manager import JobManager
from ..lib.paf import Paf

from .datamodels import (
    BaseResponse,
    NotFoundResponse,
    NotImplementedResponse,
    AskUploadQuery,
    AskUploadResponse,
    Config,
    ConfigResponse,
    DotplotResponse,
    GalleryResponse,
    JobFilePath,
    JobPath,
    BatchSubmissionResponse,
    BatchSubmissionQuery,
    Limits,
    Session,
    SessionResponse,
    UploadFileForm,
    JobStatus,
    JobStatusResponse,
    JobDescription,
    Job,
    JobType,
    UploadResponse,
    SummaryResponse,
    QTAssoc,
    QTAssocRecord,
    QTAssocResponse,
    NoAssoc,
    NoAssocInput,
    NoAssocResponse,
    ExampleFilesResponse,
    PrepareFasta,
    PrepareFastaInput,
    PrepareFastaEnum,
    PrepareFastaResponse
)
from .job_descriptions import job_descriptions
from ..lib.upload_file import UploadFile
from ..tools import Tools

from ..views import update_files, compute_summary, build_fasta, get_inforun

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

notImplementedResponse = NotImplementedResponse()

def get_max_file_size(job_type: JobType, role: str) -> int:
    if job_type == "align" and role == "target":
        return config_reader.max_upload_size_ava
    return config_reader.max_upload_size

@api.get('/config', responses={200: ConfigResponse})
def get_config():
    """
    Get this D-Genies instance configuration and limits
    """
    res = Config(
        banner=get_inforun(),
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


def delete_session(session_id: str) -> None:
    """
    Delete a session
    """
    if MODE == "webserver":
        with db.Session.connect():
            session = db.Session.get(s_id=session_id)
            session.delete_instance()


def allow_upload(session_id: str) -> bool:
    """
    Tell if the upload is allowed for a session id

    :param session_id: the session id
    :type: str
    :return: True if the upload is allowed, False else
    :rtype: bool
    """
    if MODE != "webserver":
        return True
    else:
        with db.Session.connect():
            session = db.Session.get(s_id=session_id)
            return session.ask_for_upload(True)

@api.post('/ask-upload',
          responses={
              200: AskUploadResponse,
              403: BaseResponse
          })
def ask_upload(body: AskUploadQuery):
    """
    Ask to upload files. A session must be asked before be allowed to use /upload route.
    You must ask regularly until allowed.
    """
    try:
        return {"code": 0, "message": "ok", "data": {"allowed": allow_upload(body.session_id)}}, 200
    except DoesNotExist:
        return {"code": 403, "message": "Session not initialized. Please GET a session"}, 403


@api.post('/ping-upload',
          responses={
              200: BaseResponse,
              404: NotFoundResponse
          })
def ping_upload(body: Session):
    """
    When upload waiting, ping to be kept in the waiting line
    """
    if MODE == "webserver":
        try:
            with db.Session.connect():
                session = db.Session.get(s_id=body.session_id)
                session.ping()
        except DoesNotExist:
            return {"code": 404, "message": "Session doesn't exist"}, 404
        except Exception:
            logger.error(traceback.format_exc())
            return {"code": 500, "message": "Internal error"}, 500
    return {"code": 0, "message": "ok"}, 200


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
    """
    Get the upload folder for a session id

    :param session_id: the session id
    :type: str
    """
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


@api.post('/upload',
          responses={
              200: UploadResponse,
              403: UploadResponse,
              404: UploadResponse,
              413: UploadResponse,
              415: UploadResponse
          })
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
            needed_files = {fn for fn, _ in needed_files if not os.path.exists(os.path.join(upload_folder, fn))}

            # Check if file already exists
            if filename not in needed_files:
                return {
                    "code": 403, "message": "Unneeded file or already uploaded file", "data": {
                        "filename": filename,
                        "job_id": None,
                        "needed_files": [f for f in needed_files]
                    }
                }, 403

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
                return {"code": 415, "message": "File type not allowed", "data": {"files": [f for f in needed_files]}}, 415

            else:
                # Save file to disk
                uploaded_file_path = os.path.join(upload_folder, filename)
                logger.info(f"Session '{form.session_id}' starts saving file {uploaded_file_path}")
                form.file.save(uploaded_file_path)
                logger.info(f"Session '{form.session_id}' has saved file {uploaded_file_path}")

                # get file size after saving
                size = os.path.getsize(uploaded_file_path)
                # Check file size
                compressed = uploaded_file_path.endswith(".gz")
                if compressed and not Functions.is_gz_file(uploaded_file_path):
                    # Check file is correctly gzipped
                    #raise DGeniesNotGzipFileError(filename)
                    return {"code": 415, "message": "Not a gzip file", "data": {"files": [f for f in needed_files]}}, 415

                min_allowed_size = min((get_max_file_size(j, r) for j, fn, r in roles))
                if size > min_allowed_size:
                    #raise DGeniesUploadedFileSizeLimitError(filename, Functions.get_readable_size(size, base="MiB"),
                    #                                        unit="Mb", compressed=compressed)
                    return {"code": 413, "message": "File too large", "data": {"files": [f for f in needed_files]}}, 413

                # return json for js call back
                result = UploadFile(name=filename, type_f=mime_type, size=size)
                needed_files.remove(filename)

                if needed_files:
                    return {
                        "code": 0, "message": "ok", "data": {
                            "needed_files": [f for f in needed_files],
                            "batch_id": None,
                            "job_ids": None,
                            "file": result.get_file()
                        }
                    }, 200
                else:
                    # Create & Launch jobs
                    job_manager = launch_batch(form.session_id, batch.batch_id, batch.email, batch.nb_jobs, batch.jobs)
                    logger.info(f"Session: '{form.session_id}' - Starting job {batch.batch_id}")
                    subjobs = job_manager.get_subjob_ids()
                    print(subjobs)
                    return {
                        "code": 0, "message": "ok", "data": {
                            "batch_id": job_manager.id_job,
                            "job_ids": subjobs if subjobs else [job_manager.id_job],
                            "needed_files": [],
                            "file": result.get_file()
                        }
                    }, 200

        return {"code": 404, "message": "No file provided", "data": {"files": [] }}, 404

    except:  # Except all possible exceptions to prevent crashes
        traceback.print_exc()
        return {"code": 500, "message": "An unexpected error has occurred on upload. Please contact the support."}, 500


def valid_email(email: str|None):
    """
    Validate email
    """
    if Functions.is_email_mandatory():
        if not email:
            raise DGeniesValidationError("Email not given")
        elif not re.match(r"^.+@.+\..+$", email):
            # The email regex is simple because checking email address is not simple (RFC3696).
            # Sending an email to the address is the most reliable way to check if the email address is correct.
            # The only constraints we set on the email address are:
            # - to have at least one @ in it, with something before and something after
            # - to have something.tdl syntax for email server, as it will be used over Internet (not mandatory in RFC)
            raise DGeniesValidationError("Email is invalid")


def valid_align(job: Job) -> Job:
    """
    Valid and complete with default values parameters of an align job

    :param job: the job
    :type job: Job
    :return: The job modified to include default parameters if missing.
    :rtype: Job
    """
    print(job)
    # Valid input files (type, syntax)
    if not job.target:
        raise DGeniesValidationError("'target' is required")
    if not job.target_type:
        raise DGeniesValidationError("'target_type' is required (either 'local' or 'url'")
    if job.query and not job.query_type:
        raise DGeniesValidationError("'query_type' is required (either 'local' or 'url'")
    # validate file based on name extension

    # Valid tool + options
    if not job.tool:
        job.tool = Tools().get_default()
    elif job.tool not in Tools().tools:
        raise DGeniesUnknownToolError(job.tool)
    tool = Tools().tools[job.tool]
    # Check options
    unknown_options = [opt for opt in job.tool_options if opt not in tool.get_options_keys()]
    # Get missing default options
    if unknown_options:
        raise DGeniesUnknownOptionError(", ".join(unknown_options))
    job.tool_options.extend(tool.get_default_options(job.tool_options))
    return job


def valid_plot(job: Job) -> Job:
    """
    Valid and complete with default values parameters of a plot job

    :param job: the job
    :type job: Job
    :return: The job modified to include default parameters if missing.
    :rtype: Job
    """
    print(job)
    if job.backup:
        if not job.target_type:
            raise DGeniesValidationError("'target_type' is required (either 'local' or 'url'")
        if job.query and not job.query_type:
            raise DGeniesValidationError("'query_type' is required (either 'local' or 'url'")
        # validate file based on name extension
    else:
        if not job.target:
            raise DGeniesValidationError("'target' is required")
        if not job.target_type:
            raise DGeniesValidationError("'target_type' is required (either 'local' or 'url'")
        if not job.query:
            raise DGeniesValidationError("'query' is required")
        if not job.query_type:
            raise DGeniesValidationError("'query_type' is required (either 'local' or 'url'")
        if not job.align:
            raise DGeniesValidationError("'align' is required")
        if not job.align_type:
            raise DGeniesValidationError("'align_type' is required (either 'local' or 'url'")
    return job


def valid_job(job: Job) -> Job:
    """
    Valid and complete with default values parameters of a job.

    :param job: the job
    :type job: Job
    :return: The job modified to include default parameters if missing.
    :rtype: Job
    """
    if job.type == JobType.align:
        return valid_align(job)
    elif job.type == JobType.plot:
        return valid_plot(job)
    else:
        raise DGeniesValidationError(f"Job type '{job.type}' is not supported")

def valid_form(form: BatchSubmissionQuery) -> None:
    """
    Valid and complete with default values parameters of a submission of jobs.

    :param form: the job
    :type form: BatchSubmissionQuery
    """
    if len(form.jobs) != form.nb_jobs:
        raise DGeniesValidationError("Incorrect number of jobs")
    valid_email(form.email)
    if form.nb_jobs < 1:
        raise DGeniesValidationError("No job provided")
    elif form.nb_jobs == 1:
        # Batch id is ignored when running 1 job only
        valid_job(form.jobs[0])
    else :
        if form.batch_id == "":
            raise DGeniesValidationError("Batch id is required")
        for job in form.jobs:
            valid_job(job)

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
            roles = ["backup"]
        else:
            roles = ["query", "target", "align"]
    for role in roles:
        file_type = getattr(job, role + '_type')
        if file_type in file_types:
            yield getattr(job, role), role


@api.post('/job',
          responses={
              200: BatchSubmissionResponse,
              400: BaseResponse,
              404: NotFoundResponse,
              500: BaseResponse
          })
def post_jobs(body: BatchSubmissionQuery):
    """
    Launch the job
    """
    form = body
    message = "Unknown error"
    try:
        valid_form(form)
        form_pass = True
    except DGeniesValidationError as e:
        message = e.message
        form_pass = False

    if form_pass:
        try:
            # Create a session
            session_id = Functions.create_session()

            # Serialize the batch job into the upload folder
            upload_folder = os.path.join(current_app.config["UPLOAD_FOLDER"], get_upload_folder(session_id))
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            batch_file = os.path.join(upload_folder, 'jobs.json')
            logger.info(f'writing jobs to {batch_file}')
            with open(batch_file, 'w') as outfile:
                json.dump(form.model_dump(), outfile)

            # Get files from jobs in form
            needed_files = set(it.chain.from_iterable((get_file_role(job, file_types=['local']) for job in form.jobs)))
            needed_files = [f for f, _ in needed_files if f]

            if needed_files:
                return {"code": 0, "message": "ok", "data": {
                    "batch_id": None,
                    "job_ids": None,
                    "session_id": session_id,
                    "needed_files": needed_files,
                    "allowed_upload": allow_upload(session_id)
                }}, 200
            else:
                delete_session(session_id)
                # Create & Launch jobs
                job_manager = launch_batch(session_id, form.batch_id, form.email, form.nb_jobs, form.jobs)
                logger.info(f"Session: '{session_id}' - Starting job {form.batch_id}")
                subjobs = job_manager.get_subjob_ids()
                return {"code": 0, "message": "ok", "data": {
                    "batch_id": job_manager.id_job,
                    "job_ids": subjobs if subjobs else [job_manager.id_job],
                    "session_id": None,
                    "needed_files": [],
                    "allowed_upload": False
                }}, 200

        except DGeniesExampleInvalid as e:
            return {"code": 404, "message": e.message}, 404

        except Exception:
            traceback.print_exc()
            return {"code": 500, "message": "Something went wrong during job creation!"}, 500

    else:
        return {"code": 400, "message": f"Incorrect form: {message}"}, 400

def get_tools_options(tool_name: str, chosen_options: list[str]) -> list[str]:
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
    """
    Convert a list of jobs into a legacy list of dict of jobs

    :param email: the email
    :type email: str
    :param jobs: the list of jobs
    :type jobs: list of Job
    :return: return options value
    :rtype: list of dict
    """
    result = []
    for job in jobs:
        result.append({
            "job_id": job.job_id,
            "type": job.type,
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
            "options": " ".join(get_tools_options(job.tool.value, job.tool_options)) if job.tool_options else None
        })
    return result

#def launch_batch(session_id: str, form: BatchSubmissionQuery) -> JobManager:
def launch_batch(session_id: str, batch_id: str, email: str, nb_jobs: int, jobs: list[Job]) -> JobManager:
    """
    Run a batch of jobs

    :param session_id: the session id
    :type session_id: str
    :param batch_id: the batch id
    :type batch_id: str
    :param email: the email
    :type email: str
    :param nb_jobs: the number of jobs
    :type nb_jobs: int
    :param jobs: the list of jobs
    :type jobs: list of Job
    :return: A job manager
    :rtype: JobManager
    """
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
    delete_session(session_id)

    print(legacy_jobs)
    # Launch job:
    job = JobManager.create(id_job=job_id, job_type=job_type, jobs=legacy_jobs, email=email, mailer=mailer)
    if MODE == "webserver":
        job.launch()
    else:
        job.launch_standalone()
    return job


def get_percentage(status: str) -> float:
    """
    Get percentage from status string

    :param status: the job status
    :type status: str
    :return: a percentage that takes value between 0 and 100
    :rtype: float
    """
    if status in ["getfiles", "getfiles-waiting"]:
        return 3.7
    elif status == "waiting":
        return 7
    elif status in ["preparing", "prepare-scheduled", "preparing-cluster"]:
        return 10.7
    elif status == "prepared":
        return 20.4
    elif status == "scheduled":
        return 30.3
    elif status in ["starting", "scheduled-cluster"]:
        return 35.2
    elif status in ["started", "started-batch"]:
        return 40.3
    elif status == "succeed":
        return 75.0
    elif status == "merging":
        return 80.4
    elif status in ["success", "no-match", "fail"]:
        return 100
    return 0

def create_job_status(answer: dict[str, Any]) -> JobStatus:
    """
    Convert legacy status answer to the new status object

    :param answer: the legacy status answer
    :type answer: dict
    :return: the new status answer
    :rtype: JobStatus
    """
    error = answer.get("error", None)
    status = answer.get("status", 'unknown')
    res = JobStatus(
            job_id=answer["id_job"],
            percent=get_percentage(status),
            status=status,
            error=error if error else None,
            has_logs=answer.get("has_logs", False),
            mem_peak=answer.get("mem_peak", None),
            time_elapsed=answer.get("time_elapsed", None)
    )
    return res


def has_sorted_output(job_id: str) -> bool:
    """
    Check that sorted output files are present for a job.
    """
    job_dir = os.path.join(APP_DATA, job_id)
    return all(
        os.path.exists(os.path.join(job_dir, f))
        for f in [".sorted", "map.paf.sorted", "query.idx.sorted"]
    )


@api.get('/status/<job_id>',
         responses={
             200: JobStatusResponse,
             404: NotFoundResponse,
             500: BaseResponse
         })
def get_status(path: JobPath):
    """
    Get status for a job id
    """
    job = JobManager(id_job=path.job_id)
    answer = Functions().get_status(job)
    try:
        if answer["status"] == "unknown":
            return {"code": 404, "message": "Job does not exists"}, 404
        return {"code": 0, "message": "ok", "data" : create_job_status(answer).model_dump()}
    except KeyError:
        return {"code": 500, "message": "Unknown error, please contact support"}, 500


@api.get('/result/<job_id>/dotplot',
         responses={
             200: DotplotResponse,
             404: NotFoundResponse,
             500: BaseResponse,
         })
def get_dotplot(path: JobPath):
    """
    Get dotplot data for a job id
    """
    id_f = path.job_id
    paf = os.path.join(APP_DATA, id_f, "map.paf")
    idx1 = os.path.join(APP_DATA, id_f, "query.idx")
    idx2 = os.path.join(APP_DATA, id_f, "target.idx")
    try:
        paf = Paf(paf, idx1, idx2)
        if paf.parsed:
            valid = os.path.join(APP_DATA, id_f, ".valid")
            if not os.path.exists(valid):
                Path(valid).touch()
            return {"code": 0, "message": "ok", "data" : paf.get_dotplot_data(sorted=False)}
        return {"code": 500, "message": paf.error}
    except FileNotFoundError:
        return {"code": 404, "message": "Job not found"}, 404

@api.get('/result/<job_id>/sorted-dotplot',
         responses={
             200: DotplotResponse,
             403: BaseResponse,
             404: NotFoundResponse,
             500: BaseResponse,
         })
def sorted_dotplot(path: JobPath):
    """
    Get sorted dot plot to reference
    """
    id_res = path.job_id
    job_dir = os.path.join(APP_DATA, id_res)
    try:
        if not os.path.exists(job_dir):
            return {"code": 404, "message": "Job not found"}, 404
        if os.path.exists(os.path.join(job_dir, ".all-vs-all")):
            return {"code": 403, "message": "Sort is not available for Self Align mode"}, 403
        paf_file = os.path.join(job_dir, "map.paf")
        idx1 = os.path.join(job_dir, "query.idx")
        idx2 = os.path.join(job_dir, "target.idx")
        paf = Paf(paf_file, idx1, idx2, False)
        paf.sort()
        # TODO: maybe clean this part
        if paf.parsed:
            return {"code": 0, "message": "ok", "data": paf.get_dotplot_data(sorted=True)}, 200
        return {"code": 500, "message": paf.error}, 500
    except FileNotFoundError:
        return {"code": 500, "message": "Server error"}, 500


@api.get('/result/<job_id>/summary',
         responses={
             200: SummaryResponse,
             404: NotFoundResponse,
             500: BaseResponse
         })
def get_summary(path: JobPath):
    """
    Get dot plot summary
    """
    percents, s_status = compute_summary(path.job_id)
    if s_status == "file_not_found":
        return {
            "code": 404, "message": "Unable to load data!", "data": {}
        }, 404
    if s_status == "job_not_found":
        return {
            "code": 404, "message": "Job does not exists!", "data": {}
        }, 404
    if s_status == "fail":
        return {
            "code": 500, "message": "Build of summary failed. Please contact us to report the bug"
        }, 500
    return {"code": 0, "message": s_status, "data": percents}, 200


@api.get('/sort/<job_id>',
          responses={
              200: BaseResponse,
              404: NotFoundResponse,
              500: BaseResponse
          })
def post_sort(path: JobPath):
    """
    Sort dot plot to reference
    """
    id_res = path.job_id
    job_dir = os.path.join(APP_DATA, id_res)

    if os.path.exists(os.path.join(job_dir, ".all-vs-all")):
        return {"code": 404, "message": "Sort is not available for All-vs-All mode"}, 404

    if has_sorted_output(id_res):
        return {"code": 0, "message": "ok"}, 200

    paf_file = os.path.join(job_dir, "map.paf")
    idx1 = os.path.join(job_dir, "query.idx")
    idx2 = os.path.join(job_dir, "target.idx")
    paf = Paf(paf_file, idx1, idx2, False)
    paf.sort()
    if paf.parsed and has_sorted_output(id_res):
        return {"code": 0, "message": "ok"}, 200
    if not paf.error:
        return {"code": 500, "message": "Sort output was not produced"}, 500
    return {"code": 500, "message": paf.error}, 500


@api.post('/reset-sort/<job_id>',
          responses={
              200: BaseResponse,
              404: BaseResponse
          })
def post_reset_sort(path: JobPath):
    """
    Reset sort on dotplot
    """
    id_res = path.job_id
    to_remove = [".sorted", "map.paf.sorted", "query.idx.sorted"]
    try:
        for f in to_remove:
            if os.path.exists(os.path.join(APP_DATA, id_res, f)):
                os.remove(os.path.join(APP_DATA, id_res, f))

        paf = os.path.join(APP_DATA, id_res, "map.paf")
        idx1 = os.path.join(APP_DATA, id_res, "query.idx")
        idx2 = os.path.join(APP_DATA, id_res, "target.idx")

        paf = Paf(paf, idx1, idx2)
        # Force refresh the sorted query file.
        Path(os.path.join(APP_DATA, id_res, ".new-reversals")).touch()

        if paf.parsed:
            return {"code": 0, "message": "ok"}, 200
        return {"code": 404, "message": paf.error}, 404
    except FileNotFoundError:
        return {"code": 404, "message": f"Job doesn't exists"}, 404


from pydantic import BaseModel

class ReverseContigInput(BaseModel):
    contig: str

@api.post('/result/<job_id>/reverse-contig',
          responses={
              200: BaseResponse,
              404: NotFoundResponse
          })
def post_reverse_contig(path: JobPath, body: ReverseContigInput):
    """
    Reverse contig order on query
    """
    id_res = path.job_id
    contig_name = body.contig
    try:
        if not os.path.exists(os.path.join(APP_DATA, id_res, ".all-vs-all")):
            paf_file = os.path.join(APP_DATA, id_res, "map.paf")
            idx1 = os.path.join(APP_DATA, id_res, "query.idx")
            idx2 = os.path.join(APP_DATA, id_res, "target.idx")
            paf = Paf(paf_file, idx1, idx2, False)
            Path(os.path.join(APP_DATA, id_res, ".new-reversals")).touch()
            paf.reverse_contig(contig_name)
            if paf.parsed:
                # TODO: to apply on sorted dotplot only
                return {"code": 0, "message": "ok"}
            return {"code": 404, "message": paf.error}, 404
        return {"code": 404, "message": "Sort is not available for All-vs-All mode"}, 404
    except FileNotFoundError:
        return {"code": 404, "message": f"Job doesn't exists"}, 404


@api.post('/result/<job_id>/free-noise', responses={501: NotImplementedResponse})
def post_free_noise(path: JobPath, body):
    """
    Remove noise from the dot plot
    """
    return notImplementedResponse.model_dump(), 501


# Associations between query and target

@api.get('/result/<job_id>/qt-assoc',
         responses={
            200: QTAssocResponse,
            404: NotFoundResponse
        })
def get_qt_assoc(path: JobPath):
    """
    Get the query on target associations
    """
    id_res = path.job_id
    res_dir = os.path.join(APP_DATA, id_res)
    if os.path.exists(res_dir) and os.path.isdir(res_dir):
        paf_file = os.path.join(APP_DATA, id_res, "map.paf")
        idx1 = os.path.join(APP_DATA, id_res, "query.idx")
        idx2 = os.path.join(APP_DATA, id_res, "target.idx")
        try:
            paf = Paf(paf_file, idx1, idx2, False)
            paf.parse_paf(False)
        except FileNotFoundError:
            return {"code": 404, "message": "Unable to load data!"}, 404
        records = [QTAssocRecord(
            query= row[0],
            target= row[1],
            strand= row[2],
            q_len= row[3],
            q_start= row[4],
            q_stop= row[5],
            t_len= row[6],
            t_start= row[7],
            t_stop= row[8]) for row in list(paf.build_query_on_target_association_records())]
        return {
            "code": 0,
            "message": "OK",
            "data": QTAssoc(
                records=records,
                count=len(records)
            ).model_dump()}
    return {"code": 404, "message": "Job doesn't exist"}, 404


@api.get('/download/<job_id>/qt-assoc',
          responses={
              200: {"content": {"text/tsv": {"schema": {"type": "string"}}}}     ,
              404: NotFoundResponse
          })
def get_dl_qt_assoc(path: JobPath):
    """
    Get the query on target associations
    """
    id_res = path.job_id
    res_dir = os.path.join(APP_DATA, id_res)
    if os.path.exists(res_dir) and os.path.isdir(res_dir):
        paf_file = os.path.join(APP_DATA, id_res, "map.paf")
        idx1 = os.path.join(APP_DATA, id_res, "query.idx")
        idx2 = os.path.join(APP_DATA, id_res, "target.idx")
        try:
            paf = Paf(paf_file, idx1, idx2, False)
            paf.parse_paf(False)
        except FileNotFoundError:
            return NotFoundResponse(code= 404, message="Unable to load data! Does job is done?").model_dump(), 404
        return paf.build_query_on_target_association_file(), 200
    return NotFoundResponse(code=404, message="Job doesn't exist").model_dump(), 404


@api.post('/result/<job_id>/no-assoc',
          responses={
              200: NoAssocResponse,
              404: NotFoundResponse
          })
def post_no_assoc(path: JobPath, body: NoAssocInput):
    """
    Get the list of contigs or chromosomes from query (resp. target) that don't match the target (resp. query)
    """
    id_res = path.job_id
    res_dir = os.path.join(APP_DATA, id_res)
    if os.path.exists(res_dir) and os.path.isdir(res_dir):
        paf_file = os.path.join(APP_DATA, id_res, "map.paf")
        idx1 = os.path.join(APP_DATA, id_res, "query.idx")
        idx2 = os.path.join(APP_DATA, id_res, "target.idx")
        try:
            paf = Paf(paf_file, idx1, idx2, False)
        except FileNotFoundError:
            return {"code": 404, "message": "Unable to load data!"}, 404
        contigs_list = paf.build_list_no_assoc(body.which)
        return {"code": 0, "message": "ok", "data": NoAssoc(which=body.which, count=len(contigs_list), contigs=contigs_list).model_dump()}, 200
    return {"code": 404, "message": "Job doesn't exist"}, 404


@api.post('/download/<job_id>/no-assoc',
          responses={
              200: {"content": {"text/tsv": {"schema": {"type": "string"}}}},
              404: NotFoundResponse
          })
def post_dl_no_assoc(path: JobPath, body: NoAssocInput):
    """
    Download as a text file the list of contigs or chromosomes from query (resp. target) that don't match the target (resp. query)
    """
    id_res = path.job_id
    res_dir = os.path.join(APP_DATA, id_res)
    if os.path.exists(res_dir) and os.path.isdir(res_dir):
        paf_file = os.path.join(APP_DATA, id_res, "map.paf")
        idx1 = os.path.join(APP_DATA, id_res, "query.idx")
        idx2 = os.path.join(APP_DATA, id_res, "target.idx")
        try:
            paf = Paf(paf_file, idx1, idx2, False)
        except FileNotFoundError:
            return NotFoundResponse(code= 404, message="Unable to load data!").model_dump(), 404
        content = "\n".join(paf.build_list_no_assoc(body.which)) + "\n"
        return content, 200
    return NotFoundResponse(code=404, message="Job doesn't exist").model_dump(), 404


@api.post('/result/<job_id>/prepare-fasta-query',
          responses={
              200: PrepareFastaResponse,
              404: NotFoundResponse
          })
def prepare_fasta_query(path: JobPath, body: PrepareFastaInput):
    """
    Prepare the query fasta file for download with /result/<job_id>/get-fasta-query route.
    Depend on the sorted state of the dotplot.
    """
    try:
        status, is_compressed = build_fasta(path.job_id, body.gzip)
        if status == 1:
            return {
                "code": 0, "message": "ok",
                "data": PrepareFasta(status=PrepareFastaEnum.in_progress, gzip=None, mail=MODE == "webserver").model_dump()
            }, 200
        elif status == 2:
            return {
                "code": 0, "message": "ok",
                "data": PrepareFasta(status=PrepareFastaEnum.done, gzip=is_compressed, mail=MODE == "webserver").model_dump()
            }, 200
    except DGeniesMissingJobError:
        return NotFoundResponse(code=1, message="Job doesn't exist").model_dump(), 404
    except FileNotFoundError:
        return NotFoundResponse(code=2, message="Query fasta file not available").model_dump(), 404
    except Exception as e:
        print(e)
        pass
    return {"code": 500, "message": "Internal error, please contact support"}, 500

@api.get('/result/<job_id>/get-fasta-query',
          responses={
              200: {"content": {
                  "text/plain": {"schema": {"type": "string"}},
                  "application/gzip": {"schema": {"type": "string", "format": "binary"}}
              }},
              404: NotFoundResponse
          })
def get_fasta_query(path: JobPath):
    """
    Get the fasta file of query
    """
    res_dir = os.path.join(APP_DATA, path.job_id)
    lock_query = os.path.join(res_dir, ".query-fasta-build")

    if os.path.exists(lock_query):
        return {"code": 404, "message": "Query fasta file is building, try latter"}, 404
    query_fasta = Functions.get_fasta_file(res_dir, "query", is_sorted=False)
    if query_fasta is None:
        return {"code": 404, "message": "Query fasta file not available"}, 404

    try:
        is_gzip = query_fasta.endswith(".gz")
        content = open(query_fasta, "rb" if is_gzip else "r").read()
    except FileNotFoundError:
        # Not fasta file was uploaded (plot)
        return {"code": 404, "message": "Query fasta file not available"}, 404
    except IOError as e:
        print(e.__traceback__)
        return {"code": 500, "message": "Internal server error, please contact support"}, 500

    response = make_response(content, HTTPStatus.OK)
    response.mimetype = "application/gzip" if is_gzip else "text/plain"
    return response


def build_query_as_reference(id_res):
    """
    Build fasta of query with contigs order like reference

    :param id_res: job id
    :type id_res: str
    """
    import threading
    paf_file = os.path.join(APP_DATA, id_res, "map.paf")
    idx1 = os.path.join(APP_DATA, id_res, "query.idx")
    idx2 = os.path.join(APP_DATA, id_res, "target.idx")
    paf = Paf(paf_file, idx1, idx2, False, mailer=mailer, id_job=id_res)
    paf.parse_paf(False, True)
    if MODE == "webserver":
        thread = threading.Timer(0, paf.build_query_chr_as_reference, kwargs={"compress": True})
        thread.start()
        return True
    return paf.build_query_chr_as_reference(compress=False)

@api.post('/build-query-as-reference/<job_id>',
          responses={
              200: BaseResponse,
              404: NotFoundResponse
          })
def post_build_query_as_reference(path: JobPath):
    """
    Launch build fasta of query with contigs order like reference
    """
    id_res = path.job_id
    res_dir = os.path.join(APP_DATA, id_res)
    if os.path.exists(res_dir) and os.path.isdir(res_dir):
        build_query_as_reference(id_res)
        return {"code": 0, "message": "ok"}
    return NotFoundResponse(code=404, message="Job doesn't exist").model_dump(), 404

@api.post('/get-query-as-reference/<job_id>', responses={501: NotImplementedResponse})
def get_build_query_as_reference(path: JobPath):
    """
    Get fasta of query with contigs order like reference
    """
    return notImplementedResponse.model_dump(), 501

# Download file contents

@api.get('/download/<job_id>/file/<filename>', responses={501: NotImplementedResponse})
def get_file(path: JobFilePath):
    """
    Download a file produced by the job
    """
    return notImplementedResponse.model_dump(), 501

@api.get('/download/<job_id>/paf', responses={501: NotImplementedResponse})
def get_paf(path: JobPath):
    """
    Download the alignment file in paf format
    """
    return notImplementedResponse.model_dump(), 501

@api.get('/download/<job_id>/backup', responses={501: NotImplementedResponse})
def get_backup(path: JobPath):
    """
    Download the backup file in tar.gz format
    """
    return notImplementedResponse.model_dump(), 501

@api.get('/download/<job_id>/logs', responses={501: NotImplementedResponse})
def get_logs(path: JobPath):
    """
    Download the log file
    """
    return notImplementedResponse.model_dump(), 501

@api.get('/download/<job_id>/query-as-reference', responses={501: NotImplementedResponse})
def get_query_as_reference(path: JobPath):
    """
    Download the query fasta file
    """
    return notImplementedResponse.model_dump(), 501

@api.get('/download/<job_id>/fasta-query', responses={501: NotImplementedResponse})
def get_dl_fasta_query(path: JobPath):
    """
    Download the query fasta file
    """
    return notImplementedResponse.model_dump(), 501

@api.get('/download/<job_id>/filter-out/query', responses={501: NotImplementedResponse})
def get_filter_out_target(path: JobPath):
    """
    Download query filtered fasta, when it has been filtered before job run
    """
    return notImplementedResponse.model_dump(), 501

@api.get('/download/<job_id>/filter-out/target', responses={501: NotImplementedResponse})
def get_filter_out_query(path: JobPath):
    """
    Download target filtered fasta, when it has been filtered before job run
    """
    return notImplementedResponse.model_dump(), 501

@api.get('/download/<job_id>/viewer', responses={501: NotImplementedResponse})
def get_viewer(path: JobPath):
    """
    Get HTML file with offline interactive viewer inside
    """
    return notImplementedResponse.model_dump(), 501

@api.delete('/job/<job_id>',
            responses={
                200: BaseResponse,
                403: BaseResponse
            })
def delete_job(path: JobPath):
    """
    Delete a job
    """
    print(path.job_id)
    job = JobManager(id_job=path.job_id)
    try:
        job.delete()
        return {
            "code": 0,
            "message": "ok"
        }
    except DGeniesMissingJobError:
        return {
            "code": 0,
            "message": "ok"
        }
    except DGeniesDeleteGalleryJobForbidden:
        return {
            "code": 403,
            "message": "Access denied"
        }, 403

@api.get('/example/jobs',responses={501: NotImplementedResponse})
def get_example_jobs():
    """
    Get example jobs
    """
    return notImplementedResponse.model_dump(), 501

@api.get('/example/files',responses={200: ExampleFilesResponse})
def get_example_files():
    """
    Get example files uri
    """
    example_files = []
    for f in ["backup", "query", "target"]:
        example_file = getattr(config_reader, f"example_{f}")
        if example_file:
            example_files.append(f"example://{os.path.basename(example_file)}")
    return {
        "code": 0,
        "message": "ok",
        "data": example_files
    }, 200

# Gallery
@api.get('/gallery',
         responses={
             200: GalleryResponse,
             404: NotFoundResponse
         })
def get_gallery():
    """
    Get gallery items
    """
    if MODE == "webserver":
        items = Functions.get_gallery_items()
        # fix key
        for e in items:
            e['job_id'] = e.pop('id_job')
        return {
            "code": 0,
            "message": "ok",
            "data": items
        }
    return NotFoundResponse(code=404, message="Not available in this instance").model_dump(), 404
