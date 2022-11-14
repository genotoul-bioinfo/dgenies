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
import tarfile
from dgenies.bin.split_fa import Splitter
from dgenies.bin.index import index_file, Index
from dgenies.bin.filter_contigs import Filter
from dgenies.bin.merge_splitted_chrms import Merger
from dgenies.bin.sort_paf import Sorter
from dgenies.lib.paf import Paf
from dgenies.lib.batch import read_batch_file
from dgenies.lib.exceptions import DGeniesFileCheckError, DGeniesNotGzipFileError, DGeniesUploadedFileSizeLimitError, \
    DGeniesAlignmentFileUnsupported, DGeniesAlignmentFileInvalid, DGeniesIndexFileInvalid, \
    DGeniesURLError, DGeniesURLInvalid, DGeniesDistantFileTypeUnsupported, DGeniesDownloadError, \
    DGeniesBackupUnpackError, DGeniesBatchFileError
import gzip
import io
import binascii
import json
from hashlib import sha1
from dgenies.database import Job, ID_JOB_LENGTH
from dgenies.allowed_extensions import AllowedExtensions

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

if MODE == "webserver":
    from dgenies.database import Session, Gallery
    from peewee import DoesNotExist


class JobManager:
    """
    Jobs management
    """

    def __init__(self, id_job, email=None, query: DataFile = None, target: DataFile = None, mailer=None,
                 tool="minimap2", align: DataFile = None, backup: DataFile = None, batch=None, options=None):
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
        :param batch: batch file
        :type batch: DataFile
        :param options: list of str containing options for the chosen tool
        :type options: list
        """
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
            return JobManager(id_job=id_job, email=email, batch=jobs, mailer=mailer)

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
        return [(attr, getattr(self, attr)) for attr in to_display if getattr(self, attr) is not None]

    def __str__(self):
        return "JobManager({})".format(", ".join(["{}:{}".format(k, v) for k, v in self.__repr__()]))

    def do_align(self):
        """
        Check if we have to make alignment

        :return: True if the job is launched with an alignment file
        """
        return not os.path.exists(os.path.join(self.output_dir, ".align"))

    @staticmethod
    def get_align_format(filepath):
        return os.path.splitext(filepath)[1][1:]

    @staticmethod
    def is_gz_file(filepath):
        """
        Check if a file is gzipped

        :param filepath: file to check
        :type filepath: str
        :return: True if gzipped, else False
        """
        with open(filepath, 'rb') as test_f:
            return binascii.hexlify(test_f.read(2)) == b'1f8b'

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
                self.align = DataFile(
                    name="map",
                    path=file_path,
                    type_f="local"
                )
                self.aln_format = os.path.splitext(file_path)[1][1:]
        batch_file = os.path.join(res_dir, ".batch")
        if os.path.exists(batch_file):
            with open(batch_file) as b_f:
                file_path = b_f.readline()
                self.batch = DataFile(
                    name="batch",
                    path=file_path,
                    type_f="local"
                )

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

    def get_job_mail_part(self, status, target_name, query_name=None):
        """
        Build mail content part for status mail for standard job

        :param status: job status
        :type status: str
        :param target_name: name of target
        :type target_name: str
        :param query_name:  name of query
        :type query_name: str
        :return: mail content part
        :rtype: str
        """
        if status == "success":
            message = "Your job %s was completed successfully!\n\n" % self.id_job
            message += str("Your job {0} is finished. You can see the results by clicking on the link below:\n"
                           "{1}/result/{0}\n\n").format(self.id_job, self.config.web_url)
        else:
            message = "Your job %s has failed!\n\n" % self.id_job
            if self.error != "":
                message += self.error.replace("#ID#", self.id_job).replace("<br/>", "\n")
                message += "\n\n"
            else:
                message += "Your job %s has failed. You can try again. " \
                           "If the problem persists, please contact the support.\n\n" % self.id_job
        if target_name is not None:
            message += "Sequences compared in this analysis:\n"
            if query_name is not None:
                message += "Target: %s\nQuery: %s\n\n" % (target_name, query_name)
            else:
                message += "Target: %s\n\n" % target_name
        if status == "success":
            if self.is_target_filtered():
                message += str("Note: target fasta has been filtered because it contains too small contigs."
                               "To see which contigs has been removed from the analysis, click on the link below:\n"
                               "{1}/filter-out/{0}/target\n\n").format(self.id_job, self.config.web_url)
            if self.is_query_filtered():
                message += str("Note: query fasta has been filtered because it contains too small contigs."
                               "To see which contigs has been removed from the analysis, click on the link below:\n"
                               "{1}/filter-out/{0}/query\n\n").format(self.id_job, self.config.web_url)
        return message

    def get_batch_mail_part(self, status):
        """
        Build mail content part for status mail for batch job

        :param status: job status
        :type status: str
        :return: mail content part
        :rtype: str
        """
        if status == "success":
            message = "Your batch job %s was completed successfully!\n\n" % self.id_job
        else:
            message = "Your batch job %s has failed!\n\n" % self.id_job
            if self.error != "":
                message += self.error.replace("#ID#", self.id_job).replace("<br/>", "\n")
                message += "\n\n"
            else:
                message += "Your job %s has failed. You can try again. " \
                           "If the problem persists, please contact the support.\n\n" % self.id_job
        message += "Here the detail of each job:\n\n"
        subjobs = (JobManager(i) for i in self.get_subjob_ids())
        for sj in subjobs:
            message += sj.id_job + "\n" + "-" * len(sj.id_job) + "\n\n"
            query_name, target_name = sj._get_query_target_names()
            message += sj.get_job_mail_part(sj.status().get("status", "unknown"), target_name, query_name)
        return message

    def get_mail_content(self, status, target_name, query_name=None):
        """
        Build mail content for status mail

        :param status: job status
        :type status: str
        :param target_name: name of target
        :type target_name: str
        :param query_name:  name of query
        :type query_name: str
        :return: mail content
        :rtype: str
        """
        message = "D-Genies\n\n"
        if self.is_batch():
            message += self.get_batch_mail_part(status)
        else:
            message += self.get_job_mail_part(status, target_name, query_name)
        message += "See you soon on D-Genies,\n"
        message += "The team"
        return message

    def get_mail_content_html(self, status, target_name, query_name=None):
        """
        Build mail content as HTML

        :param status: job status
        :type status: str
        :param target_name: name of target
        :type target_name: str
        :param query_name:  name of query
        :type query_name: str
        :return: mail content (html)
        :rtype: str
        """
        if self.is_batch():
            with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "mail_templates",
                                   "batch_job_notification.html")) \
                    as t_file:
                template = Template(t_file.read())
                subjobs = (JobManager(i) for i in self.get_subjob_ids())
                subjob_list = []
                for sj in subjobs:
                    query_name, target_name = sj._get_query_target_names()
                    subjob_list.append({
                        "job_name": sj.id_job,
                        "status": sj.status().get("status", "unknown"),
                        "query_name": query_name if query_name is not None else "",
                        "target_name": target_name if target_name is not None else "",
                        "error": sj.error,
                        "target_filtered": sj.is_target_filtered(),
                        "query_filtered": sj.is_query_filtered()
                    })
                return template.render(job_name=self.id_job, status=status, url_base=self.config.web_url,
                                       error=self.error, subjobs=subjob_list)
        else:
            with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "mail_templates",
                                   "job_notification.html")) \
                    as t_file:
                template = Template(t_file.read())
                return template.render(job_name=self.id_job, status=status, url_base=self.config.web_url,
                                       query_name=query_name if query_name is not None else "",
                                       target_name=target_name if target_name is not None else "",
                                       error=self.error,
                                       target_filtered=self.is_target_filtered(),
                                       query_filtered=self.is_query_filtered())

    def get_mail_subject(self, status):
        """
        Build mail subject

        :param status: job status
        :type status: str
        :return: mail subject
        :rtype: str
        """

        if status == "success" or status == "no-match":
            return "DGenies - Job completed: %s" % self.id_job
        else:
            return "DGenies - Job failed: %s" % self.id_job

    def set_send_mail(self, activate):
        """
        Set or unset the ability to send mail for the current job

        :param activate: activate send mail if true, deactivate if false
        :type activate: bool
        """
        no_mail_file = os.path.join(self.output_dir, ".no_mail")
        if activate:
            if os.path.exists(no_mail_file):
                os.remove(no_mail_file)
        else:
            Path(no_mail_file).touch()

    def is_send_mail_allowed(self):
        """
        Set or unset the ability to send mail for the current job

        :return: True is sending a mail is allowed, False else
        :rtype: bool
        """
        return MODE == "webserver" and self.config.send_mail_status \
               and not os.path.exists(os.path.join(self.output_dir, ".no_mail"))

    def send_mail_if_allowed(self):
        """
        Send mail
        """
        if self.is_send_mail_allowed():
            # Retrieve infos:
            with Job.connect():
                job = Job.get(Job.id_job == self.id_job)
                if self.email is None:
                    self.email = job.email
                status = job.status
                self.error = job.error

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

                # Send:
                self.mailer.send_mail(recipients=[self.email],
                                      subject=self.get_mail_subject(status),
                                      message=self.get_mail_content(status, target_name, query_name),
                                      message_html=self.get_mail_content_html(status, target_name, query_name))

    def send_mail_post_if_allowed(self):
        """
        Send mail using POST url (if there is no access to mailer like on cluster nodes)
        """
        if self.is_send_mail_allowed():
            key = Functions.random_string(15)
            key_file = os.path.join(self.config.app_data, self.id_job, ".key")
            with open(key_file, "w") as k_f:
                k_f.write(key)
            data = parse.urlencode({"key": key}).encode()
            req = request.Request(self.config.web_url + "/send-mail/" + self.id_job, data=data)
            resp = request.urlopen(req)
            if resp.getcode() != 200:
                logger.error("%s: Send mail failed!" % self.id_job)

    def search_error(self):
        """
        Search for an error in the log file (for local runs). If no error found, returns a generic error message

        :return: error message to give to the user
        :rtype: str
        """
        logs = os.path.join(self.output_dir, "logs.txt")
        if os.path.exists(logs) and os.name == 'posix':
            lines = subprocess.check_output(['tail', '-2', logs]).decode("utf-8").split("\n")
            if re.match(r"\[morecore] \d+ bytes requested but not available.", lines[1]) or \
                    re.match(r"\[morecore] \d+ bytes requested but not available.", lines[1]) or \
                    re.match(r"\[morecore] insufficient memory", lines[0]) or \
                    re.match(r"\[morecore] insufficient memory", lines[1]):
                return "Your job #ID# has failed because of memory limit exceeded. May be your sequences are too big?" \
                       "<br/>You can contact the support for more information."
        return "Your job #ID# has failed. You can try again.<br/>If the problem persists, please contact the support."

    def _launch_local(self):
        """
        Launch a job on the current machine

        :return: True if job succeed, else False
        :rtype: bool
        """
        if MODE == "webserver":
            cmd = ["/usr/bin/time", "-f", "%e %M"]
        else:
            cmd = []
        if self.query is not None:
            command_line = self.tool.command_line.replace("{query}", self.query.get_path())
        else:
            command_line = self.tool.all_vs_all
        out_file = None
        if ">" in command_line:
            out_file = self.paf_raw
            command_line = command_line[:command_line.index(">")]
        command_line = command_line.replace("{exe}", self.tool.exec) \
                                   .replace("{target}", self.target.get_path()) \
                                   .replace("{threads}", str(self.tool.threads)) \
                                   .replace("{options}", self.options) \
                                   .replace("{out}", self.paf_raw)

        cmd += command_line.split(" ")
        if out_file is None:
            with open(self.logs, "w") as logs:
                p = subprocess.Popen(cmd, stdout=logs, stderr=logs)
        else:
            with open(self.logs, "w") as logs, open(out_file, "w") as out:
                p = subprocess.Popen(cmd, stdout=out, stderr=logs)
        with Job.connect():
            status = "started"
            if MODE == "webserver":
                job = Job.get(Job.id_job == self.id_job)
                job.id_process = p.pid
                job.status = status
                job.save()
            else:
                job = None
                self.set_status_standalone(status)
            p.wait()
            if p.returncode == 0:
                status = self.check_job_success()
                if MODE == "webserver":
                    job.status = status
                    job.save()
                else:
                    self.set_status_standalone(status)
                if status == "no-match":
                    self._set_analytics_job_status("no-match")
                return status == "succeed"
            self.error = self.search_error()
            status = "fail"
            if MODE == "webserver":
                job.status = status
                job.error = self.error
                job.save()
            else:
                self.set_status_standalone(status, self.error)
        return False

    def check_job_status_slurm(self):
        """
        Check status of a SLURM job run

        :return: True if the job has successfully ended, else False
        """
        status = subprocess.check_output("sacct -p -n --format=state,maxvmsize,elapsed -j %s.batch" % self.id_process,
                                         shell=True).decode("utf-8").strip("\n")

        status = status.split("|")

        success = status[0] == "COMPLETED"
        if success:
            mem_peak = int(status[1][:-1])  # Remove the K letter
            elapsed_full = list(map(int, status[2].split(":")))
            elapsed = elapsed_full[0] * 3600 + elapsed_full[1] * 60 + elapsed_full[2]
            with open(self.logs, "a") as logs:
                logs.write("%s %d" % (elapsed, mem_peak))

        return success

    def check_job_status_sge(self):
        """
        Check status of a SGE job run

        :return: True if the job jas successfully ended, else False
        """
        status = "-1"
        start = None
        end = None
        mem_peak = None
        acct = subprocess.check_output("qacct -d 1 -j %s" % self.id_process,
                                       shell=True).decode("utf-8")
        lines = acct.split("\n")
        for line in lines:
            if line.startswith("failed"):
                status = re.split(r"\s+", line, 1)[1]
            elif line.startswith("start_time"):
                start = datetime.strptime(re.split(r"\s+", line, 1)[1], "%a %b %d %H:%M:%S %Y")
            elif line.startswith("end_time"):
                end = datetime.strptime(re.split(r"\s+", line, 1)[1], "%a %b %d %H:%M:%S %Y")
            elif line.startswith("maxvmem"):
                mem_peak = re.split(r"\s+", line, 1)[1]
                if mem_peak.endswith("G"):
                    mem_peak = int(mem_peak[-1]) * 1024 * 1024
                elif mem_peak.endswith("M"):
                    mem_peak = int(mem_peak[-1]) * 1024

        if status == "0":
            if start is not None and end is not None and mem_peak is not None:
                elapsed = end - start
                elapsed = elapsed.seconds
                with open(self.logs, "a") as logs:
                    logs.write("%s %d" % (elapsed, mem_peak))

        return status == "0"

    def set_job_status(self, status, error=""):
        """
        Change status of a job

        :param status: new job status
        :type status: str
        :param error: error description (if any)
        :type error: str
        """
        if MODE == "webserver":
            job = Job.get(Job.id_job == self.id_job)
            job.status = status
            job.error = error
            job.save()
        else:
            self.set_status_standalone(status, error)

    def update_job_status(self, status, id_process=None):
        """
        Update job status

        :param status: new status
        :param id_process: system process id or jobid on cluster scheduler
        """
        if MODE == "webserver":
            with Job.connect():
                job = Job.get(Job.id_job == self.id_job)
                job.status = status
                if id_process is not None:
                    job.id_process = id_process
                job.save()
        else:
            # unreachable code, update_job_status is only used in launch_to_cluster which is not used in standalone mode
            self.set_status_standalone(status)

    @staticmethod
    def find_error_in_log(log_file):
        """
        Find error in log (for cluster run)

        :param log_file: log file of the job
        :return: error (empty if no error)
        :rtype: str
        """
        error = ""
        with open(log_file, "r") as log:
            for line in log:
                if line.startswith("###ERR### "):
                    error = line[10:].rstrip()
                    break
        return error

    def launch_to_cluster(self, step, runner_type, command, args, log_out, log_err):
        """
        Launch a program to the cluster

        :param step: step (prepare, start)
        :type step: str
        :param runner_type: slurm or sge
        :type runner_type: str
        :param command: program to launch (without arguments)
        :type command: str
        :param args: arguments to use for the program
        :type args: list
        :param log_out: log file for stdout
        :type log_out: str
        :param log_err: log file for stderr
        :type log_err: str
        :return: True if succeed, else False
        :rtype: bool
        """
        import drmaa
        from dgenies.lib.drmaasession import DrmaaSession
        drmaa_session = DrmaaSession()
        s = drmaa_session.session
        jt = s.createJobTemplate()
        jt.remoteCommand = command
        jt.args = args
        jt.jobName = "_".join([step[:2], self.id_job])
        if log_out == log_err:
            jt.joinFiles = True
            jt.outputPath = ":" + log_out
        else:
            jt.joinFiles = False
            jt.outputPath = ":" + log_out
            jt.errorPath = ":" + log_err

        if step == "start":
            memory = self.config.cluster_memory
            if self.query is None:  # ava mode
                memory = self.config.cluster_memory_ava
                if memory > 32:
                    name, order, contigs, reversed_c, abs_start, c_len = Index.load(self.idx_t, False)
                    if c_len <= 500000000:
                        memory = 32
            if memory > self.tool.max_memory:
                memory = self.tool.max_memory
        else:
            memory = 8000

        native_specs = self.config.drmaa_native_specs
        if runner_type == "slurm":
            if native_specs == "###DEFAULT###":
                native_specs = "--mem-per-cpu={0} --mincpus={1} --time={2}"
            if step == "prepare":
                jt.nativeSpecification = native_specs.format(memory, 1, "02:00:00")
            elif step == "start":
                jt.nativeSpecification = native_specs.format(memory // self.tool.threads_cluster * 1000,
                                                             self.tool.threads_cluster, "02:00:00")
        elif runner_type == "sge":
            if native_specs == "###DEFAULT###":
                native_specs = "-l mem={0},h_vmem={0} -pe parallel_smp {1}"
            if step == "prepare":
                jt.nativeSpecification = native_specs.format(8000, 1)
            elif step == "start":
                jt.nativeSpecification = native_specs.format(
                    memory // self.tool.threads_cluster * 1000, self.tool.threads_cluster)
        jt.workingDirectory = self.output_dir
        jobid = s.runJob(jt)
        self.id_process = jobid

        self.update_job_status("scheduled-cluster" if step == "start" else "prepare-scheduled", jobid)

        retval = s.wait(jobid, drmaa.Session.TIMEOUT_WAIT_FOREVER)
        if retval.hasExited and (self.check_job_status_slurm() if runner_type == "slurm" else
        self.check_job_status_sge()):
            if step == "start":
                status = self.check_job_success()
                if status == "no-match":
                    self._set_analytics_job_status("no-match")
            else:
                status = "prepared"
            # job = Job.get(id_job=self.id_job)
            # job.status = status
            # db.commit()
            self.update_job_status(status)
            s.deleteJobTemplate(jt)
            return status == "succeed" or status == "prepared"
        error = self.find_error_in_log(log_err)
        if step == "prepare":
            error += "<br/>Please check your input file and try again."
        self.set_job_status("fail", error)

        s.deleteJobTemplate(jt)
        return False

    def _launch_drmaa(self, runner_type):
        """
        Launch the mapping step to a cluster

        :param runner_type: slurm or sge
        :return: True if job succeed, else False
        """

        if self.query is not None:
            args = re.sub("{exe}\s?", "", self.tool.command_line).replace("{query}", self.get_query_split())
        else:
            args = re.sub("{exe}\s?", "", self.tool.all_vs_all)
        out_file = self.logs
        if ">" in args:
            out_file = self.paf_raw
            args = args[:args.index(">")]
        args = args.replace("{target}", self.target.get_path()) \
                   .replace("{threads}", str(self.tool.threads_cluster)) \
                   .replace("{options}", self.options) \
                   .replace("{out}", self.paf_raw)

        args = args.split(" ")

        return self.launch_to_cluster(step="start",
                                      runner_type=runner_type,
                                      command=self.tool.exec,
                                      args=args,
                                      log_out=out_file,
                                      log_err=self.logs)

    def _getting_local_file(self, datafile):
        """
        Copy temp file to its final location

        :param datafile: data file Object
        :type datafile: DataFile
        :return: final full path of the file
        :rtype: str
        """
        finale_path = os.path.join(self.output_dir, os.path.basename(datafile.get_path()))
        if datafile.is_example():
            shutil.copy(datafile.get_path(), finale_path)
        else:
            if os.path.exists(datafile.get_path()):
                shutil.move(datafile.get_path(), finale_path)
            else:
                raise Exception("Unable to copy file from temp to finale path: %s file does not exists" %
                                (datafile.get_path()))
        return finale_path

    def normalize_files(self):
        """
        Rename data file with prefix and create dotfiles
        """
        for type_f in self.allowed_ext.get_roles(self.get_job_type()):
            datafile = getattr(self, type_f)
            if datafile is not None:
                finale_path = os.path.join(self.output_dir, type_f + "_" + os.path.basename(datafile.get_path()))
                if os.path.exists(datafile.get_path()):
                    logger.debug("Move {} to {}".format(datafile.get_path(), finale_path))
                    shutil.move(datafile.get_path(), finale_path)
                    datafile.set_path(finale_path)
                else:
                    raise Exception("Unable to normalize %s file: %s file does not exists" %
                                    (type_f, datafile.get_path()))

                # We create a "dot file" to store the file name for cluster
                with open(os.path.join(self.output_dir, "." + type_f), "w") as save_file:
                    save_file.write(finale_path)

    def _get_filename_from_url(self, url):
        """
        Retrieve filename from an URL (http or ftp). Will raise DGeniesURLInvalid exception on error.

        :param url: url of the file to download
        :type url: str
        :return: filename
        :rtype: str
        """
        if url not in self._filename_for_url:
            if url.startswith("ftp://"):
                self._filename_for_url[url] = url.split("/")[-1]
            elif url.startswith("http://") or url.startswith("https://"):
                try:
                    r = requests.head(url, allow_redirects=True)
                    self._filename_for_url[url] = r.url.split("/")[-1]
                    if 'content-disposition' in r.headers:
                        fnames = re.findall(r'filename="(.+)"', r.headers['content-disposition'])
                        if fnames:
                            self._filename_for_url[url] = fnames[0]
                except (ConnectionError, URLError):
                    raise DGeniesURLInvalid(url)
            else:
                raise DGeniesURLInvalid(url)
        return self._filename_for_url[url]

    def _download_file(self, url):
        """
        Download a file from an URL

        :param url: url of the file to download
        :type url: str
        :return: distant file name and absolute path of the downloaded file
        :rtype: tuple of str
        """
        distant_filename = self._get_filename_from_url(url)
        # Manage file override
        local_path = os.path.join(self.output_dir, distant_filename)
        i = 1
        while os.path.exists(local_path):
            local_path = os.path.join(self.output_dir, "{:d}_".format(i) + distant_filename)
            i += 1
        # NOTE the stream=True parameter
        if url.startswith("ftp://"):
            urlretrieve(url, local_path)
        else:
            r = requests.get(url, stream=True)
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
                        # f.flush() commented by recommendation from J.F.Sebastian
        return distant_filename, local_path

    def _getting_file_from_url(self, datafile):
        """
        Download file from URL

        :param datafile: input file description
        :type datafile: DataFile
        :return:
            * [0] Finale path of the downloaded file {str}
            * [1] Name of the downloaded file {str}
        :rtype: tuple
        """
        try:
            distant_filename, dl_path = self._download_file(datafile.get_path())
        except (ConnectionError, URLError):
            raise DGeniesURLInvalid(datafile.get_path())
        name = os.path.splitext(os.path.basename(distant_filename).replace(".gz", ""))[0]
        return dl_path, name

    def _check_url(self, datafile, contexts):
        """
        Check if an URL is valid, and if the file is valid too. If invalid, raise an DGeniesURLError

        :param datafile: datafile file object
        :type datafile: DataFile
        :param contexts: list of contexts as (job type, file role) the datafile is used with
        :type contexts: list of tuple
        """
        url = datafile.get_path()
        filename = self._get_filename_from_url(url)
        for job_type, file_role in contexts:
            logger.debug(file_role)
            formats = self.allowed_ext.get_formats(job_type, file_role)
            allowed = Functions.allowed_file(filename, tuple(formats))
            if not allowed:
                format_descriptions = [self.allowed_ext.get_description(f) for f in formats]
                raise DGeniesDistantFileTypeUnsupported(filename, url, format_descriptions)

    def clear(self):
        """
        Remove job dir
        """
        shutil.rmtree(self.output_dir)

    @staticmethod
    def get_pending_local_number():
        """
        Get number of jobs running or waiting for a run

        :return: number of jobs
        :rtype: int
        """
        if MODE == "webserver":
            with Job.connect():
                return len(Job.select().where((Job.runner_type == "local") & (Job.status != "success") &
                                              (Job.status != "fail") & (Job.status != "no-match")))
        else:
            return 0

    def check_file(self, datafile, input_type, size_limit, should_be_local):
        """
        Check if file is correct: format, size, valid gzip, will raise a DGeniesFileCheckError Exception on error
        Will set the size attribute of datafile

        :param datafile: file to check
        :type datafile: DataFile
        :param input_type: query, target, align, backup or batch
        :type input_type: str
        :param size_limit: limit of file size
        :type size_limit: int
        :param should_be_local: True if job should be treated locally
        :type should_be_local: bool
        :return: True if should be local, False else
        :rtype: bool
        """
        logger.info('Check file: {}'.format(datafile.get_path()))
        max_upload_size_readable = size_limit / 1024 / 1024
        with Job.connect():
            if datafile.get_path().endswith(".gz") and not self.is_gz_file(datafile.get_path()):
                # Check file is correctly gzipped
                raise DGeniesNotGzipFileError(input_type)
            # Check size:
            file_size = self.get_file_size(datafile.get_path())
            datafile.set_file_size(file_size)
            if -1 < size_limit < file_size:
                raise DGeniesUploadedFileSizeLimitError(input_type, max_upload_size_readable, unit="Mb",
                                                        compressed=False)

            if input_type == "align":
                aln_format = self.get_align_format(datafile.get_path())
                if not hasattr(validators, aln_format):
                    raise DGeniesAlignmentFileUnsupported()
                if not getattr(validators, aln_format)(datafile.get_path()):
                    raise DGeniesAlignmentFileInvalid()
            elif input_type not in ("backup", "batch"):
                if datafile.get_path().endswith(".idx"):
                    if not validators.v_idx(datafile.get_path()):
                        raise DGeniesIndexFileInvalid(input_type.capitalize())
                if self.config.runner_type != "local" and file_size >= getattr(self.config, "min_%s_size" % input_type):
                    should_be_local = False
        logger.info('Done check file: {}'.format(datafile.get_path()))

        return should_be_local

    def download_files_with_pending(self, datafiles_with_contexts, should_be_local):
        """
        Download files from URLs, with pending (according to the max number of concurrent downloads)

        :param datafiles_with_contexts: datafiles with contexts.
        :type datafiles_with_contexts: DataFileContextManager
        :param should_be_local: True if the job should be run locally (according to input file sizes), else False
        :type should_be_local: bool
        :return: True if the job should be run locally according to file local, False else
        :rtype: bool
        """
        with Job.connect():
            status = "getfiles-waiting"
            if MODE == "webserver":
                job = Job.get(Job.id_job == self.id_job)
                job.status = status
                job.save()
                # Create a session:
                s_id = Session.new(True)
                session = Session.get(s_id=s_id)
            else:
                status = "getfiles"
                session = None
                job = None
                s_id = None

            try:
                if MODE == "webserver":
                    allowed = session.ask_for_upload(True)
                    while not allowed:
                        time.sleep(15)
                        session = Session.get(s_id=s_id)
                        allowed = session.ask_for_upload(False)
                else:
                    allowed = True
                if allowed:
                    if MODE == "webserver":
                        job.status = "getfiles"
                        job.save()

                    # download each distant file
                    for datafile in datafiles_with_contexts.get_datafiles():
                        if datafile.get_type() != "local":
                            logger.info("Download file: {}".format(datafile.get_path()))
                            finale_path, filename = self._getting_file_from_url(datafile)  # Raise exception on error
                            datafile.set_path(finale_path)
                            datafile.set_name(filename)
                            datafile.set_type("local")
                            # Check file
                            for file_role, size_limit in datafiles_with_contexts.get_distinct(datafile, 'file_role', 'size_limit'):
                                should_be_local = self.check_file(datafile, file_role, size_limit, should_be_local)

            except (DGeniesFileCheckError, DGeniesURLError) as e:
                if MODE == "webserver":
                    session.delete_instance()
                # We propagate known errors (else will be catch with next except
                raise e

            except:
                # Except all possible exceptions, but in particular session disappearance on timeout
                traceback.print_exc()
                if MODE == "webserver":
                    session.delete_instance()
                raise DGeniesDownloadError

            if MODE == "webserver":
                session.delete_instance()
            return should_be_local

    def move_and_check_local_files(self, datafiles_with_contexts):
        """
        Move local file from tmp and check files (both local files and distant files)
        Raise DGeniesFileCheckError or DGeniesURLError on error

        :params datafiles_with_contexts: Datafiles with contexts (job type, file type, file size, ...) they apply to
        :type: DataFileContextManager
        :return: True if the job should be run locally according to file local, False else
        :rtype: bool
        """
        should_be_local = True
        for datafile in datafiles_with_contexts.get_datafiles():
            if datafile.get_type() == "local":
                # Move local files from tmp and check them
                datafile.set_path(self._getting_local_file(datafile))
                for file_role, size_limit in datafiles_with_contexts.get_distinct(datafile, 'file_role', 'size_limit'):
                    should_be_local = self.check_file(datafile, file_role, size_limit, should_be_local)
            else:
                contexts = datafiles_with_contexts.get_distinct(datafile, 'job_type', 'file_role')
                logger.debug(contexts)
                self._check_url(datafile, contexts)  # Will raise an exception on error
        return should_be_local

    def run_align_in_thread(self, runner_type="local"):
        """
        Run a job asynchronously into a new thread

        :param runner_type: slurm or sge
        :type runner_type: str
        """
        thread = threading.Timer(1, self.run_align, kwargs={"runner_type": runner_type})
        thread.start()  # Start the execution
        if MODE != "webserver":
            thread.join()

    def prepare_job_in_thread(self):
        """
        Prepare job, like getting data, in a new thread
        """
        thread = threading.Timer(1, self.prepare_job)
        thread.start()  # Start the execution
        if MODE != "webserver":
            thread.join()

    def prepare_align_cluster(self, runner_type):
        """
        Launch of prepare align data on a cluster

        :param runner_type: slurm or sge
        :type runner_type: str
        :return: True if succeed, else False
        :rtype: bool
        """
        args = [self.config.cluster_prepare_script,
                "-t", self.target.get_path(),
                "-m", self.target.get_name(),
                "-p", self.preptime_file]
        if self.query is not None:
            args += ["-q", self.query.get_path(),
                     "-u", self.get_query_split(),
                     "-n", self.query.get_name()]
            if self.tool.split_before:
                args.append("--split")
        success = self.launch_to_cluster(step="prepare",
                                         runner_type=runner_type,
                                         command=self.config.cluster_python_exec,
                                         args=args,
                                         log_out=self.logs,
                                         log_err=self.logs)
        self.send_mail_post_if_allowed()
        return success

    def prepare_align_local(self):
        """
        Prepare align data locally. On standalone mode, launch job after, if success.
        :return: True if job succeed, else False
        :rtype: bool
        """
        with open(self.preptime_file, "w") as ptime, Job.connect():
            self.set_job_status("preparing")
            ptime.write(str(round(time.time())) + "\n")
            error_tail = "Please check your input file and try again."
            if self.query is not None:
                fasta_in = self.query.get_path()
                if self.tool.split_before:
                    split = True
                    splitter = Splitter(input_f=fasta_in, name_f=self.query.get_name(), output_f=self.get_query_split(),
                                        query_index=self.query_index_split, debug=DEBUG)
                    success, error = splitter.split()
                    nb_contigs = splitter.nb_contigs
                    in_fasta = self.get_query_split()
                else:
                    split = False
                    uncompressed = None
                    if self.query.get_path().endswith(".gz"):
                        uncompressed = self.query.get_path()[:-3]
                    success, nb_contigs, error = index_file(self.query.get_path(), self.query.get_name(), self.idx_q,
                                                            uncompressed)
                    in_fasta = self.query.get_path()
                    if uncompressed is not None:
                        in_fasta = uncompressed
                if success:
                    filtered_fasta = os.path.join(os.path.dirname(self.get_query_split()), "filtered_" +
                                                  os.path.basename(self.get_query_split()))
                    filter_f = Filter(fasta=in_fasta,
                                      index_file=self.query_index_split if split else self.idx_q,
                                      type_f="query",
                                      min_filtered=round(nb_contigs / 4),
                                      split=True,
                                      out_fasta=filtered_fasta,
                                      replace_fa=True)
                    filter_f.filter()
                else:
                    self.set_job_status("fail", "<br/>".join(["Query fasta file is not valid:", error, error_tail]))
                    self.send_mail_post_if_allowed()
                    return False
            uncompressed = None
            if self.target.get_path().endswith(".gz"):
                uncompressed = self.target.get_path()[:-3]
            success, nb_contigs, error = index_file(self.target.get_path(), self.target.get_name(), self.idx_t,
                                                    uncompressed)
            if success:
                in_fasta = self.target.get_path()
                if uncompressed is not None:
                    in_fasta = uncompressed
                filtered_fasta = os.path.join(os.path.dirname(in_fasta), "filtered_" + os.path.basename(in_fasta))
                filter_f = Filter(fasta=in_fasta,
                                  index_file=self.idx_t,
                                  type_f="target",
                                  min_filtered=round(nb_contigs / 4),
                                  split=False,
                                  out_fasta=filtered_fasta,
                                  replace_fa=True)
                is_filtered = filter_f.filter()
                if uncompressed is not None:
                    if is_filtered:
                        # replace original fasta file with filtered one
                        os.remove(self.target.get_path())
                        self.target.set_path(uncompressed)
                        with open(os.path.join(self.output_dir, ".target"), "w") as save_file:
                            save_file.write(uncompressed)
                    else:
                        os.remove(uncompressed)
            else:
                if uncompressed is not None:
                    try:
                        os.remove(uncompressed)
                    except FileNotFoundError:
                        pass
                self.set_job_status("fail", "<br/>".join(["Target fasta file is not valid:", error, error_tail]))
                self.send_mail_post_if_allowed()
                return False
            ptime.write(str(round(time.time())) + "\n")
            self.set_job_status("prepared")
            if MODE != "webserver":
                self.run_align("local")
            return True

    def _end_of_prepare_dotplot(self):
        """
        Tasks done after preparing dot plot data: parse & sort of alignment file
        """
        # Parse alignment file:
        if hasattr(parsers, self.aln_format):
            getattr(parsers, self.aln_format)(self.align.get_path(), self.paf_raw)
            os.remove(self.align.get_path())
        elif self.aln_format == "paf":
            shutil.move(self.align.get_path(), self.paf_raw)
        else:
            self.set_job_status("fail", "No parser found for format %s. Please contact the support." % self.aln_format)
            return False

        self.set_job_status("started")

        # Sort paf lines:
        sorter = Sorter(self.paf_raw, self.paf)
        sorter.sort()
        os.remove(self.paf_raw)
        if self.target is not None and os.path.exists(self.target.get_path()) and not \
                self.target.get_path().endswith(".idx"):
            os.remove(self.target.get_path())

        self.align.set_path(self.paf)
        self.set_job_status("success")
        self.send_mail_post_if_allowed()
        return True

    def prepare_dotplot_cluster(self, runner_type):
        """
        Prepare data if alignment already done: just index the fasta (if index not given), then parse the alignment

        :param runner_type: type of cluster (slurm or sge)
        :type runner_type: str
        """

        args = [self.config.cluster_prepare_script,
                "-p", self.preptime_file, "--index-only"]

        has_index = False

        target_format = os.path.splitext(self.target.get_path())[1][1:]
        if target_format == "idx":
            shutil.move(self.target.get_path(), self.idx_t)
            os.remove(os.path.join(self.output_dir, ".target"))
        else:
            has_index = True
            args += ["-t", self.target.get_path(),
                     "-m", self.target.get_name()]
        if self.query is not None:
            query_format = os.path.splitext(self.query.get_path())[1][1:]
            if query_format == "idx":
                shutil.move(self.query.get_path(), self.idx_q)
                os.remove(os.path.join(self.output_dir, ".query"))
            else:
                has_index = True
                args += ["-q", self.query.get_path(),
                         "-n", self.query.get_name()]

        success = True
        if has_index:
            success = self.launch_to_cluster(step="prepare",
                                             runner_type=runner_type,
                                             command=self.config.cluster_python_exec,
                                             args=args,
                                             log_out=self.logs,
                                             log_err=self.logs)

        if success:
            if self.query is None:
                shutil.copy(self.idx_t, self.idx_q)
            return self._end_of_prepare_dotplot()

        self.send_mail_post_if_allowed()
        return False

    def prepare_dotplot_local(self):
        """
        Prepare data if alignment already done: just index the fasta (if index not given), then parse the alignment
        file and sort it.
        """
        self.set_job_status("preparing")
        # Prepare target index:
        target_format = os.path.splitext(self.target.get_path())[1][1:]
        if target_format == "idx":
            shutil.move(self.target.get_path(), self.idx_t)
            os.remove(os.path.join(self.output_dir, ".target"))
        else:
            index_file(self.target.get_path(), self.target.get_name(), self.idx_t)

        # Prepare query index:
        if self.query is not None:
            query_format = os.path.splitext(self.query.get_path())[1][1:]
            if query_format == "idx":
                shutil.move(self.query.get_path(), self.idx_q)
                os.remove(os.path.join(self.output_dir, ".query"))
            else:
                index_file(self.query.get_path(), self.query.get_name(), self.idx_q)
        else:
            shutil.copy(self.idx_t, self.idx_q)

        return self._end_of_prepare_dotplot()

    def write_jobs(self, jobs):
        """
        Write job description (file paths for roles, tool, options, ...) into a json file for futher steps file storing jobs description
        Document structure follows the message structure obtained from form.
        """
        with open(os.path.join(self.output_dir, ".jobs"), "wt", encoding = 'utf8') as json_file:
            data = [subjob.as_job_entry() for subjob in jobs]
            json.dump(data, json_file, allow_nan=True, )

    def read_jobs(self):
        """
        Read file storing job descriptions (file paths for roles, tool, options, ...)
        Document structure follows the message structure obtained from form.

        :return: list of dict. Each dict is a job is a dict where param:value
        :rtype: list
        """
        with open(os.path.join(self.output_dir, ".jobs"), "rt", encoding = 'utf8') as json_file:
            data = json.load(json_file)
            print(data)
            return data

    def get_subjob_ids(self):
        """
        Get the subjobs ids if any

        :return:
        :rtype: list of str
        """
        try:
            return [j['id_job'] for j in self.read_jobs()]
        except FileNotFoundError:
            return []

    def prepare_batch(self):
        """
        Prepare batch locally.
        """
        # We get the job list from .jobs file
        logger.info("Prepare batch job")
        subjobs = self.read_jobs()
        if not subjobs:
            self.set_job_status("fail", "Batch mode: no subjob found")
            self.send_mail_post_if_allowed()
            return False
        # We create a queue in order to run jobs sequentially in standalone mode.
        self.set_job_status("preparing")
        job_queue = []
        # TODO: get back options and tool
        for sj in subjobs:
            j = JobManager(sj["id_job"], email=self.email, mailer=self.mailer)
            j.set_inputs_from_res_dir()
            j.tool_name = sj["tool"] if "tool" in sj else None
            j.options = sj["options"] if "options" in sj else None
            job_queue.append(j)
        if MODE == "webserver":
            self.set_job_status("started-batch")
            for subjob in job_queue:
                logger.info("run job " + subjob.id_job)
                subjob.set_send_mail(False)
                subjob.launch()
        else:
            self.set_job_status("started-batch")
            for subjob in job_queue:
                logger.info("run job " + subjob.id_job)
                subjob.launch_standalone(sync=True)
            # We get end status for each subjob
            is_success = all(s in ("success", "no-match") for s in map(lambda j: j.get_status_standalone(), job_queue))
            # The batch job succeed if all subjobs succeed
            self.set_job_status("success") if is_success else self.set_job_status("fail")
        return True

    def prepare_job(self):
        """
        Launch job preparation (in particular preparing data) according to the job type
        """
        if self.batch is not None:
            # batch mode
            if MODE == "webserver":
                with Job.connect():
                    job = Job.get(Job.id_job == self.id_job)
                    success = self.prepare_batch()
                    if not success:
                        self._set_analytics_job_status("fail-batch-prepare")
            else:
                self.prepare_batch()
        elif self.align is None:
            # new align mode
            if MODE == "webserver":
                with Job.connect():
                    job = Job.get(Job.id_job == self.id_job)
                    if job.runner_type == "local":
                        success = self.prepare_align_local()
                    else:
                        success = self.prepare_align_cluster(job.runner_type)
                    if not success:
                        self._set_analytics_job_status("fail-prepare")
            else:
                self.prepare_align_local()
        else:
            # plot mode
            if MODE == "webserver":
                with Job.connect():
                    job = Job.get(Job.id_job == self.id_job)
                    if job.runner_type == "local":
                        success = self.prepare_dotplot_local()
                    else:
                        success = self.prepare_dotplot_cluster(job.runner_type)
                    if success:
                        self._set_analytics_job_status("success")
                    else:
                        self._set_analytics_job_status("fail-all")
            else:
                self.prepare_dotplot_local()

    def refresh_batch_status(self):
        status_list = []
        for i in self.get_subjob_ids():
            job = JobManager(i)
            status_list.append(job.status())
        print(status_list)
        is_finished = all(s["status"] in ("success", "fail", "no-match") for s in status_list)
        is_successfull = all(s["status"] in ("success", "no-match") for s in status_list)
        if is_finished:
            status = "success" if is_successfull else "fail"
            self._set_analytics_job_status(status)
            return status
        return "started-batch"

    def run_align(self, runner_type):
        """
        Run of a job (mapping step)

        :param runner_type: type of cluster (slurm or sge)
        :type runner_type: str
        """
        try:
            if self.batch is not None:
                # A batch job does nothing but refresh it state until it ends
                self.set_job_status(self.refresh_batch_status())
            else:
                # We start the 'align' job
                success = False
                if runner_type == "local":
                    success = self._launch_local()
                elif runner_type in ["slurm", "sge"]:
                    success = self._launch_drmaa(runner_type)
                if success:
                    with Job.connect():
                        # We get the stats of the job
                        if MODE == "webserver":
                            job = Job.get(Job.id_job == self.id_job)
                            with open(self.logs) as logs:
                                measures = logs.readlines()[-1].strip("\n").split(" ")
                                map_elapsed = round(float(measures[0]))
                                job.mem_peak = int(measures[1])
                            with open(self.preptime_file) as ptime:
                                lines = ptime.readlines()
                                start = int(lines[0].strip("\n"))
                                end = int(lines[1].strip("\n"))
                                prep_elapsed = end - start
                                job.time_elapsed = prep_elapsed + map_elapsed
                        else:
                            job = None
                        # We do the post processes
                        status = "merging"
                        if MODE == "webserver":
                            job.status = "merging"
                            job.save()
                        else:
                            self.set_status_standalone(status)
                        if self.tool.split_before and self.query is not None:
                            # If split and not ava, we merge back files
                            start = time.time()
                            paf_raw = self.paf_raw + ".split"
                            os.remove(self.get_query_split())
                            merger = Merger(self.paf_raw, paf_raw, self.query_index_split,
                                            self.idx_q, debug=DEBUG)
                            merger.merge()
                            os.remove(self.paf_raw)
                            os.remove(self.query_index_split)
                            self.paf_raw = paf_raw
                            end = time.time()
                            if MODE == "webserver":
                                job.time_elapsed += end - start
                        elif self.query is None:
                            # If ava, we copy target index to query index
                            shutil.copyfile(self.idx_t, self.idx_q)
                            Path(os.path.join(self.output_dir, ".all-vs-all")).touch()
                        if self.tool.parser is not None:
                            # The align file needs to be transformed to paf
                            paf_raw = self.paf_raw + ".parsed"
                            getattr(parsers, self.tool.parser)(self.paf_raw, paf_raw)
                            os.remove(self.paf_raw)
                            self.paf_raw = paf_raw
                        # Matches form paf file are sorted by desc. matching size
                        sorter = Sorter(self.paf_raw, self.paf)
                        sorter.sort()
                        os.remove(self.paf_raw)
                        # Cleanup target
                        if self.target is not None and os.path.exists(self.target.get_path()):
                            os.remove(self.target.get_path())
                        # The job ask to do a sort of contig
                        if os.path.isfile(os.path.join(self.output_dir, ".do-sort")):
                            paf = Paf(paf=self.paf,
                                      idx_q=self.idx_q,
                                      idx_t=self.idx_t,
                                      auto_parse=False)
                            paf.sort()
                            if not paf.parsed:
                                success = False
                                status = "fail"
                                error = "Error while sorting query. Please contact us to report the bug"
                                if MODE == "webserver":
                                    job = Job.get(Job.id_job == self.id_job)
                                    job.status = status
                                    job.error = error
                                    self._set_analytics_job_status("fail-sort")
                                else:
                                    self.set_status_standalone(status, error)
                        if success:
                            status = "success"
                            if MODE == "webserver":
                                job = Job.get(Job.id_job == self.id_job)
                                job.status = "success"
                                job.save()

                                # Analytics:
                                self._set_analytics_job_status("success")
                                self.send_mail_post_if_allowed()

                            else:
                                self.set_status_standalone(status)
                elif MODE == "webserver":
                    self._set_analytics_job_status("fail-map")
        except Exception as e:
            traceback.print_exc()
            with open(self.logs, 'a') as f:
                f.write(str(e))
                f.write(traceback.format_exc())
            self.set_job_status("fail", "Your job has failed for an unexpected reason. Please contact the support if"
                                        "the problem persists.")
            if MODE == "webserver":
                self._set_analytics_job_status("fail-map-after")

    def _anonymize_mail_client(self, email):
        """
        Replace the email address with its group defined in config file if anonymization is enabled
        :param email: email to anonymize
        :type email: str
        :return: email group if anonymization is enabled (empty string if no group matching), email else
        :rtype: str
        """
        if not self.config.disable_anonymous_analytics:
            return email
        if self.config.anonymous_analytics == "full_hash":
            return sha1(email.encode('utf-8')).hexdigest()
        if self.config.anonymous_analytics in ["dual_hash", "left_hash"]:
            lpart, rpart = email.rsplit('@', 1)
            return sha1(lpart.encode('utf-8')).hexdigest() + "@" + \
                   (sha1(
                       rpart.encode('utf-8')).hexdigest() if self.config.anonymous_analytics == "dual_hash" else rpart)
        else:
            for group, pattern in self.config.analytics_groups:
                if re.match(pattern, email):
                    return group
        return ''

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

    def _save_analytics_data(self):
        """
        Save analytics data into the database
        """
        if self.config.analytics_enabled and MODE == "webserver":
            from dgenies.database import Analytics
            with Job.connect():
                job = Job.get(Job.id_job == self.id_job)
                target_size = os.path.getsize(self.target.get_path()) if (self.target is not None and self.target.get_type()
                                                                          == "local" and
                                                                          os.path.exists(self.target.get_path())) else 0
                query_size = None
                if self.query is not None and self.query.get_type() == "local" and os.path.exists(self.query.get_path()):
                    query_size = os.path.getsize(self.query.get_path())
                log = Analytics.create(
                    id_job=self.id_job,
                    date_created=datetime.now(),
                    target_size=target_size,
                    query_size=query_size,
                    mail_client=self._anonymize_mail_client(job.email),
                    runner_type=job.runner_type,
                    job_type=self.get_job_type(),
                    tool=self.tool_name if self.tool_name is not None else "unset")
                log.save()

    def _set_analytics_job_status(self, status):
        """
        Change status for a job in analytics database

        :param status: new status
        :type status: str (20)
        """
        if self.config.analytics_enabled and MODE == "webserver":
            from dgenies.database import Analytics
            with Job.connect():
                analytic = Analytics.get(Analytics.id_job == self.id_job)
                if analytic.status != "no-match":
                    analytic.status = status
                    analytic.save()

    @staticmethod
    def allowed_backup_files(members, allowed_files=[]):
        """
        Generator filter files to be extracted from tar file

        :param members: elements in tarfile
        :type members: list of TarInfo
        :param allowed_files: list of allows files
        :type allowed_files: list of str
        """
        for tarinfo in members:
            if tarinfo.name in allowed_files:
                yield tarinfo

    def _unpack_backup(self, backup: DataFile, output_dir):
        """
        Unpack backup file. A backup file must contain 3 files: "./map.paf", "./query.idx" and "./target.idx".
        Will raise a DGeniesBackupUnpackError exception if file is not valid or on extraction error.

        :param backup: backup file to unpack
        :type backup: DataFile
        :param output_dir: Directory where to unpack backup
        :type output_dir: str or Path
        :return: a triplet of datafiles
            *[0]: query Datafile for "query.idx"
            *[1]: target Datafile for "target.idx"
            *[3]: align Datafile for "map.paf"
        :rtype: tuple
        """
        allowed_files = {"map.paf", "query.idx", "target.idx"}
        try:
            with tarfile.open(backup.get_path(), "r:*") as tar:
                members = tar.getmembers()
                if len(members) != 3:
                    raise DGeniesBackupUnpackError()
                for m in members:
                    if m.name not in allowed_files or not m.isfile():
                        raise DGeniesBackupUnpackError()
                tar.extractall(path=output_dir, members=self.allowed_backup_files(tar, allowed_files))
                align_path = os.path.join(output_dir, "map.paf")
                if not validators.paf(align_path):
                    raise DGeniesBackupUnpackError()
                target_path = os.path.join(output_dir, "target.idx")
                query_path = os.path.join(output_dir, "query.idx")
                if not validators.v_idx(target_path) or not validators.v_idx(query_path):
                    raise DGeniesBackupUnpackError()
                align = DataFile(name="map", path=align_path, type_f="local")
                target = DataFile(name="target", path=target_path, type_f="local")
                query = DataFile(name="query", path=query_path, type_f="local")
            return query, target, align
        except:
            traceback.print_exc()
            raise DGeniesBackupUnpackError()

    def unpack_backups(self, datafiles_with_contexts):
        """
        Unpack all backup files (if any) and update associated job. Backup files are deleted if not used as anything
        else in other jobs.
        On error raise an DGeniesBackupUnpackError exception.

        :params datafiles_with_contexts: Collection of datafiles with associated contexts
        :params datafiles_with_contexts: DataFileContextManager
        """
        try:
            for datafile in datafiles_with_contexts.get_datafiles():
                if ("backup",) in datafiles_with_contexts.get_distinct(datafile, 'file_role'):
                    logger.info("Unpack backup file {} ...".format(datafile.get_path()))
                    output_dir = os.path.join(self.output_dir,
                                              os.path.splitext(re.sub(r"\.gz$", "", datafile.get_path()))[0])
                    os.mkdir(output_dir)
                    query, target, align = self._unpack_backup(datafile, output_dir)
                    # Remove backup datafiles
                    removed_ctx = datafiles_with_contexts.remove(datafile, file_role="backup")
                    # Add the extracted datafiles and update jobs
                    for ctx in removed_ctx:
                        # remove batch file from jobs it appears in
                        ctx.job.unset_role('backup')
                        # add decompressed datafiles into jobs in which they are used
                        for role, new_datafile in [("align", align), ("query", query), ("target", target)]:
                            new_ctx = ctx.clone()
                            new_ctx.file_role = role
                            new_ctx.job.set_role(role, new_datafile)
                            datafiles_with_contexts.add(new_datafile, new_ctx)
                    logger.info("Unpack backup file {} OK".format(datafile.get_path()))

                if not datafiles_with_contexts.get_distinct(datafile, 'file_role'):
                    # File is not used anywhere else, we remove it
                    os.remove(datafile.get_path())
        except DGeniesBackupUnpackError as e:
            raise e

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

    def to_job_list(self):
        """
        Get a representation of current job a list of jobs similar to what we obtain when reading batch file
        """
        job = self.as_job_entry()
        jobtype = job.pop('type')
        return [(jobtype, job)]

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
                try:
                    v = cache[v]
                except KeyError:
                    v = DataFile.create(name=os.path.basename(v), path=v)
                    cache[v] = v
            res[p] = v
        return job_type, res

    def read_batch_file(self):
        """
        Read batch file where file are deduplicated datafiles

        :return: list of jobs
        :rtype: list of tuple
        """
        cache = dict()
        try:
            job_list = [self.from_file_to_datafiles(jt, params, cache) for jt, params in
                        read_batch_file(self.batch.get_path())]
        except DGeniesBatchFileError as e:
            self.set_job_status("fail", e.message)
            self.send_mail_post_if_allowed()
            raise e
        return job_list

    def create_subjob(self, job_type, params_dict):
        """"
        Create a list of JobManager objects

        :params job_params: List of jobs with parameters such as each entry is
            * [0] the job type
            * [1] a dict of params -> value
        :type job_params: list of couples
        :return: list of jobs
        :rtype: list of JobManager
        """
        # We create a subjob id and the corresponding working directory
        random_length = 5
        job_id_prefix = params_dict.get(
            "id_job",
            self.id_job
        )
        job_id_prefix = job_id_prefix[0: min(len(job_id_prefix), ID_JOB_LENGTH - random_length - 1)]
        subjob_id = job_id_prefix + "_" + Functions.random_string(random_length)
        while os.path.exists(os.path.join(self.config.app_data, subjob_id)):
            subjob_id = job_id_prefix + "_" + Functions.random_string(random_length)
        folder_files = os.path.join(self.config.app_data, subjob_id)
        os.makedirs(folder_files)
        # We create the subjob itself
        subjob = JobManager(
            id_job=subjob_id,
            email=self.email,
            query=params_dict.get("query", None),
            target=params_dict.get("target", None),
            align=params_dict.get("align", None),
            backup=params_dict.get("backup", None),
            mailer=self.mailer,
            tool=params_dict.get("tool", None),
            options=params_dict.get("options", None))
        return subjob

    def start_job(self):
        """
        Start job: download, check and parse input files
        """
        with Job.connect():
            status = "getfiles"
            if MODE == "webserver":
                job = Job.get(Job.id_job == self.id_job)
                job.status = status
                job.save()
            else:
                job = None
                self.set_status_standalone(status)
            try:
                if os.path.exists(os.path.join(self.output_dir, '.already_checked')):
                    logger.info("Files already checked, skipping file checking")
                    should_be_local = not os.path.exists(os.path.join(self.output_dir, '.should_not_be_local'))
                    logger.debug("Job should be local: {}".format(should_be_local))
                else:
                    job_list = self.to_job_list()
                    logger.debug(job_list)
                    dcm = DataFileContextManager([self])
                    logger.info("Check local files...")
                    # Will raise a DGeniesFileCheckError or DGeniesURLError on error
                    should_be_local = self.move_and_check_local_files(dcm)
                    logger.info("Check local files: OK")

                    # Some files may be downloaded
                    # Will raise a DGeniesURLError, DGeniesDownloadError or DGeniesFileCheckError on error
                    logger.info("Download distant files...")
                    should_be_local = self.download_files_with_pending(dcm, should_be_local)
                    logger.info("Download distant files: OK")

                    if self.backup is not None:
                        logger.info("Unpack backup files...")
                        self.unpack_backups(dcm)
                        logger.info("Unpack backup files: OK")

                    #  Normalize files for job: add prefix to data files and create dotfiles.
                    logger.info("Normalize filenames...")
                    self.normalize_files()
                    logger.info("Normalize filenames: OK")

                    if self.is_batch():
                        logger.info("Manage files in batch file...")

                        # We read the batch file and get (jobtype, files)
                        job_list = self.read_batch_file()
                        logger.debug(job_list)
                        # Prepare list of datafiles with context for checking
                        job_dict = dict()
                        for jobtype, params in job_list:
                            subjob = self.create_subjob(jobtype, params)
                            logger.debug("Job created: {}".format(subjob.id_job))
                            job_dict[subjob.id_job] = subjob

                        dcm = DataFileContextManager(job_dict.values())

                        logger.info("Check local files for batch...")
                        # Will raise a DGeniesFileCheckError or DGeniesURLError on error
                        self.move_and_check_local_files(dcm)
                        logger.info("Check local files for batch: OK")

                        # Some files may be downloaded
                        # Will raise a DGeniesURLError, DGeniesDownloadError or DGeniesFileCheckError on error
                        logger.info("Download distant files for batch...")
                        self.download_files_with_pending(dcm, True)
                        logger.info("Download distant files for batch: OK")

                        # Unpack backup files if any
                        self.unpack_backups(dcm)

                        # Move and check datafile in working dir
                        logger.info("Copy files in each subjob...")
                        # We copy datafile in subjob directory, duplicate datafile and update subjob
                        for datafile in dcm.get_datafiles():
                            for subjob, file_role in dcm.get_distinct(datafile, 'job', 'file_role'):
                                logger.info("Copy {f} to {j}...".format(f=datafile.get_path(), j=subjob.id_job))
                                new_path = os.path.join(subjob.output_dir, os.path.basename(datafile.get_path()))
                                shutil.copy(datafile.get_path(), new_path)
                                new_datafile = datafile.clone()
                                new_datafile.set_path(new_path)
                                subjob.set_role(file_role, new_datafile)
                                if MODE == "webserver" and subjob.config.runner_type != "local" \
                                        and hasattr(subjob.config, "min_%s_size" % file_role) \
                                        and datafile.get_file_size() >= getattr(subjob.config, "min_%s_size" % file_role):
                                    # We set a flag to tell job must run on cluster
                                    Path(os.path.join(subjob.output_dir, '.should_not_be_local')).touch()
                        #os.remove(datafile.get_path())  # We remove uneeded files for batch dir
                        logger.info("Copy files in each subjob: OK")

                        for subjob in job_dict.values():
                            logger.info("Normalize files in subjob: {}".format(subjob.id_job))
                            subjob.normalize_files()
                            logger.info("Done normalize files in subjob: {}".format(subjob.id_job))
                            # We set a flag to tell the files of subjob are already checked
                            Path(os.path.join(subjob.output_dir, '.already_checked')).touch()

                        # Backup jobs with params for next step in standalone mode.
                        self.write_jobs(job_dict.values())


                # Set the runner according to available resource
                if MODE == "webserver" and job.runner_type != "local" and should_be_local \
                        and self.get_pending_local_number() < self.config.max_run_local:
                    job.runner_type = "local"
                    job.save()

            except (DGeniesFileCheckError, DGeniesURLError, DGeniesDownloadError) as e:
                self.set_job_status("fail", e.message)
                self._save_analytics_data()
                self._set_analytics_job_status("fail-getfiles")
                if e.clear_job:
                    self.clear()

            except DGeniesBackupUnpackError as e:
                self.set_job_status("fail", e.message)
                self._save_analytics_data()
                self.send_mail_if_allowed()
                if e.clear_job:
                    self.clear()

            except Exception:
                traceback.print_exc()
                error = "<p>An unexpected error has occurred while getting the files. Please contact the support to " \
                        "report the bug.</p> "
                self.set_job_status("fail", error)
                self._save_analytics_data()
                self._set_analytics_job_status("fail-getfiles")
                self.send_mail_if_allowed()

            else:
                self._save_analytics_data()
                # Prepare job for next step
                status = "waiting"
                if MODE == "webserver":
                    # Register job for next step
                    job = Job.get(Job.id_job == self.id_job)
                    job.status = status
                    job.save()
                else:
                    # Start next step
                    self.set_status_standalone(status)
                    self.prepare_job_in_thread()

    def launch_standalone(self, sync=False):
        """
        Launch a job in standalone mode (asynchronously in a new thread)
        :param sync: force sync
        :type sync: bool
        """
        print(self.get_job_type())
        if not os.path.exists(self.output_dir):
            os.mkdir(self.output_dir)
        self.set_status_standalone("submitted")
        thread = threading.Timer(1, self.start_job)
        thread.start()
        if sync:
            thread.join()

    def launch(self):
        """
        Launch a job in webserver mode (asynchronously in a new thread)
        """
        logger.info(self.id_job + ": start " + self.get_job_type() + "job")
        with Job.connect():
            # Cleanup
            j1 = Job.select().where(Job.id_job == self.id_job)
            if len(j1) > 0:
                logger.info(self.id_job + ": Old job found without result dir existing: delete it from BDD!")
                for j11 in j1:
                    j11.delete_instance()
            if self.target is not None or self.backup is not None or self.batch is not None:
                # We create the job if everything is correct
                job = Job.create(id_job=self.id_job, email=self.email, runner_type=self.config.runner_type,
                                 date_created=datetime.now(), tool=self.tool.name if self.tool is not None else None,
                                 options=self.options)
                job.save()
                if not os.path.exists(self.output_dir):
                    os.mkdir(self.output_dir)
                thread = threading.Timer(1, self.start_job)
                thread.start()
            else:
                # Something missing in job description
                job = Job.create(id_job=self.id_job, email=self.email, runner_type=self.config.runner_type,
                                 date_created=datetime.now(), tool=self.tool.name if self.tool is not None else None,
                                 options=self.options, status="fail")
                job.save()

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

        :return:
            * [0] Success of the deletion
            * [1] Error message, if any (else empty string)
        :rtype: (bool, str)
        """
        if not os.path.exists(self.output_dir) or not os.path.isdir(self.output_dir):
            return False, "Job does not exists"
        if MODE == "webserver":
            # Forbid to delete job existing in gallery
            try:
                job = Job.get(id_job=self.id_job)
            except DoesNotExist:
                pass
            else:
                is_gallery = Gallery.select().where(Gallery.job == job)
                if is_gallery:
                    return False, "Delete a job that is in gallery is forbidden"
                job.delete_instance()
        shutil.rmtree(self.output_dir)
        return True, ""

    def get_input_roles(self, datafile):
        return (a for a in self.datafile_roles if getattr(self, a) is datafile)

    def check_size(self, datafile: DataFile):
        """
        Check if datafile size is correct

        :param datafile: local datafile
        :type datafile: DataFile
        :return: file size (bytes)
        :rtype: int
        """
        if datafile.get_path().endswith(".gz") and not self.is_gz_file(datafile.get_path()):
            # Check file is correctly gzipped
            raise DGeniesNotGzipFileError(datafile.get_path())
        file_size = self.get_file_size(datafile.get_path())
        datafile.set_file_size(file_size)
        for role in self.get_input_roles(datafile):
            size_limit = self.get_size_limit(role)
            max_upload_size_readable = size_limit / 1024 / 1024
            if -1 < size_limit < file_size:
                raise DGeniesUploadedFileSizeLimitError(role, max_upload_size_readable, unit="Mb", compressed=False)
        return file_size

    def check_format(self, datafile: DataFile, role: str):
        """
        Check if file format is correct. Will raise a DGeniesFileCheckError Exception on error

        :param datafile: datafile to check
        :type datafile: DataFile
        :param role: query, target, align, backup or batch
        :type role: str
        """
        pass

    def check_local_file(self, datafile: DataFile, role: str, should_be_local: bool):
        file_size = self.check_size(datafile)
        self.check_format(datafile, role)
        if self.config.runner_type != "local" and file_size >= getattr(self.config, "min_%s_size" % role):
            should_be_local = False
        return should_be_local


