import math

from dgenies import MODE, DEBUG

import os
import shutil
import subprocess
from datetime import datetime
import time
import threading
import re
import dgenies.lib.parsers as parsers
import traceback
from pathlib import Path
from dgenies.bin.split_fa import Splitter
from dgenies.bin.index import index_file, Index
from dgenies.bin.filter_contigs import Filter
from dgenies.bin.merge_splitted_chrms import Merger
from dgenies.bin.sort_paf import Sorter
from dgenies.lib.paf import Paf
import json
from dgenies.database import Job
from dgenies.lib.exceptions import DGeniesFastaFileInvalid, DGeniesRunError, DGeniesClusterRunError, \
    DGeniesLocalRunError, DGeniesMissingParserError, DgeniesMissingSubjobsError


class JobManagerExecutionMixin:

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

    def forge_align_command(self, default_out_file=None):
        """
        Forge command line for running alignment

        :params default_out_file: output file to use by default
        :type default_out_file: str
        :return: the command line and the output file that will be used:
            *[0]: the exec file
            *[2]: the command arguments
            *[1]: the output file, can be either the default one, or the one computed from tool command pattern
        :rtype: tuple
        """
        out_file = default_out_file
        if self.is_ava():
            args = re.sub(r"{exe}\s?", "", self.tool.all_vs_all)
        else:
            args = re.sub(r"{exe}\s?", "", self.tool.command_line).replace("{query}", self.get_query_split())
        if ">" in args:
            out_file = self.paf_raw
            args = args[:args.index(">")]
        args = (args.strip()
                   .replace("{target}", self.target.get_path())
                   .replace("{threads}", str(self.tool.threads))
                   .replace("{options}", str(self.options))
                   .replace("{out}", self.paf_raw))
        args = re.sub(r" +", " ", args)
        return self.tool.exec, args, out_file

    def _launch_local(self):
        """
        Launch a job on the current machine
        Raise DGeniesLocalRunError on error
        """
        if MODE == "webserver":
            cmd = ["/usr/bin/time", "-f", "%e %M"]
        else:
            cmd = []

        exe, args, out_file = self.forge_align_command(default_out_file=None)
        cmd += [exe]
        cmd += args.split(" ")
        self.logger.info("{} - Will run: {}".format(self.id_job, " ".join(cmd)))
        with open(self.logs, "a") as logs:
            logs.write("Run {0} ({1}):\n".format(self.tool.label, self.tool.name))
            logs.write("{0}\n".format(" ".join(cmd)))
        if out_file is None:
            with open(self.logs, "a") as logs:
                p = subprocess.Popen(cmd, stdout=logs, stderr=logs)
        else:
            with open(self.logs, "a") as logs, open(out_file, "w") as out:
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
            else:
                self.error = self.search_error()
                raise DGeniesLocalRunError(self.error)

    def check_job_status_slurm(self):
        """
        Check status of a SLURM job run

        :return: True if the job has successfully ended, else False
        """
        status = subprocess.check_output("sacct -p -n --format=state,maxvmsize,elapsed --units=K -j %s.batch" % self.id_process,
                                         shell=True).decode("utf-8").strip("\n")

        status = status.split("|")

        success = status[0] == "COMPLETED"
        if success:
            mem_peak = math.floor(float(status[1] if status[1][-1] != 'K' else status[1][:-1])) # Remove the K letter if needed
            elapsed_full = list(map(int, status[2].split(":")))
            elapsed = elapsed_full[0] * 3600 + elapsed_full[1] * 60 + elapsed_full[2]
            with open(self.logs, "a") as logs:
                logs.write("%s %d\n" % (elapsed, mem_peak))

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
                    logs.write("%s %d\n" % (elapsed, mem_peak))

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

    def _get_runner_config(self, step):
        """
        Get runner config (runner type, memory, thread, walltime)

        :param step: The job step
        :type step: str
        :return: the config:
            * [0]: memory in GB
            * [1]: number of threads
            * [2]: walltime
        :rtype: tuple
        """
        if step == "start":
            # TODO: rework hardcoded memory limits
            memory = self.config.cluster_memory
            if self.is_ava():
                memory = self.config.cluster_memory_ava
                if memory > 32:
                    name, order, contigs, reversed_c, abs_start, c_len = Index.load(self.idx_t, False)
                    if c_len <= 500000000:
                        memory = 32
            if memory > self.tool.max_memory:
                memory = self.tool.max_memory
            return memory, self.tool.threads_cluster, self.config.cluster_walltime_align
        else:  # step == "prepare"
            return 8, 1, self.config.cluster_walltime_prepare

    def launch_to_cluster(self, step, runner_type, command, args, log_out, log_err, scheduled_status):
        """
        Launch a program to the cluster.
        Raise DGeniesClusterRunError on error

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
        :param scheduled_status: status to set when job is scheduled
        :type scheduled_status: str
        """
        import drmaa
        from dgenies.lib.drmaasession import DrmaaSession
        drmaa_session = DrmaaSession()
        s = drmaa_session.session

        # prepare job submission
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

        memory, threads, walltime = self._get_runner_config(step)

        native_specs = self.config.drmaa_native_specs
        if runner_type == "slurm":
            if native_specs == "###DEFAULT###":
                native_specs = "--mem-per-cpu={0} --nodes=1 --mincpus={1} --cpus-per-task={1} --time={2}"
            jt.nativeSpecification = native_specs.format(memory * 1000 // threads, threads, walltime)
        elif runner_type == "sge":
            if native_specs == "###DEFAULT###":
                native_specs = "-l mem={0},h_vmem={0} -pe parallel_smp {1}"
            jt.nativeSpecification = native_specs.format(memory * 1000 // threads, threads)
        jt.workingDirectory = self.output_dir

        # submit job
        self.logger.info("{} - Submit {} job with native specs: {}".format(self.id_job, runner_type, jt.nativeSpecification))
        jobid = s.runJob(jt)
        self.id_process = jobid
        self.logger.info("{} - Job {} submitted".format(self.id_job, jobid))
        # TODO split here into submit_to_cluster -> s (above) and wait_cluster(s) in order to update job status outside
        #  of the function
        self.update_job_status(scheduled_status, jobid)

        # wait for job ending
        retval = s.wait(jobid, drmaa.Session.TIMEOUT_WAIT_FOREVER)
        self.logger.info("{} - Job {} ended".format(self.id_job, jobid))
        # copy cluster logs to job log file
        if log_err != self.logs:
            with open(log_err, 'r') as cluster_log, open(self.logs, 'a') as logs:
                logs.write(cluster_log.read())
        if retval.hasExited and (self.check_job_status_slurm() if runner_type == "slurm" else
        self.check_job_status_sge()):
            self.logger.info("{} - Job {} ended successfully".format(self.id_job, jobid))
            s.deleteJobTemplate(jt)
        else:
            error = self.find_error_in_log(log_err)
            self.logger.info("{} - Job {} ended with error: {}".format(self.id_job, jobid, error))
            s.deleteJobTemplate(jt)
            raise DGeniesClusterRunError(error)

    def _launch_drmaa(self, runner_type):
        """
        Launch the mapping step to a cluster
        Raise DGeniesClusterRunError on error

        :param runner_type: slurm or sge
        :type runner_type: str
        :return: new status:either succeed, no-match or fail
        :rtype: str
        """
        exec, args, out_file = self.forge_align_command(default_out_file=self.logs + ".cluster")
        args = args.split(" ")
        try:
            self.logger.info("{} - Run align files: {} {}".format(self.id_job, self.tool.exec, str(args)))
            with open(self.logs, "a") as logs:
                logs.write("Run {0} ({1}):\n".format(self.tool.label, self.tool.name))
                logs.write("{0} {1}\n".format(self.tool.exec, " ".join(args)))
            self.launch_to_cluster(step="start",
                                   runner_type=runner_type,
                                   command=self.tool.exec,
                                   args=args,
                                   log_out=out_file,
                                   log_err=self.logs + ".cluster",
                                   scheduled_status="scheduled-cluster")
            status = self.check_job_success()
            self.logger.debug("{} - Job {} ends with status: {}".format(self.id_job, self.id_job, status))
            if status == "no-match":
                self._set_analytics_job_status("no-match")
            self.update_job_status(status)
        except DGeniesClusterRunError as e:
            raise e


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

        try:
            self.logger.info("{} - Prepare files: {} {}".format(self.id_job, self.tool.exec, str(args)))
            with open(self.logs, "a") as logs:
                logs.write("Prepare files:\n")
                logs.write("{0} {1}\n".format(self.config.cluster_python_exec, " ".join(args)))
            self.launch_to_cluster(step="prepare",
                                   runner_type=runner_type,
                                   command=self.config.cluster_python_exec,
                                   args=args,
                                   log_out=self.logs + ".cluster",
                                   log_err=self.logs + ".cluster",
                                   scheduled_status="prepare-scheduled")
            status = "prepared"
            # job = Job.get(id_job=self.id_job)
            # job.status = status
            # db.commit()
            self.update_job_status(status)

        except DGeniesClusterRunError as e:
            raise e

    def prepare_align_local(self):
        """
        Prepare align data locally. On standalone mode, launch job after, if success.
        :return: True if job succeed, else False
        :rtype: bool
        """
        with open(self.logs, "a") as logs:
            logs.write("Prepare files\n")
        with open(self.preptime_file, "w") as ptime, Job.connect():
            self.set_job_status("preparing")
            ptime.write(str(round(time.time())) + "\n")
            if self.query is not None:
                fasta_in = self.query.get_path()
                if self.tool.split_before:
                    self.logger.info("{} - Split query file: {}".format(self.id_job, fasta_in))
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
                    self.logger.info("{} - Index query file: {}".format(self.id_job, self.query.get_path()))
                    success, nb_contigs, error = index_file(self.query.get_path(), self.query.get_name(), self.idx_q,
                                                            uncompressed)
                    in_fasta = self.query.get_path()
                    if uncompressed is not None:
                        in_fasta = uncompressed
                if success:
                    self.logger.info("{} - Filter query file: {}".format(self.id_job, self.query.get_path()))
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
                    raise DGeniesFastaFileInvalid("Query", error)
            uncompressed = None
            if self.target.get_path().endswith(".gz"):
                uncompressed = self.target.get_path()[:-3]
            success, nb_contigs, error = index_file(self.target.get_path(), self.target.get_name(), self.idx_t,
                                                    uncompressed)
            if success:
                in_fasta = self.target.get_path()
                if uncompressed is not None:
                    in_fasta = uncompressed
                self.logger.info("{} - Filter target file: {}".format(self.id_job, in_fasta))
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
                raise DGeniesFastaFileInvalid("Target", error)
            ptime.write(str(round(time.time())) + "\n")
            self.set_job_status("prepared")
            if MODE != "webserver":
                self.run_align("local")

    def _end_of_prepare_dotplot(self):
        """
        Tasks done after preparing dot plot data: parse & sort of alignment file
        """
        # Parse alignment file:
        self.logger.info("{} - Parse align file".format(self.id_job))
        if hasattr(parsers, self.aln_format):
            getattr(parsers, self.aln_format)(self.align.get_path(), self.paf_raw)
            os.remove(self.align.get_path())
        elif self.aln_format == "paf":
            shutil.move(self.align.get_path(), self.paf_raw)
        else:
            raise DGeniesMissingParserError(self.aln_format)

        self.set_job_status("started")

        # Sort paf lines:
        self.logger.info("{} - Sort PAF file".format(self.id_job))
        sorter = Sorter(self.paf_raw, self.paf)
        sorter.sort()
        os.remove(self.paf_raw)
        if self.target is not None and os.path.exists(self.target.get_path()) and not \
                self.target.get_path().endswith(".idx"):
            os.remove(self.target.get_path())

        self.align.set_path(self.paf)
        self.set_job_status("success")
        self.send_mail_post_if_allowed()

    def prepare_dotplot_cluster(self, runner_type):
        """
        Prepare data if alignment already done: just index the fasta (if index not given), then parse the alignment
        DGeniesClusterRunError or DGeniesMissingParserError on error

        :param runner_type: type of cluster (slurm or sge)
        :type runner_type: str
        """

        args = [self.config.cluster_prepare_script,
                "-p", self.preptime_file, "--index-only"]

        target_format = os.path.splitext(self.target.get_path())[1][1:]
        all_is_index = target_format == "idx"
        if all_is_index:
            shutil.move(self.target.get_path(), self.idx_t)
            os.remove(os.path.join(self.output_dir, ".target"))
        else:
            args += ["-t", self.target.get_path(),
                     "-m", self.target.get_name()]
        self.logger.info("{} - Target is index: {}".format(self.id_job, all_is_index))

        if self.query is not None:
            query_format = os.path.splitext(self.query.get_path())[1][1:]
            target_is_index = query_format == "idx"
            if target_is_index:
                shutil.move(self.query.get_path(), self.idx_q)
                os.remove(os.path.join(self.output_dir, ".query"))
            else:
                args += ["-q", self.query.get_path(),
                         "-n", self.query.get_name()]
            self.logger.info("{} - Query is index: {}".format(self.id_job, target_is_index))
            all_is_index = all_is_index and target_is_index

        self.logger.info("{} - Must index files: {}".format(self.id_job, not all_is_index))
        if not all_is_index:
            self.logger.info("{} - Index files: {} {}".format(self.id_job, self.config.cluster_python_exec, str(args)))
            try:
                with open(self.logs, "a") as logs:
                    logs.write("Index files:\n")
                    logs.write("{0} {1}\n".format(self.config.cluster_python_exec, " ".join(args)))
                self.launch_to_cluster(step="prepare",
                                       runner_type=runner_type,
                                       command=self.config.cluster_python_exec,
                                       args=args,
                                       log_out=self.logs + ".cluster",
                                       log_err=self.logs + ".cluster",
                                       scheduled_status="prepare-scheduled")

            except (DGeniesClusterRunError, DGeniesMissingParserError) as e:
                raise e

        if self.query is None:
            shutil.copy(self.idx_t, self.idx_q)

        status = "prepared"
        self.update_job_status(status)
        self._end_of_prepare_dotplot()

    def prepare_dotplot_local(self):
        """
        Prepare data if alignment already done: just index the fasta (if index not given), then parse the alignment
        file and sort it.
        Raise DGeniesMissingParserError on error
        """
        self.set_job_status("preparing")
        # Prepare target index:
        target_format = os.path.splitext(self.target.get_path())[1][1:]
        if target_format == "idx":
            shutil.move(self.target.get_path(), self.idx_t)
            os.remove(os.path.join(self.output_dir, ".target"))
        else:
            self.logger.info("{} - Index target file: {}".format(self.id_job, self.target.get_path()))
            with open(self.logs, "a") as logs:
                logs.write("Index target file: {}\n".format(self.target.get_path()))
            index_file(self.target.get_path(), self.target.get_name(), self.idx_t)

        # Prepare query index:
        if self.query is not None:
            query_format = os.path.splitext(self.query.get_path())[1][1:]
            if query_format == "idx":
                shutil.move(self.query.get_path(), self.idx_q)
                os.remove(os.path.join(self.output_dir, ".query"))
            else:
                self.logger.info("{} - Index query file: {}".format(self.id_job, self.query.get_path()))
                with open(self.logs, "a") as logs:
                    logs.write("Index target file: {}\n".format(self.query.get_path()))
                index_file(self.query.get_path(), self.query.get_name(), self.idx_q)
        else:
            shutil.copy(self.idx_t, self.idx_q)

        try:
            self._end_of_prepare_dotplot()
        except DGeniesMissingParserError as e:
            raise e

    def write_jobs(self, jobs):
        """
        Write job description (file paths for roles, tool, options, ...) into a json file for futher steps file storing jobs description
        Document structure follows the message structure obtained from form.
        """
        with open(os.path.join(self.output_dir, ".jobs"), "wt", encoding='utf8') as json_file:
            data = [subjob.as_job_entry() for subjob in jobs]
            json.dump(data, json_file, allow_nan=True)

    def read_jobs(self):
        """
        Read file storing job descriptions (file paths for roles, tool, options, ...)
        Document structure follows the message structure obtained from form.

        :return: list of dict. Each dict is a job is a dict where param:value
        :rtype: list
        """
        with open(os.path.join(self.output_dir, ".jobs"), "rt", encoding='utf8') as json_file:
            data = json.load(json_file)
            return data

    def get_subjob_ids(self):
        """
        Get the subjobs ids if any

        :return:
        :rtype: list of str
        """
        try:
            with open(os.path.join(self.output_dir, ".batch"), "r") as infile:
                return infile.read().splitlines()
        except FileNotFoundError:
            return []

    def prepare_batch(self):
        """
        Prepare batch locally.
        """
        # We get the job list from .jobs file
        self.logger.info("{} - Prepare batch job".format(self.id_job))
        subjobs = self.read_jobs()
        if not subjobs:
            raise DgeniesMissingSubjobsError()
        # We create a queue in order to run jobs sequentially in standalone mode.
        self.set_job_status("preparing")
        job_queue = []
        for sj in subjobs:
            j = type(self)(sj["id_job"], email=self.email, mailer=self.mailer)
            j.set_inputs_from_res_dir()
            j.tool_name = sj["tool"] if "tool" in sj else None
            j.options = sj["options"] if "options" in sj else None
            job_queue.append(j)
        if MODE == "webserver":
            self.set_job_status("started-batch")
            for subjob in job_queue:
                self.logger.info("{} - Run job {}".format(self.id_job, subjob.id_job))
                subjob.set_send_mail(False)
                subjob.launch()
        else:
            self.set_job_status("started-batch")
            for subjob in job_queue:
                self.logger.info("{} - Run job {}".format(self.id_job, subjob.id_job))
                subjob.launch_standalone(sync=True)
            # We get end status for each subjob
            is_success = all(s in ("success", "no-match") for s in map(lambda j: j.get_status_standalone(), job_queue))
            # The batch job succeed if all subjobs succeed
            self.set_job_status("success") if is_success else self.set_job_status("fail")

    def prepare_job(self):
        """
        Launch job preparation (in particular preparing data) according to the job type
        """
        if self.batch is not None:
            # batch mode
            try:
                self.logger.info("{} - Run batch job".format(self.id_job))
                self.prepare_batch()
                self.logger.info("{} - Run batch: Ended".format(self.id_job))

            except DgeniesMissingSubjobsError as e:
                self.logger.error("{} - Run batch: Failed".format(self.id_job))
                self.set_job_status("fail", e.message)
                self._set_analytics_job_status("fail-batch-prepare")
                self.send_mail_post_if_allowed()

        elif self.align is None:
            # new align mode
            try:
                if MODE == "webserver":
                    with Job.connect():
                        job = Job.get(Job.id_job == self.id_job)
                        if job.runner_type == "local":
                            self.logger.info("{} - Run prepare align: local mode".format(self.id_job))
                            self.prepare_align_local()
                        else:
                            self.logger.info("{} - Run prepare align: cluster mode".format(self.id_job))
                            self.prepare_align_cluster(job.runner_type)
                else:
                    self.prepare_align_local()

            except DGeniesClusterRunError as e:
                self.logger.error("{} - Run prepare align: Failed".format(self.id_job))
                error = e.message + "<br/>Please check your input file and try again."
                self.set_job_status("fail", error)
                self._set_analytics_job_status("fail-prepare")
                self.send_mail_post_if_allowed()

            except DGeniesFastaFileInvalid as e:
                self.logger.error("{} - Run prepare align: Failed".format(self.id_job))
                self.set_job_status("fail", e.message)
                self._set_analytics_job_status("fail-prepare")
                self.send_mail_post_if_allowed()

        else:
            # plot mode
            try:
                if MODE == "webserver":
                    with Job.connect():
                        job = Job.get(Job.id_job == self.id_job)
                        if job.runner_type == "local":
                            self.logger.info("{} - Run prepare plot: local mode".format(self.id_job))
                            self.prepare_dotplot_local()
                        else:
                            self.logger.info("{} - Run prepare plot: cluster mode".format(self.id_job))
                            self.prepare_dotplot_cluster(job.runner_type)
                        self._set_analytics_job_status("success")
                else:
                    self.prepare_dotplot_local()

            except DGeniesClusterRunError as e:
                self.logger.error("{} - Run prepare plot: Failed".format(self.id_job))
                error = e.message + "<br/>Please check your input file and try again."
                self.set_job_status("fail", error)
                self._set_analytics_job_status("fail-all")
                self.send_mail_post_if_allowed()

            except DGeniesMissingParserError as e:
                self.logger.error("{} - Run prepare plot: Failed".format(self.id_job))
                self.set_job_status("fail", e.message)
                self._set_analytics_job_status("fail-all")
                self.send_mail_post_if_allowed()

    def refresh_batch_status(self):
        """
        Compute batch status by looking at subjob status
        
        :return: new job status
        :rtype: str
        """
        status_list = []
        for i in self.get_subjob_ids():
            job = type(self)(i)
            status_list.append(job.status())
        is_finished = all(s["status"] in ("success", "fail", "no-match") for s in status_list)
        has_failed = any(s["status"] == "fail" for s in status_list)
        if is_finished:
            status = "fail" if has_failed else "success"
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
                # A batch job does nothing but refresh its state until it ends
                self.set_job_status(self.refresh_batch_status())
            else:
                # We start the 'align' job
                if runner_type == "local":
                    self.logger.info("{} - Run align: local mode".format(self.id_job))
                    self._launch_local()
                elif runner_type in ["slurm", "sge"]:
                    self.logger.info("{} - Run align: cluster mode".format(self.id_job))
                    self._launch_drmaa(runner_type)
                with Job.connect():
                    # We get the stats of the job
                    if MODE == "webserver":
                        job = Job.get(Job.id_job == self.id_job)
                        with open(self.logs, "r") as logs:
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
                    self.logger.info("{} - Starting merging step".format(self.id_job))
                    if MODE == "webserver":
                        job.status = status
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
                        self.logger.debug("{} - No merge needed in ava mode".format(self.id_job))
                        # If ava, we copy target index to query index
                        shutil.copyfile(self.idx_t, self.idx_q)
                        Path(os.path.join(self.output_dir, ".all-vs-all")).touch()
                    if self.tool.parser is not None:
                        # The align file needs to be transformed to paf
                        self.logger.debug("{} - Transform align file to PAF...".format(self.id_job))
                        paf_raw = self.paf_raw + ".parsed"
                        getattr(parsers, self.tool.parser)(self.paf_raw, paf_raw)
                        os.remove(self.paf_raw)
                        self.paf_raw = paf_raw
                        self.logger.debug("{} - Transform align file to PAF: OK".format(self.id_job))
                    # Matches form paf file are sorted by desc. matching size
                    self.logger.info("{} - Sorting PAF file...".format(self.id_job))
                    sorter = Sorter(self.paf_raw, self.paf)
                    sorter.sort()
                    os.remove(self.paf_raw)
                    self.logger.info("{} - Sorting PAF file: OK".format(self.id_job))
                    # Cleanup target
                    if self.target is not None and os.path.exists(self.target.get_path()):
                        os.remove(self.target.get_path())
                    # The job ask to do a sort of contig
                    success = True
                    if os.path.isfile(os.path.join(self.output_dir, ".do-sort")):
                        self.logger.info("{} - Sorting contig files...".format(self.id_job))
                        paf = Paf(paf=self.paf,
                                  idx_q=self.idx_q,
                                  idx_t=self.idx_t,
                                  auto_parse=False)
                        paf.sort()
                        if not paf.parsed:
                            self.logger.info("{} - Run align: Failed".format(self.id_job))
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
                            job.status = status
                            job.save()

                            # Analytics:
                            self._set_analytics_job_status("success")
                            self.send_mail_post_if_allowed()

                        else:
                            self.logger.info("{} - Run align: OK".format(self.id_job))
                            self.set_status_standalone(status)

        except DGeniesRunError as e:
            with Job.connect():
                self.logger.error("{} - Run align: Failed - DGeniesRunError".format(self.id_job))
                status = "fail"
                if MODE == "webserver":
                    job = Job.get(Job.id_job == self.id_job)
                    job.status = status
                    job.error = e.error
                    job.save()
                else:
                    self.set_status_standalone(status, e.error)
                self._set_analytics_job_status("fail-map")
                self.send_mail_post_if_allowed()

        except Exception as e:
            # TODO: avoid catching send mail related exception errors here
            self.logger.error("{} - Run align: Failed".format(self.id_job))
            traceback.print_exc()
            with open(self.logs, 'a') as f:
                f.write(str(e))
                f.write(traceback.format_exc())
            self.set_job_status("fail", "Your job has failed for an unexpected reason. Please contact the support if"
                                        " the problem persists.")
            if MODE == "webserver":
                self._set_analytics_job_status("fail-map-after")
