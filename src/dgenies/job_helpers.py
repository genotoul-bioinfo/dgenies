from __future__ import annotations

import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path

import dgenies
from werkzeug.utils import secure_filename

from dgenies.lib.datafile import DataFile
from dgenies.lib.exceptions import (
    DGeniesExampleInvalid,
    DGeniesExampleNotAvailable,
    DGeniesMissingJobError,
)
from dgenies.lib.functions import Functions
from dgenies.lib.paf import Paf

logger = logging.getLogger(__name__)


def create_datafile(f: str, f_type: str, upload_folder: str, example_paths: list) -> DataFile:
    """
    Create DataFile object. Raise an DGeniesExampleNotAvailable if example file does not exist

   :param f: filename or url
   :type f: str
   :param f_type: file type
   :type f_type: str
   :param upload_folder: upload folder
   :type upload_folder: str
   :param example_paths: list of example file path
   :type example_paths: str
   :return: Fasta object
   :rtype: DataFile
    """
    example = False
    f_name = None
    if f.startswith("example://"):
        if example_paths:
            # File path is local example file
            f_name = re.sub(r"^example://", "", f)
            try:
                example_index = [os.path.basename(f_example) for f_example in example_paths].index(f_name)
                f_path = example_paths[example_index]
            except ValueError:
                raise DGeniesExampleInvalid(f_name)
            f_type = "local"
            example = True
        else:
            raise DGeniesExampleNotAvailable
    else:
        if f_type == "local":
            f_name = os.path.splitext(re.sub(r"\.gz$", "", f))[0]
            f_path = os.path.join(dgenies.app.config["UPLOAD_FOLDER"], upload_folder, f)
            # Sanitize filename
            if os.path.exists(f_path):
                if " " in f:
                    new_f_path = os.path.join(
                        dgenies.app.config["UPLOAD_FOLDER"],
                        upload_folder,
                        secure_filename(f.replace(" ", "_")),
                    )
                    shutil.move(f_path, new_f_path)
                    f_path = new_f_path
            else:
                raise FileNotFoundError
        else:
            # File path is file url
            f_path = f
    return DataFile(name=f_name, path=f_path, type_f=f_type, example=example)


def update_files(jobs: list, upload_folder: str):
    """
    Update job list by replacing file url and file path by datafile object.
    Same path is replaced by same datafile object avoiding duplication.

    jobs:
    """
    # entries with a potential file
    file_roles = ["query", "target", "align", "backup"]
    # entries with a potential example
    roles_with_example = {
        k: getattr(dgenies.config_reader, f"example_{k}")
        for k in ["query", "target", "backup"]
    }
    datafiles = dict()  # cache for deduplication
    for j in jobs:
        for role in file_roles:
            if role in j and j[role]:
                path = j[role]
                if path in datafiles:
                    f = datafiles[path]
                else:
                    file_type = j[f"{role}_type"]
                    example_files = []
                    if role in roles_with_example:
                        example_files.append(roles_with_example[role])
                    if role == "query":
                        if "target" in roles_with_example:
                            example_files.append(roles_with_example["target"])
                    elif role == "target":
                        if "query" in roles_with_example:
                            example_files.append(roles_with_example["query"])
                    f = create_datafile(path, file_type, upload_folder, example_files)
                    datafiles[path] = f
                j[role] = f
                del j[f"{role}_type"]


