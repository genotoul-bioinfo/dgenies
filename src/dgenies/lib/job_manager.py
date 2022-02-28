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
from .fasta import Fasta
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
import gzip
import io
import binascii
from dgenies.database import Job

if MODE == "webserver":
    from dgenies.database import Session, Gallery
    from peewee import DoesNotExist


class JobManager:
    """
    Jobs management
    """

    def __init__(self, id_job, email=None, query: Fasta=None, target: Fasta=None, mailer=None,
                 tool="minimap2", align: Fasta=None, backup: Fasta=None, options=None):
        """
        :param id_job: job id
        :type id_job: str
        :param email: email from user
        :type email: str
        :param query: query fasta
        :type query: Fasta
        :param target: target fasta
        :type target: Fasta
        :param mailer: mailer object (to send mail throw flask app)
        :type mailer: Mailer
        :param tool: tool to use for mapping (choice from tools config)
        :type tool: str
        :param align: alignment file (PAF, MAF, ...) as a fasta object
        :type align: Fasta
        :param backup: backup TAR file
        :type backup: Fasta
        :param options: list of str containing options for the chosen tool
        :type options: list
        """
        self.id_job = id_job
        self.email = email
        self.query = query
        self.target = target
        self.align = align
        if align is not None:
            self.aln_format = os.path.splitext(align.get_path())[1][1:]
        self.backup = backup
        self.error = ""
        self.id_process = "-1"
        # Get configs:
        self.config = AppConfigReader()
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
        self._filename_for_url = {}

    def do_align(self):
        """
        Check if we have to make alignment

        :return: True if the job is launched with an alignment file
        """
        return not os.path.exists(os.path.join(self.output_dir, ".align"))

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
                self.query = Fasta(
                    name="target" if file_path.endswith(".idx") else
                         os.path.splitext(os.path.basename(file_path.replace(".gz", "")).split("_", 1)[1])[0],
                    path=file_path,
                    type_f="local"
                )
        target_file = os.path.join(res_dir, ".target")
        if os.path.exists(target_file):
            with open(target_file) as t_f:
                file_path = t_f.readline()
                self.target = Fasta(
                    name="query" if file_path.endswith(".idx") else
                         os.path.splitext(os.path.basename(file_path.replace(".gz", "")).split("_", 1)[1])[0],
                    path=file_path,
                    type_f="local"
                )
        align_file = os.path.join(res_dir, ".align")
        if os.path.exists(align_file):
            with open(align_file) as a_f:
                file_path = a_f.readline()
                self.align = Fasta(
                    name="map",
                    path=file_path,
                    type_f="local"
                )
                self.aln_format = os.path.splitext(file_path)[1][1:]

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
        """
        return os.path.exists(os.path.join(self.output_dir, ".filter-query"))

    def is_target_filtered(self):
        """
        Check if target has been filtered

        :return: True if filtered, else False
        :return:
        """
        return os.path.exists(os.path.join(self.output_dir, ".filter-target"))

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
        if status == "success":
            message += "Your job %s was completed successfully!\n\n" % self.id_job
            message += str("Your job {0} is finished. You can see  the results by clicking on the link below:\n"
                           "{1}/result/{0}\n\n").format(self.id_job, self.config.web_url)
        else:
            message += "Your job %s has failed!\n\n" % self.id_job
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
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "mail_templates", "job_notification.html"))\
                as t_file:
            template = Template(t_file.read())
            return template.render(job_name=self.id_job, status=status, url_base=self.config.web_url,
                                   query_name=query_name if query_name is not None else "",
                                   target_name=target_name if target_name is not None else "",
                                   error=self.error,
                                   target_filtered=self.is_target_filtered(), query_filtered=self.is_query_filtered())

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

    def send_mail(self):
        """
        Send mail
        """
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

    def update_job_status(self, status, id_process=None):
        """
        Update job status

        :param status: new status
        :param id_process: system process id
        """
        if MODE == "webserver":
            with Job.connect():
                job = Job.get(Job.id_job == self.id_job)
                job.status = status
                if id_process is not None:
                    job.id_process = id_process
                job.save()
        else:
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

    def launch_to_cluster(self, step, batch_system_type, command, args, log_out, log_err):
        """
        Launch a program to the cluster

        :param step: step (prepare, start)
        :type step: str
        :param batch_system_type: slurm or sge
        :type batch_system_type: str
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
            if self.query is None:
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
        if batch_system_type == "slurm":
            if native_specs == "###DEFAULT###":
                native_specs = "--mem-per-cpu={0} --mincpus={1} --time={2}"
            if step == "prepare":
                jt.nativeSpecification = native_specs.format(memory, 1, "02:00:00")
            elif step == "start":
                jt.nativeSpecification = native_specs.format(memory // self.tool.threads_cluster * 1000,
                                                             self.tool.threads_cluster, "02:00:00")
        elif batch_system_type == "sge":
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
        if retval.hasExited and (self.check_job_status_slurm() if batch_system_type == "slurm" else
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

    def _launch_drmaa(self, batch_system_type):
        """
        Launch the mapping step to a cluster

        :param batch_system_type: slurm or sge
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
                                      batch_system_type=batch_system_type,
                                      command=self.tool.exec,
                                      args=args,
                                      log_out=out_file,
                                      log_err=self.logs)

    def _getting_local_file(self, fasta, type_f):
        """
        Copy temp file to its final location

        :param fasta: fasta file Object
        :type fasta: Fasta
        :param type_f: query or target
        :type type_f: str
        :return: final full path of the file
        :rtype: str
        """
        finale_path = os.path.join(self.output_dir, type_f + "_" + os.path.basename(fasta.get_path()))
        if fasta.is_example():
            shutil.copy(fasta.get_path(), finale_path)
        else:
            if os.path.exists(fasta.get_path()):
                shutil.move(fasta.get_path(), finale_path)
            else:
                other_file = os.path.join(self.output_dir, ("query" if type_f == "target" else "query") + "_" +
                                          os.path.basename(fasta.get_path()))
                if os.path.exists(other_file):
                    shutil.copy(other_file, finale_path)
                else:
                    raise Exception("Unable to copy %s file from temp to finale path: %s file does not exists" %
                                    (type_f, fasta.get_path()))

        with open(os.path.join(self.output_dir, "." + type_f), "w") as save_file:
            save_file.write(finale_path)
        return finale_path

    def _get_filename_from_url(self, url):
        """
        Retrieve filename from an URL (http or ftp)

        :param url: url of the file to download
        :type url: str
        :return: filename
        :rtype: str
        """
        if url not in self._filename_for_url:
            if url.startswith("ftp://"):
                self._filename_for_url[url] = url.split("/")[-1]
            elif url.startswith("http://") or url.startswith("https://"):
                self._filename_for_url[url] = requests.head(url, allow_redirects=True).url.split("/")[-1]
            else:
                return None
        return self._filename_for_url[url]

    def _download_file(self, url):
        """
        Download a file from an URL

        :param url: url of the file to download
        :type url: str
        :return: absolute path of the downloaded file
        :rtype: str
        """
        local_filename = os.path.join(self.output_dir, self._get_filename_from_url(url))
        # NOTE the stream=True parameter
        if url.startswith("ftp://"):
            urlretrieve(url, local_filename)
        else:
            r = requests.get(url, stream=True)
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
                        # f.flush() commented by recommendation from J.F.Sebastian
        return local_filename

    def _getting_file_from_url(self, fasta, type_f):
        """
        Download file from URL

        :param fasta: Fasta object describing the input file
        :type fasta: Fasta
        :param type_f: type of the file (query or target)
        :type type_f: str
        :return:
            * [0] True if no error happened, else False
            * [1] If an error happened, True if the error was saved for the job, else False (will be saved later)
            * [2] Finale path of the downloaded file {str}
            * [3] Name of the downloaded file {str}
        :rtype: tuple
        """
        try:
            dl_path = self._download_file(fasta.get_path())
        except (ConnectionError, URLError):
            status = "fail"
            error = "<p>Url <b>%s</b> is not valid!</p>" \
                    "<p>If this is unattended, please contact the support.</p>" % fasta.get_path()
            if MODE == "webserver":
                with Job.connect():
                    job = Job.get(Job.id_job == self.id_job)
                    job.status = status
                    job.error = error
                    job.save()
            else:
                self.set_status_standalone(status, error)
            return False, True, None, None
        filename = os.path.basename(dl_path)
        name = os.path.splitext(filename.replace(".gz", ""))[0]
        finale_path = os.path.join(self.output_dir, type_f + "_" + filename)
        shutil.move(dl_path, finale_path)
        with open(os.path.join(self.output_dir, "." + type_f), "w") as save_file:
            save_file.write(finale_path)
        return True, False, finale_path, name

    def _check_url(self, fasta, formats):
        """
        Check if an URL is valid, and if the file is valid too

        :param fasta: fasta file object
        :type fasta: Fasta
        :param formats: allowed file formats
        :type formats: tuple
        :return: True if URL and file are valid, else False
        :rtype: bool
        """
        url = fasta.get_path()
        try:
            filename = self._get_filename_from_url(url)
        except (ConnectionError, URLError):
            status = "fail"
            error = "<p>Url <b>%s</b> is not valid!</p>" \
                    "<p>If this is unattended, please contact the support.</p>" % fasta.get_path()
            if MODE == "webserver":
                with Job.connect():
                    job = Job.get(Job.id_job == self.id_job)
                    job.status = status
                    job.error = error
                    job.save()
            else:
                self.set_status_standalone(status, error)
            return False
        if filename is not None:
            allowed = Functions.allowed_file(filename, formats)
            if not allowed:
                status = "fail"
                format_txt = ""
                if len(formats) == 1:
                    if formats[0] == "fasta":
                        format_txt = "a Fasta file"
                    elif formats[0] == "idx":
                        format_txt = "an index file"
                    elif formats[0] == "map":
                        format_txt = "an alignment file"
                    elif formats[0] == "backup":
                        format_txt = "a backup file"
                    else:
                        format_txt = "a valid file"
                else:
                    if "fasta" in formats and "idx" in formats:
                        format_txt = "a Fasta file or an index file"
                    else:
                        format_txt = "a valid file"
                error = "<p>File <b>%s</b> downloaded from <b>%s</b> is not %s!</p>" \
                        "<p>If this is unattended, please contact the support.</p>" % (filename, url, format_txt)
                if MODE == "webserver":
                    with Job.connect():
                        job = Job.get(Job.id_job == self.id_job)
                        job.status = status
                        job.error = error
                        job.save()
                else:
                    self.set_status_standalone(status, error)
        else:
            allowed = False
            status = "fail"
            error = "<p>Url <b>%s</b> is not a valid URL!</p>" \
                    "<p>If this is unattended, please contact the support.</p>" % url
            if MODE == "webserver":
                with Job.connect():
                    job = Job.get(Job.id_job == self.id_job)
                    job.status = status
                    job.error = error
                    job.save()
            else:
                self.set_status_standalone(status, error)
        return allowed

    def clear(self):
        """
        Remove job dir
        """
        shutil.rmtree(self.output_dir)

    @staticmethod
    def get_pending_local_number():
        """
        Get number of of jobs running or waiting for a run

        :return: number of jobs
        :rtype: int
        """
        if MODE == "webserver":
            with Job.connect():
                return len(Job.select().where((Job.batch_type == "local") & (Job.status != "success") &
                                              (Job.status != "fail") & (Job.status != "no-match")))
        else:
            return 0

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

    def check_file(self, input_type, should_be_local, max_upload_size_readable):
        """
        Check if file is correct: format, size, valid gzip

        :param input_type: query or target
        :param should_be_local: True if job should be treated locally
        :param max_upload_size_readable: max upload size human readable
        :return: (True if correct, True if error set [for fail], True if should be local)
        """
        if input_type == "target" and self.query is None:
            max_upload_size_readable = self.config.max_upload_size_ava / 1024 / 1024
        with Job.connect():
            my_input = getattr(self, input_type)
            if my_input.get_path().endswith(".gz") and not self.is_gz_file(my_input.get_path()):
                # Check file is correctly gzipped
                self.set_job_status("fail", input_type + " file is not a correct gzip file")
                self.clear()
                return False, True, None
            # Check size:
            file_size = self.get_file_size(my_input.get_path())
            if -1 < (self.config.max_upload_size if (input_type == "query" or self.query is not None)
                     else self.config.max_upload_size_ava) < file_size:
                self.set_job_status("fail",
                                    input_type +
                                    " file exceed size limit of %d Mb (uncompressed)" % max_upload_size_readable)
                self.clear()
                return False, True, None

            if input_type == "align":
                if not hasattr(validators, self.aln_format):
                    self.set_job_status("fail", "Alignment file format not supported")
                    return False, True, None
                if not getattr(validators, self.aln_format)(self.align.get_path()):
                    self.set_job_status("fail", "Alignment file is invalid. Please check your file.")
                    return False, True, None
            elif input_type != "backup":
                if my_input.get_path().endswith(".idx"):
                    if not validators.v_idx(my_input.get_path()):
                        self.set_job_status("fail",
                                            "%s index file is invalid. Please check your file." %
                                            input_type.capitalize())
                        return False, True, None
                if self.config.batch_system_type != "local" and file_size >= getattr(self.config,
                                                                                     "min_%s_size" % input_type):
                    should_be_local = False

        return True, False, should_be_local

    def download_files_with_pending(self, files_to_download, should_be_local, max_upload_size_readable):
        """
        Download files from URLs, with pending (according to the max number of concurrent downloads)

        :param files_to_download: files to download. For each item of the list, it's a list with 2 elements: first one
            is the Fasta object, second one the input type (query or target)
        :type files_to_download: list of list
        :param should_be_local: True if the job should be run locally (according to input file sizes), else False
        :type should_be_local: bool
        :param max_upload_size_readable: Human readable max upload size (to show on errors)
        :type max_upload_size_readable: str
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
                correct = True
                error_set = False
                if MODE == "webserver":
                    allowed = session.ask_for_upload(True)
                else:
                    allowed = True
                while not allowed:
                    time.sleep(15)
                    session = Session.get(s_id=s_id)
                    allowed = session.ask_for_upload(False)
                if allowed:
                    if MODE == "webserver":
                        job.status = "getfiles"
                        job.save()
                    for file, input_type in files_to_download:
                        correct, error_set, finale_path, filename = self._getting_file_from_url(file, input_type)
                        if not correct:
                            break
                        my_input = getattr(self, input_type)
                        my_input.set_path(finale_path)
                        my_input.set_name(filename)
                        correct, error_set, should_be_local = self.check_file(input_type, should_be_local,
                                                                              max_upload_size_readable)
                        if not correct:
                            break

                    if correct and MODE == "webserver" and job.batch_type != "local" and should_be_local \
                            and self.get_pending_local_number() < self.config.max_run_local:
                        job.batch_type = "local"
                        job.save()
                else:
                    correct = False
            except:  # Except all possible exceptions
                traceback.print_exc()
                correct = False
                error_set = False
            if MODE == "webserver":
                session.delete_instance()
            self._after_start(correct, error_set)

    def getting_files(self):
        """
        Get files for the job

        :return:
            * [0] True if getting files succeed, False else
            * [1] If error happenned, True if error already saved for the job, False else (error will be saved later)
            * [2] True if no data must be downloaded (will be downloaded with pending if True)
        :rtype: tuple
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
            correct = True
            error_set = False
            should_be_local = True
            max_upload_size_readable = self.config.max_upload_size / 1024 / 1024  # Set it in Mb
            files_to_download = []
            if self.query is not None:
                if self.query.get_type() == "local":
                    self.query.set_path(self._getting_local_file(self.query, "query"))
                    correct, error_set, should_be_local = self.check_file("query", should_be_local,
                                                                          max_upload_size_readable)
                    if not correct:
                        return False, error_set, True
                elif self._check_url(self.query, ("fasta",) if self.align is None else ("fasta", "idx")):
                    files_to_download.append([self.query, "query"])
                else:
                    return False, True, True
            if correct and self.target is not None:
                if self.target.get_type() == "local":
                    self.target.set_path(self._getting_local_file(self.target, "target"))
                    correct, error_set, should_be_local = self.check_file("target", should_be_local,
                                                                          max_upload_size_readable)
                    if not correct:
                        return False, error_set, True
                elif self._check_url(self.target, ("fasta",) if self.align is None else ("fasta", "idx")):
                    files_to_download.append([self.target, "target"])
                else:
                    return False, True, True
            if correct and self.align is not None:
                if self.align.get_type() == "local":
                    self.align.set_path(self._getting_local_file(self.align, "align"))
                    correct, error_set, should_be_local = self.check_file("align", should_be_local,
                                                                          max_upload_size_readable)
                elif self._check_url(self.align, ("map",)):
                    files_to_download.append([self.align, "align"])
                else:
                    return False, True, True
            if correct and self.backup is not None:
                if self.backup.get_type() == "local":
                    self.backup.set_path(self._getting_local_file(self.backup, "backup"))
                    correct, error_set, should_be_local = self.check_file("backup", should_be_local,
                                                                          max_upload_size_readable)
                elif self._check_url(self.backup, ("backup",)):
                    files_to_download.append([self.backup, "backup"])
                else:
                    return False, True, True

            all_downloaded = True
            if correct:
                if len(files_to_download) > 0:
                    all_downloaded = False
                    thread = threading.Timer(0, self.download_files_with_pending,
                                             kwargs={"files_to_download": files_to_download,
                                                     "should_be_local": should_be_local,
                                                     "max_upload_size_readable": max_upload_size_readable})
                    thread.start()  # Start the execution

                elif correct and MODE == "webserver" and job.batch_type != "local" and should_be_local \
                        and self.get_pending_local_number() < self.config.max_run_local:
                    job.batch_type = "local"
                    job.save()
        return correct, error_set, all_downloaded

    def send_mail_post(self):
        """
        Send mail using POST url (if there is no access to mailer)
        """
        key = Functions.random_string(15)
        key_file = os.path.join(self.config.app_data, self.id_job, ".key")
        with open(key_file, "w") as k_f:
            k_f.write(key)
        data = parse.urlencode({"key": key}).encode()
        req = request.Request(self.config.web_url + "/send-mail/" + self.id_job, data=data)
        resp = request.urlopen(req)
        if resp.getcode() != 200:
            print("Job %s: Send mail failed!" % self.id_job)

    def run_job_in_thread(self, batch_system_type="local"):
        """
        Run a job asynchronously into a new thread

        :param batch_system_type: slurm or sge
        :type batch_system_type: str
        """
        thread = threading.Timer(1, self.run_job, kwargs={"batch_system_type": batch_system_type})
        thread.start()  # Start the execution

    def prepare_data_in_thread(self):
        """
        Prepare data in a new thread
        """
        thread = threading.Timer(1, self.prepare_data)
        thread.start()  # Start the execution

    def prepare_data_cluster(self, batch_system_type):
        """
        Launch of prepare data on a cluster

        :param batch_system_type: slurm or sge
        :type batch_system_type: str
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
                                         batch_system_type=batch_system_type,
                                         command=self.config.cluster_python_exec,
                                         args=args,
                                         log_out=self.logs,
                                         log_err=self.logs)
        if not success and MODE == "webserver" and self.config.send_mail_status:
            self.send_mail_post()
        return success

    def prepare_data_local(self):
        """
        Prepare data locally. On standalone mode, launch job after, if success.
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
                    if self.config.send_mail_status:
                        self.send_mail_post()
                    return False
            uncompressed = None
            if self.target.get_path().endswith(".gz"):
                uncompressed = self.target.get_path()[:-3]
            success, nb_contigs, error = index_file(self.target.get_path(), self.target.get_name(), self.idx_t, uncompressed)
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
                if self.config.send_mail_status:
                    self.send_mail_post()
                return False
            ptime.write(str(round(time.time())) + "\n")
            self.set_job_status("prepared")
            if MODE != "webserver":
                self.run_job("local")
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

        if MODE == "webserver" and self.config.send_mail_status:
            self.send_mail_post()

        return True

    def prepare_dotplot_cluster(self, batch_system_type):
        """
        Prepare data if alignment already done: just index the fasta (if index not given), then parse the alignment

        :param batch_system_type: type of cluster (slurm or sge)
        :type batch_system_type: str
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
                                             batch_system_type=batch_system_type,
                                             command=self.config.cluster_python_exec,
                                             args=args,
                                             log_out=self.logs,
                                             log_err=self.logs)

        if success:
            if self.query is None:
                shutil.copy(self.idx_t, self.idx_q)
            return self._end_of_prepare_dotplot()
        elif MODE == "webserver" and self.config.send_mail_status:
            self.send_mail_post()

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

    def prepare_data(self):
        """
        Launch preparation of data
        """
        if self.align is None:
            if MODE == "webserver":
                with Job.connect():
                    job = Job.get(Job.id_job == self.id_job)
                    if job.batch_type == "local":
                        success = self.prepare_data_local()
                    else:
                        success = self.prepare_data_cluster(job.batch_type)
                    if not success:
                        self._set_analytics_job_status("fail-prepare")
            else:
                self.prepare_data_local()
        else:
            if MODE == "webserver":
                with Job.connect():
                    job = Job.get(Job.id_job == self.id_job)
                    if job.batch_type == "local":
                        success = self.prepare_dotplot_local()
                    else:
                        success = self.prepare_dotplot_cluster(job.batch_type)
                    if success:
                        self._set_analytics_job_status("success")
                    else:
                        self._set_analytics_job_status("fail-all")
            else:
                self.prepare_dotplot_local()

    def run_job(self, batch_system_type):
        """
        Run of a job (mapping step)

        :param batch_system_type: type of cluster (slurm or sge)
        :type batch_system_type: str
        """
        try:
            success = False
            if batch_system_type == "local":
                success = self._launch_local()
            elif batch_system_type in ["slurm", "sge"]:
                success = self._launch_drmaa(batch_system_type)
            if success:
                with Job.connect():
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
                    status = "merging"
                    if MODE == "webserver":
                        job.status = "merging"
                        job.save()
                    else:
                        self.set_status_standalone(status)
                    if self.tool.split_before and self.query is not None:
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
                        shutil.copyfile(self.idx_t, self.idx_q)
                        Path(os.path.join(self.output_dir, ".all-vs-all")).touch()
                    if self.tool.parser is not None:
                        paf_raw = self.paf_raw + ".parsed"
                        getattr(parsers, self.tool.parser)(self.paf_raw, paf_raw)
                        os.remove(self.paf_raw)
                        self.paf_raw = paf_raw
                    sorter = Sorter(self.paf_raw, self.paf)
                    sorter.sort()
                    os.remove(self.paf_raw)
                    if self.target is not None and os.path.exists(self.target.get_path()):
                        os.remove(self.target.get_path())
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
                            if self.config.send_mail_status:
                                self.send_mail_post()

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
        if not self.config.anonymous_analytics:
            return email
        for group, pattern in self.config.analytics_groups:
            if re.match(pattern, email):
                return group
        return ''

    def _save_analytics_data(self):
        """
        Save analytics data into the database
        """
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
                batch_type=job.batch_type,
                job_type="new" if (self.align is None and self.backup is None) else "plot",
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

    def unpack_backup(self):
        """
        Untar backup file
        """
        try:
            with tarfile.open(self.backup.get_path(), "r:*") as tar:
                names = tar.getnames()
                if len(names) != 3:
                    return False
                for name in ["map.paf", "query.idx", "target.idx"]:
                    if name not in names:
                        return False
                tar.extractall(self.output_dir)
                shutil.move(self.paf, self.paf_raw)
                if not validators.paf(self.paf_raw):
                    return False
                target_path = os.path.join(self.output_dir, "target.idx")
                query_path = os.path.join(self.output_dir, "query.idx")
                if not validators.v_idx(target_path) or not validators.v_idx(query_path):
                    return False
                self.align = Fasta(name="map", path=self.paf_raw, type_f="local")
                self.aln_format = "paf"
                with open(os.path.join(self.output_dir, ".align"), "w") as aln:
                    aln.write(self.paf_raw)
                self.target = Fasta(name="target", path=target_path, type_f="local")
                with open(os.path.join(self.output_dir, ".target"), "w") as trgt:
                    trgt.write(target_path)
                self.query = Fasta(name="query", path=query_path, type_f="local")
                with open(os.path.join(self.output_dir, ".query"), "w") as qr:
                    qr.write(query_path)
            os.remove(self.backup.get_path())
            return True
        except:
            traceback.print_exc()
            return False

    def _after_start(self, success, error_set):
        """
        Tasks done after input files downloaded, checked and parsed: if success, set job status to "waiting".
        Else, set job error and send mail.

        :param success: job success
        :type success: bool
        :param error_set: error already set (else, set it now)
        :type error_set: bool
        """
        with Job.connect():
            if MODE == "webserver" and self.config.analytics_enabled:
                self._save_analytics_data()
            if success:
                if self.backup is not None:
                    success = self.unpack_backup()
                    if not success:
                        self.set_job_status("fail", "Backup file is not valid. If it is unattended, please contact the "
                                                    "support.")
                        if MODE == "webserver" and self.config.send_mail_status:
                            self.send_mail()
                        return False
                status = "waiting"
                if MODE == "webserver":
                    job = Job.get(Job.id_job == self.id_job)
                    job.status = status
                    job.save()
                else:
                    self.set_status_standalone(status)
                    self.prepare_data_in_thread()
            else:
                self._set_analytics_job_status("fail-getfiles")
                if not error_set:
                    status = "fail"
                    error = "<p>Error while getting input files. Please contact the support to report the bug.</p>"
                    if MODE == "webserver":
                        job = Job.get(Job.id_job == self.id_job)
                        job.status = status
                        job.error = error
                        job.save()
                    else:
                        self.set_status_standalone(status, error)
                if MODE == "webserver" and self.config.send_mail_status:
                    self.send_mail()

    def start_job(self):
        """
        Start job: download, check and parse input files
        """
        try:
            success, error_set, all_downloaded = self.getting_files()
            if not success or all_downloaded:
                self._after_start(success, error_set)

        except Exception:
            traceback.print_exc()
            error = "<p>An unexpected error has occurred. Please contact the support to report the bug.</p>"
            if MODE == "webserver":
                with Job.connect():
                    job = Job.get(Job.id_job == self.id_job)
                    job.status = "fail"
                    job.error = error
                    job.save()
                    if self.config.send_mail_status:
                        self.send_mail()
            else:
                self.set_status_standalone("fail", error)

    def launch_standalone(self):
        """
        Launch a job in standalone mode (asynchronously in a new thread)
        """
        if not os.path.exists(self.output_dir):
            os.mkdir(self.output_dir)
        self.set_status_standalone("submitted")
        thread = threading.Timer(1, self.start_job)
        thread.start()

    def launch(self):
        """
        Launch a job in webserver mode (asynchronously in a new thread)
        """
        with Job.connect():
            j1 = Job.select().where(Job.id_job == self.id_job)
            if len(j1) > 0:
                print("Old job found without result dir existing: delete it from BDD!")
                for j11 in j1:
                    j11.delete_instance()
            if self.target is not None or self.backup is not None:
                job = Job.create(id_job=self.id_job, email=self.email, batch_type=self.config.batch_system_type,
                                 date_created=datetime.now(), tool=self.tool.name if self.tool is not None else None,
                                 options=self.options)
                job.save()
                if not os.path.exists(self.output_dir):
                    os.mkdir(self.output_dir)
                thread = threading.Timer(1, self.start_job)
                thread.start()
            else:
                job = Job.create(id_job=self.id_job, email=self.email, batch_type=self.config.batch_system_type,
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
                status, error = self.get_status_standalone(True)
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