class AlignJob(JobManager):

    job_type = "align"
    datafile_roles = ["query", "target"]

    def __init__(self, id_job,  email: str = None, mailer = None, query: DataFile = None, target: DataFile = None,
                 tool: str = None, options=None):
        super().__init__(id_job, email=email, mailer=mailer)
        self.tool = tool
        self._align = None
        self._query = query
        self._target = target
        self.options = options

    def _get_datafile_from_job_dir(self, role: str) -> DataFile:
        """
        Create datafile from job dir, raise DGeniesMissingFileException on error

        :rtype: DataFile
        """
        datafile = None
        res_dir = os.path.join(self.config.app_data, self.id_job)
        dot_file = os.path.join(res_dir, ".{}".format(role))
        if os.path.exists(dot_file):
            with open(dot_file) as infile:
                file_path = infile.readline()
                datafile = DataFile(
                    name=os.path.splitext(re.sub(r'^[^_]*_(.*)\.gz$', r'\1', os.path.basename(file_path)))[0],
                    path=file_path,
                    type_f="local"
                )
        else:
            raise BaseException()
        return datafile

    @property
    def align(self):
        if self._align is None:
            self._align = self._get_datafile_from_job_dir('align')
        return self._align

    @align.setter
    def align(self, value):
        self._align = value
    def is_ava(self):
        return self.query is None and self.target is not None


