import math

from dgenies import MODE, DEBUG

import os
import shutil
import subprocess
from datetime import datetime
import time
import threading
import re
from dgenies.config_reader import AppConfigReader
from dgenies.tools import Tools
import dgenies.lib.validators as validators
import dgenies.lib.parsers as parsers
from .datafile import DataFile
from .functions import Functions
import requests
from requests.exceptions import ConnectionError
from urllib.request import urlretrieve
from urllib.error import URLError
from jinja2 import Template
import traceback
from pathlib import Path
from urllib import request, parse
from urllib.error import URLError
import tarfile
from dgenies.bin.split_fa import Splitter
from dgenies.bin.index import index_file, Index
from dgenies.bin.filter_contigs import Filter
from dgenies.bin.merge_splitted_chrms import Merger
from dgenies.bin.sort_paf import Sorter
from dgenies.lib.paf import Paf
from dgenies.lib.exceptions import DGeniesFileCheckError, DGeniesNotGzipFileError, DGeniesUploadedFileSizeLimitError, \
    DGeniesAlignmentFileUnsupported, DGeniesAlignmentFileInvalid, DGeniesIndexFileInvalid, DGeniesFastaFileInvalid, \
    DGeniesURLError, DGeniesURLInvalid, DGeniesDistantFileTypeUnsupported, DGeniesDownloadError, \
    DGeniesBackupUnpackError, DGeniesRunError, DGeniesClusterRunError, DGeniesLocalRunError, DGeniesMissingParserError,\
    DGeniesMissingJobError, DgeniesMissingSubjobsError, DGeniesDeleteGalleryJobForbidden
import gzip
import io
import json
from hashlib import sha1
from dgenies.database import Job, ID_JOB_LENGTH
from dgenies.allowed_extensions import AllowedExtensions
from typing import Self

import logging

if MODE == "webserver":
    from dgenies.database import Session, Gallery
    from peewee import DoesNotExist


from . import job_manager_execution as _job_manager_execution
from . import job_manager_files as _job_manager_files
from . import job_manager_notifications as _job_manager_notifications
from .datafile_context import DataFileContext, DataFileContextManager

JobManagerExecutionMixin = _job_manager_execution.JobManagerExecutionMixin
JobManagerFilesMixin = _job_manager_files.JobManagerFilesMixin
JobManagerNotificationsMixin = _job_manager_notifications.JobManagerNotificationsMixin