def build_fasta(id_res: str, to_compress: bool) -> tuple[int, bool]:
    """
    Generate the fasta file of query

    :param id_res: job id
    :type id_res: str
    :param to_compress: ask to compress file
    :type to_compress: bool
    :return: tuple [status, gzipped]:
        * status: 1 - In progress, 2 - Done
        * is_compressed: True if file is compressed, False else or when not applicable (other state than 2- Done)
    :rtype: tuple[int, bool]
    """
    res_dir = os.path.join(dgenies.APP_DATA, id_res)
    if not os.path.exists(res_dir) and not os.path.isdir(res_dir):
        raise DGeniesMissingJobError(id_res)
    # Get base query file without querying job database
    # TODO: check database if not found and raise error depending job type.
    #       We expect query only for query vs target align job
    base_query_fasta = Functions.get_fasta_file(res_dir, "query", is_sorted=False)
    if base_query_fasta is None:
        base_query_fasta = Functions.get_fasta_file(res_dir, "query", is_sorted=True)
    if base_query_fasta is None:
        raise FileNotFoundError(id_res)
    lock_query = os.path.join(res_dir, ".query-fasta-build")
    is_sorted = os.path.exists(os.path.join(res_dir, ".sorted"))
    need_refresh = is_sorted and not has_fresh_sorted_query_fasta(res_dir)
    wanted_query_fasta = Functions.get_fasta_file(res_dir, "query", is_sorted and not need_refresh)
    if wanted_query_fasta is None:
        raise BaseException()
    if need_refresh:
        # Do the sort
        if Functions.is_file_lock_active(lock_query) or not Functions.acquire_file_lock(lock_query):
            return 1, False
        refresh_marker = os.path.join(res_dir, ".new-reversals")
        if os.path.exists(refresh_marker):
            os.remove(refresh_marker)
        if not to_compress or dgenies.MODE == "standalone":  # If compressed, it will took a long time, so not wait
            Path(lock_query + ".pending").touch()
        index_file = os.path.join(res_dir, "query.idx.sorted")
        logger.debug("Sort file{}: {}".format(" and compress" if to_compress else "", wanted_query_fasta))
        if dgenies.MODE == "webserver":
            thread = threading.Timer(1, Functions.sort_fasta, kwargs={
                "job_name": id_res,
                "fasta_file": wanted_query_fasta,
                "index_file": index_file,
                "lock_file": lock_query,
                "compress": to_compress,
                "with_date": True,
                "dot_file": os.path.join(res_dir, ".query.sorted"),
                "mailer": dgenies.mailer,
                "mode": dgenies.MODE,
                "overwrite": True
            })
            thread.start()
        else:
            try:
                Functions.sort_fasta(
                    job_name=id_res,
                    fasta_file=wanted_query_fasta,
                    index_file=index_file,
                    lock_file=lock_query,
                    compress=to_compress,
                    with_date=False,
                    dot_file=None,
                    mailer=None,
                    mode=dgenies.MODE,
                    overwrite=True
                )
            except Exception:
                Functions.release_file_lock(lock_query)
                raise
        if not to_compress or dgenies.MODE == "standalone":
            if dgenies.MODE == "webserver":
                i = 0
                time.sleep(5)
                while os.path.exists(lock_query) and (i < 2 or dgenies.MODE == "standalone"):
                    i += 1
                    time.sleep(5)
            os.remove(lock_query + ".pending")
            if os.path.exists(lock_query):
                return 1, False
            return 2, to_compress
        else:
            return 1, False
    elif is_sorted and Functions.is_file_lock_active(lock_query):
        # Sort is already in progress
        return 1, False
    else:
        # No sort to do or sort done
        is_compressed = wanted_query_fasta.endswith(".gz") or wanted_query_fasta.endswith(".gz.sorted")
        if to_compress and not is_compressed:
            logger.debug("Compress file: {}".format(wanted_query_fasta))
            # If compressed file is asked, we must compress it now if not done before...
            if Functions.is_file_lock_active(lock_query) or not Functions.acquire_file_lock(lock_query):
                return 1, False
            thread = threading.Timer(1, Functions.compress_and_send_mail, kwargs={
                "job_name": id_res,
                "fasta_file": wanted_query_fasta,
                "lock_file": lock_query,
                "mailer": dgenies.mailer,
                "dot_file": os.path.join(res_dir, ".query.sorted"),
                "overwrite": True
            })
            thread.start()
            return 1, False
        return 2, is_compressed


def compute_summary(id_res: str) -> tuple[dict[int, float] | None, str]:
    """
    Compute Dot plot summary data

    :param id_res: job id
    :type id_res: str
    """
    percents = None
    job_dir = os.path.join(dgenies.APP_DATA, id_res)
    if not os.path.exists(job_dir) or not os.path.isdir(job_dir):
        logger.debug(f"Job not found: {job_dir}")
        return percents, "job_not_found"
    paf_file = os.path.join(job_dir, "map.paf")
    idx1 = os.path.join(job_dir, "query.idx")
    idx2 = os.path.join(job_dir, "target.idx")
    s_status = "waiting"  # Accepted values: 'waiting', 'done', 'fail'
    try:
        paf = Paf(paf_file, idx1, idx2, False)
    except FileNotFoundError:
        logger.debug(f"File not found: {paf_file}, {idx1}, {idx2}")
        return percents, "file_not_found"
    status_file = os.path.join(job_dir, ".summarize")
    fail_file = status_file + ".fail"
    if not os.path.exists(status_file):  # The job is finished or not started
        if not os.path.exists(fail_file):  # The job has not started yet or has successfully ended
            percents = paf.get_summary_stats()
            if percents is None:  # The job has not started yet
                Path(status_file).touch()
                thread = threading.Timer(0, paf.build_summary_stats, kwargs={"status_file": status_file})
                thread.start()
            else:  # The job has successfully ended
                s_status = "done"
        else:  # The job has failed
            s_status = "fail"

    if s_status == "waiting":  # The job is running
        # Check if the job end in the next 30 seconds
        nb_iter = 0
        while os.path.exists(status_file) and not os.path.exists(fail_file) and nb_iter < 10:
            time.sleep(3)
            nb_iter += 1
        if not os.path.exists(status_file):  # The job has ended
            percents = paf.get_summary_stats()
            if percents is None:  # The job has failed
                s_status = "fail"
            else:  # The job has successfully ended
                s_status = "done"
    return percents, s_status


def has_fresh_sorted_query_fasta(res_dir: str) -> bool:
    """
    Tell whether a sorted query fasta matching the current dotplot state exists.
    """
    if not os.path.exists(os.path.join(res_dir, ".sorted")):
        return False

    base_query_fasta = Functions.get_fasta_file(res_dir, "query", is_sorted=False)
    sorted_query_fasta = Functions.get_fasta_file(res_dir, "query", is_sorted=True)
    if base_query_fasta is None or sorted_query_fasta is None:
        return False

    try:
        if os.path.realpath(base_query_fasta) == os.path.realpath(sorted_query_fasta):
            return False
    except FileNotFoundError:
        return False

    refresh_marker = os.path.join(res_dir, ".new-reversals")
    if os.path.exists(refresh_marker):
        try:
            sorted_mtime = os.path.getmtime(sorted_query_fasta)
            refresh_mtime = os.path.getmtime(refresh_marker)
        except FileNotFoundError:
            return False
        return sorted_mtime >= refresh_mtime
    return True