class PlotJob(JobManager):

    job_type = "plot"
    datafile_roles = ["query", "target", "align", "backup"]

    def __init__(self, id_job,  email: str = None, mailer=None, align: DataFile = None, query: DataFile = None,
                 target: DataFile = None, backup: DataFile = None):
        super().__init__(id_job, email=email, mailer=mailer)
        # a Plot job is either construct from triplet align, query and target
        self.align = align
        self.aln_format = os.path.splitext(align.get_path())[1][1:] if align is not None else None
        self.query = query
        self.target = target
        # or a backup file (that will contain align, query and target)
        self.backup = backup

    def check_format(self, datafile, role):
        if role == "align":
            if not hasattr(validators, self.aln_format):
                raise DGeniesAlignmentFileUnsupported()
            if not getattr(validators, self.aln_format)(datafile.get_path()):
                raise DGeniesAlignmentFileInvalid()
        if role in {"query", "target"}:
            if datafile.get_path().endswith(".idx"):
                if not validators.v_idx(datafile.get_path()):
                    raise DGeniesIndexFileInvalid(datafile.get_path().capitalize())


class BatchJob(JobManager):

    job_type = "batch"
    datafile_roles = ["batch"]

    def __init__(self, id_job,  email: str = None, mailer=None, batch: DataFile = None, jobs=None):
        super().__init__(id_job, email=email, mailer=mailer)
        self.batch = batch
        self.jobs = jobs