class JobManager(JobManagerExecutionMixin, JobManagerFilesMixin, JobManagerNotificationsMixin):
    """
    Jobs management
    """

    def __init__(self, id_job, email=None, query: DataFile = None, target: DataFile = None, mailer=None,
                 tool="minimap2", align: DataFile = None, backup: DataFile = None, batch: list[Self] = None, options=None):
        """
        This object will be used in two states:
         - A full state for creating, launching jobs, send emails
         - A partial state for managing job status. Only id_job will is needed in this case
        Partial state can be upgraded to full state by using 'set_inputs_from_res_dir' method (for email, mailer must be
        sent with the constructor)

        :param id_job: job id
        :type id_job: str
        :param email: email from user
        :type email: str
        :param query: query fasta
        :type query: DataFile
        :param target: target fasta
        :type target: DataFile
        :param mailer: mailer object (to send mail throw flask app)
        :type mailer: Mailer
        :param tool: tool to use for mapping (choice from tools config)
        :type tool: str
        :param align: alignment file (PAF, MAF, ...) as a fasta object
        :type align: DataFile
        :param backup: backup TAR file
        :type backup: DataFile
        :param batch: list of subjobs
        :type batch: list[JobManager]
        :param options: list of str containing options for the chosen tool
        :type options: list
        """
        self.logger = logging.getLogger(__name__)
        self.id_job = id_job
        self.email = email
        self.query = query
        self.target = target
        self.align = align
        if align is not None:
            self.aln_format = self.get_align_format(align.get_path())
        self.backup = backup
        self.batch = batch
        self.error = ""
        self.id_process = "-1"
        # Get configs:
        self.config = AppConfigReader()
        self.allowed_ext = AllowedExtensions()
        self.tools = Tools().tools
        self.tool = self.tools[tool] if tool is not None else None
        self.tool_name = tool
        self.options = options if tool is not None or options is not None else None
        # Outputs:
        self.output_dir = os.path.join(self.config.app_data, id_job)
        if self.batch is not None:
            # We keep track of subjob ids
            with open(os.path.join(self.output_dir, ".batch"), "w") as outfile:
                outfile.write("\n".join([j.id_job for j in self.batch]))
        self.preptime_file = os.path.join(self.output_dir, "prep_times")
        self.query_index_split = os.path.join(self.output_dir, "query_split.idx")
        self.paf = os.path.join(self.output_dir, "map.paf")
        self.paf_raw = os.path.join(self.output_dir, "map_raw.paf")
        self.idx_q = os.path.join(self.output_dir, "query.idx")
        self.idx_t = os.path.join(self.output_dir, "target.idx")
        self.logs = os.path.join(self.output_dir, "logs.txt")
        self.mailer = mailer
        self._filename_for_url = {}  # Cache for distant filenames

    @staticmethod
    def create(id_job: str, job_type: str, jobs: list, email: str = None, mailer=None):
        logger = logging.getLogger(__name__)
        logger.debug("Create job: {}".format(id_job))
        if job_type == "align":
            query = jobs[0].get("query", None)
            target = jobs[0].get("target", None)
            tool = jobs[0].get("tool", None)
            options = jobs[0].get("options", None)
            return JobManager(id_job=id_job, email=email, query=query, target=target,
                              mailer=mailer, tool=tool, options=options)
        elif job_type == "plot":
            query = jobs[0].get("query", None)
            target = jobs[0].get("target", None)
            align = jobs[0].get("align", None)
            backup = jobs[0].get("backup", None)
            return JobManager(id_job=id_job, email=email, query=query, target=target,
                              align=align, backup=backup, mailer=mailer)
        else:  # batch
            # We create subjobs
            batch = []
            for j in jobs:
                j = JobManager.create_subjob(id_job, j, email=email, mailer=mailer)
                batch.append(j)
                logger.debug("{} - Subjob created: {}".format(id_job, j.id_job))
            return JobManager(id_job=id_job, email=email, batch=batch, mailer=mailer)

    @staticmethod
    def create_subjob(id_job, params_dict, email=None, mailer=None):
        """"
        Create a list of JobManager objects

        :param id_job: parent job id
        :type id_job:
        :param params_dict: List of dict describing the job. Files in it must be DataFile objects
        :type params_dict: list of couples
        :return: list of jobs
        :rtype: list of JobManager
        """
        # We create a subjob id and the corresponding working directory
        logger = logging.getLogger(__name__)
        config = AppConfigReader()
        random_length = 5
        id_job_prefix = params_dict.get("id_job", id_job)
        id_job_prefix = id_job_prefix[0: min(len(id_job_prefix), ID_JOB_LENGTH - random_length - 1)]
        subjob_id = id_job_prefix + "_" + Functions.random_string(random_length)
        while os.path.exists(os.path.join(config.app_data, subjob_id)):
            subjob_id = id_job_prefix + "_" + Functions.random_string(random_length)
        job_type = params_dict.pop("type")
        folder_files = os.path.join(config.app_data, subjob_id)
        os.makedirs(folder_files)
        # We create the subjob itself
        subjob = JobManager.create(subjob_id, job_type, [params_dict],  email=email, mailer=mailer)
        logger.debug(subjob)
        return subjob

    def set_role(self, role: str, datafile: DataFile):
        """"
        Set role for a datafile

        :param role: the role (e.g. query, target, ...)
        :type role: str
        :param datafile: the datafile
        :type datafile: DataFile
        """
        if role == 'align':
            self.align = datafile
            self.aln_format = self.get_align_format(datafile.get_path()) if datafile is not None else None
        else:
            setattr(self, role, datafile)

    def unset_role(self, role: str):
        """"
        Unset a role

        :param role: the role (e.g. query, target, ...)
        :type role: str
        """
        self.set_role(role, None)

    def __repr__(self):
        to_display = ('id_job', 'query', 'target', 'align', 'backup', 'tool_name', 'options')
        attributes = [(attr, getattr(self, attr)) for attr in to_display if getattr(self, attr) is not None]
        return "JobManager({})".format(", ".join(["{}:{}".format(k, v) for k, v in attributes]))

    def do_align(self):
        """
        Check if we have to make alignment

        :return: True if the job is launched with an alignment file
        """
        return not os.path.exists(os.path.join(self.output_dir, ".align"))

    @staticmethod
    def get_align_format(filepath):
        return os.path.splitext(filepath)[1][1:]


    def get_file_size(self, filepath: str):
        """
        Get file size

        :param filepath: file path
        :type filepath: str
        :return: file size (bytes)
        :rtype: int
        """
        file_size = os.path.getsize(filepath)
        if filepath.endswith(".gz") and file_size <= self.config.max_upload_size:
            with gzip.open(filepath, 'rb') as file_obj:
                file_size = file_obj.seek(0, io.SEEK_END)
        return file_size

    def get_query_split(self):
        """
        Get query split fasta file

        :return: split query fasta file
        :rtype: str
        """
        if not self.tool.split_before:
            return self.query.get_path()
        query_split = os.path.join(self.output_dir, "split_" + os.path.basename(self.query.get_path()))
        if query_split.endswith(".gz"):
            return query_split[:-3]
        return query_split

    def set_inputs_from_res_dir(self):
        """
        Sets inputs (query, target, ...) from job dir
        """
        res_dir = os.path.join(self.config.app_data, self.id_job)
        query_file = os.path.join(res_dir, ".query")
        if os.path.exists(query_file):
            with open(query_file) as q_f:
                file_path = q_f.readline()
                self.logger.debug("{} - Set query file to {}".format(self.id_job, file_path))
                self.query = DataFile(
                    name="target" if file_path.endswith(".idx") else
                         os.path.splitext(os.path.basename(file_path.replace(".gz", "")).split("_", 1)[1])[0],
                    path=file_path,
                    type_f="local"
                )
        target_file = os.path.join(res_dir, ".target")
        if os.path.exists(target_file):
            with open(target_file) as t_f:
                file_path = t_f.readline()
                self.logger.debug("{} - Set target file to {}".format(self.id_job, file_path))
                self.target = DataFile(
                    name="query" if file_path.endswith(".idx") else
                         os.path.splitext(os.path.basename(file_path.replace(".gz", "")).split("_", 1)[1])[0],
                    path=file_path,
                    type_f="local"
                )
        align_file = os.path.join(res_dir, ".align")
        if os.path.exists(align_file):
            with open(align_file) as a_f:
                file_path = a_f.readline()
                self.logger.debug("{} - Set align file to {}".format(self.id_job, file_path))
                self.align = DataFile(
                    name="map",
                    path=file_path,
                    type_f="local"
                )
                self.aln_format = os.path.splitext(file_path)[1][1:]
        batch_file = os.path.join(res_dir, ".jobs")
        if os.path.exists(batch_file):
            # WARNING: Files in jobs are not Datafiles here.
            self.batch = self.read_jobs()

    def check_job_success(self):
        """
        Check if a job succeed

        :return: status of a job: succeed, no-match or fail
        :rtype: str
        """
        if os.path.exists(self.paf_raw):
            if os.path.getsize(self.paf_raw) > 0:
                return "succeed"
            else:
                return "no-match"
        return "fail"

    def is_query_filtered(self):
        """
        Check if query has been filtered

        :return: True if filtered, else False
        :rtype: bool
        """
        return os.path.exists(os.path.join(self.output_dir, ".filter-query"))

    def is_target_filtered(self):
        """
        Check if target has been filtered

        :return: True if filtered, else False
        :rtype: bool
        """
        return os.path.exists(os.path.join(self.output_dir, ".filter-target"))

    def _get_query_target_names(self):
        """
        Get the query and target names

        :return:
            * [0] The query name if exists, else None
            * [1] The target name if exists, else None
        :rtype: tuples
        """
        target_name = None
        if os.path.exists(self.idx_t):
            with open(self.idx_t, "r") as idxt:
                target_name = idxt.readline().rstrip()
        query_name = None
        if os.path.exists(self.idx_q):
            with open(self.idx_q, "r") as idxq:
                query_name = idxq.readline().rstrip()
                if query_name == target_name:
                    query_name = None
        return query_name, target_name


    def is_batch(self):
        """
        Check if job is a batch job
        :return: True if job is a batch job
        :rtype: bool
        """
        return self.batch is not None or os.path.exists(os.path.join(self.output_dir, ".batch"))

    def is_plot(self):
        """
        Check if job is a plot job
        :return: True if job is a plot job
        :rtype: bool
        """
        return self.align is not None \
               or os.path.exists(self.paf) \
               or self.backup is None

    def is_align(self):
        """
        Check if job is an align job
        :return: True if job is a plot job
        :rtype: bool
        """
        return not self.is_plot() is None and not self.is_batch()

    def is_ava(self):
        """
        Check if job is an ava align
        :return: True if job is an ava align job
        :rtype: bool
        """
        return self.target is not None and self.query is None

    def get_file_size_for_role(self, role):
        return self.config.max_upload_size_ava if self.is_ava() and role == 'target' else self.config.max_upload_size

    def get_job_type(self):
        """
        Return job type based on the files used for the job.
        :return: job type which is either "new" (for new align job), "plot" and "batch"
        :rtype: str
        """
        return "batch" if self.is_batch() \
            else "new" if (self.align is None and self.backup is None) else "plot"


    def as_job_entry(self):
        """
        Get a representation of current job as a job entry in batch file

        :return:
        :rtype: dict
        """
        jobtype = self.get_job_type()
        params_dict = {'type': jobtype, 'id_job': self.id_job}
        params_dict.update({a: getattr(self, a).get_path() for a in self.allowed_ext.get_roles(jobtype) if getattr(self, a) is not None})
        if self.tool_name is not None:
            params_dict["tool"] = self.tool_name
        if self.options is not None:
            params_dict["options"] = self.options
        return params_dict

    @staticmethod
    def to_job_list(jobs):
        """
        Get a representation of current job a list of jobs similar to what we obtain when reading batch file
        """
        return [(j.pop('type'), j) for j in jobs]

    def get_datafiles(self):
        """
        Return a list that maps the kind of file (query, target, etc) to the datafile
        """
        return [(file_type, getattr(self, file_type)) for file_type in self.allowed_ext.get_roles(self.get_job_type()) if
                getattr(self, file_type) is not None]

    def from_file_to_datafiles(self, job_type, params, cache=dict()):
        """
        Replace filepaths within a list of parameters into datafile objects

        :param job_type: type of job (align, plot, batch)
        :type job_type: str
        :param params: parameters of the job
        :type params: dict
        :param cache: datafile cache in order get deduplicate datafile objects
        :type cache: dict
        :return: copy of parameters where file paths where replaced by datafile object
        :rtype: dict
        """
        job_input_files = self.allowed_ext.get_roles("new" if job_type == "align" else job_type)
        res = dict()
        for p, v in params.items():
            if p in job_input_files:
                if v not in cache:
                    df = DataFile.create(name=os.path.basename(v), path=v)
                    cache[v] = df
                v = cache[v]
            res[p] = v
        return job_type, res


    def set_status_standalone(self, status, error=""):
        """
        Change job status in standalone mode

        :param status: new status
        :type status: str
        :param error: error description (if any)
        :type error: str
        """
        status_file = os.path.join(self.output_dir, ".status")
        with open(status_file, "w") as s_file:
            s_file.write("|".join([status, error]))

    def get_status_standalone(self, with_error=False):
        """
        Get job status in standalone mode

        :param with_error: get also the error
        :return: status (and error, if with_error=True)
        :rtype: str or tuple (if with_error=True)
        """
        status_file = os.path.join(self.output_dir, ".status")
        with open(status_file, "r") as s_file:
            items = s_file.read().strip("\n").split("|")
            if with_error:
                return items
            return items[0]

    def status(self):
        """
        Get job status and error. In webserver mode, get also mem peak and time elapsed

        :return: status and other information
        :rtype: dict
        """
        if MODE == "webserver":
            try:
                with Job.connect():
                    job = Job.get(Job.id_job == self.id_job)
                    return {"status": job.status, "mem_peak": job.mem_peak, "time_elapsed": job.time_elapsed,
                            "error": job.error}
            except DoesNotExist:
                return {"status": "unknown", "error": ""}
        else:
            try:
                status, error = self.get_status_standalone(with_error=True)
                return {"status": status, "mem_peak": None, "time_elapsed": None, "error": error}
            except FileNotFoundError:
                return {"status": "unknown", "error": ""}

    def delete(self):
        """
        Remove a job
        Raise a MissingJobError if job is missing, DGeniesDeleteGalleryJobForbidden if job is in gallery
        """
        if not os.path.exists(self.output_dir) or not os.path.isdir(self.output_dir):
            raise DGeniesMissingJobError
        if MODE == "webserver":
            # Forbid to delete job existing in gallery
            try:
                job = Job.get(id_job=self.id_job)
            except DoesNotExist:
                pass
            else:
                is_gallery = Gallery.select().where(Gallery.job == job)
                if is_gallery:
                    raise DGeniesDeleteGalleryJobForbidden()
                job.delete_instance()
        shutil.rmtree(self.output_dir)



_COMPAT_MODULES = (
    _job_manager_execution,
    _job_manager_files,
    _job_manager_notifications,
)
_COMPAT_NAMES = {
    'MODE', 'DEBUG', 'AppConfigReader', 'Tools', 'AllowedExtensions', 'Job', 'ID_JOB_LENGTH',
    'Session', 'Gallery', 'DoesNotExist', 'validators', 'parsers', 'requests', 'ConnectionError',
    'urlretrieve', 'URLError', 'Template', 'Functions', 'DataFile', 'Splitter', 'index_file',
    'Index', 'Filter', 'Merger', 'Sorter', 'Paf', 'DGeniesFileCheckError',
    'DGeniesNotGzipFileError', 'DGeniesUploadedFileSizeLimitError',
    'DGeniesAlignmentFileUnsupported', 'DGeniesAlignmentFileInvalid',
    'DGeniesIndexFileInvalid', 'DGeniesFastaFileInvalid', 'DGeniesURLError',
    'DGeniesURLInvalid', 'DGeniesDistantFileTypeUnsupported', 'DGeniesDownloadError',
    'DGeniesBackupUnpackError', 'DGeniesRunError', 'DGeniesClusterRunError',
    'DGeniesLocalRunError', 'DGeniesMissingParserError', 'DGeniesMissingJobError',
    'DgeniesMissingSubjobsError', 'DGeniesDeleteGalleryJobForbidden',
}

def _sync_compat_name(name, value):
    if name in _COMPAT_NAMES:
        for module in _COMPAT_MODULES:
            setattr(module, name, value)

def _delete_compat_name(name):
    if name in _COMPAT_NAMES:
        for module in _COMPAT_MODULES:
            if hasattr(module, name):
                delattr(module, name)

import sys as _sys
from types import ModuleType as _ModuleType

class _JobManagerModule(_ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        _sync_compat_name(name, value)

    def __delattr__(self, name):
        super().__delattr__(name)
        _delete_compat_name(name)

_sys.modules[__name__].__class__ = _JobManagerModule