class DataFileContext:
    """
    Keep track of datafile context
    """

    def __init__(self, job: JobManager, job_type: str, file_role: str, size_limit: int):
        self.job = job
        self.job_type = job_type
        self.file_role = file_role
        self.size_limit = size_limit

    def clone(self):
        return DataFileContext(self.job, self.job_type, self.file_role, self.size_limit)

    def __repr__(self):
        rep = ', '.join(['{}:{}'.format(k, v) for k, v in {'job': self.job, 'job_type': self.job_type,
                                                           'file_role': self.file_role, 'size_limit': self.size_limit}.items()])
        return 'DataFileContext({})'.format(rep)

    def __str__(self):
        return self.__repr__()

class DataFileContextManager:
    """
    Manage Datafile contexts
    """

    def __init__(self, jobs):
        """
        Create list of DatafilesContext for each Datafile in jobs
        """
        self.datafile_dict = dict()
        config = AppConfigReader()
        for j in jobs:
            job_type = j.get_job_type()
            for file_role, datafile in j.get_datafiles():
                size_limit = j.get_file_size_for_role(file_role)
                dc = DataFileContext(job=j, job_type=job_type, file_role=file_role, size_limit=size_limit)
                self.add(datafile, dc)

    def add(self, datafile, context):
        """
        Remove datafile matching attribute from datafile context manager. Datafile is removed if it has no more context
        """
        try:
            self.datafile_dict[datafile].append(context)
        except KeyError:
            self.datafile_dict[datafile] = [context]

    def remove(self, datafile, **kwargs):
        """
        Remove datafile matching attribute from datafile context manager. Datafile is removed if it has no more context
        """
        to_remove, to_keep = [], []
        if datafile in self.datafile_dict:
            for ctx in self.datafile_dict[datafile]:
                if all([getattr(ctx, attr) == val for attr, val in kwargs.items()]):
                    to_remove.append(ctx)
                else:
                    to_keep.append(ctx)
            if to_keep:
                self.datafile_dict[datafile] = to_keep
            else:
                del self.datafile_dict[datafile]
        return to_remove

    def get_datafiles(self):
        return list(self.datafile_dict.keys())

    def get_distinct(self, datafile, *args):
        if datafile in self.datafile_dict:
            contexts = self.datafile_dict[datafile]
            return set(tuple(getattr(context, a) for a in args) for context in contexts)
        else:
            return set()

    def __repr__(self):
        return [(datafile.get_path(), c) for datafile, contexts in self.datafile_dict.items() for c in contexts]

    def __str__(self):
        return str(self.__repr__())