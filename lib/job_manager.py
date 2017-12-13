import os
import shutil
import subprocess
import datetime
import threading
import re
from config_reader import AppConfigReader
from database import Job
from peewee import DoesNotExist
from lib.Fasta import Fasta
from lib.functions import Functions
import requests
import wget
from jinja2 import Template
import traceback
from pathlib import Path
from urllib import request, parse
from bin.split_fa import Splitter
from bin.merge_splitted_chrms import Merger
from bin.sort_paf import Sorter


class JobManager:

    def __init__(self, id_job: str, email: str=None, query: Fasta=None, target: Fasta=None, mailer=None):
        self.id_job = id_job
        self.email = email
        self.query = query
        self.target = target
        self.error = ""
        self.id_process = "-1"
        # Get configs:
        self.config = AppConfigReader()
        # Outputs:
        self.output_dir = os.path.join(self.config.app_data, id_job)
        self.query_index_split = os.path.join(self.output_dir, "query_split.idx")
        self.paf = os.path.join(self.output_dir, "map.paf")
        self.paf_raw = os.path.join(self.output_dir, "map_raw.paf")
        self.idx_q = os.path.join(self.output_dir, "query.idx")
        self.idx_t = os.path.join(self.output_dir, "target.idx")
        self.logs = os.path.join(self.output_dir, "logs.txt")
        self.mailer = mailer

    def get_query_split(self):
        query_split = os.path.join(self.output_dir, "split_" + os.path.basename(self.query.get_path()))
        if query_split.endswith(".gz"):
            return query_split[:-3]
        return query_split

    def set_inputs_from_res_dir(self):
        res_dir = os.path.join(self.config.app_data, self.id_job)
        query_file = os.path.join(res_dir, ".query")
        if os.path.exists(query_file):
            with open(query_file) as q_f:
                file_path = q_f.readline()
                self.query = Fasta(
                    name=os.path.splitext(os.path.basename(file_path.replace(".gz", "")).split("_", 1)[1])[0],
                    path=file_path,
                    type_f="local"
                )
        target_file = os.path.join(res_dir, ".target")
        if os.path.exists(target_file):
            with open(target_file) as t_f:
                file_path = t_f.readline()
                self.target = Fasta(
                    name=os.path.splitext(os.path.basename(file_path.replace(".gz", "")).split("_", 1)[1])[0],
                    path=file_path,
                    type_f="local"
                )

    def check_job_success(self):
        if os.path.exists(self.paf_raw):
            if os.path.getsize(self.paf_raw) > 0:
                return "success"
            else:
                return "no-match"
        return "fail"

    def get_mail_content(self, status):
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
        message += "Sequences compared in this analysis:\n"
        if self.query is not None:
            message += "Target: %s\nQuery: %s\n\n" % (self.target.get_name(), self.query.get_name())
        else:
            message += "Target: %s\n\n" % self.target.get_name()
        message += "See you soon on D-Genies,\n"
        message += "The team"
        return message

    def get_mail_content_html(self, status):
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "mail_templates", "job_notification.html"))\
                as t_file:
            template = Template(t_file.read())
            return template.render(job_name=self.id_job, status=status, url_base=self.config.web_url,
                                   query_name=self.query.get_name() if self.query is not None else "",
                                   target_name=self.target.get_name(),
                                   error=self.error)

    def get_mail_subject(self, status):
        if status == "success" or status == "no-match":
            return "DGenies - Job completed: %s" % self.id_job
        else:
            return "DGenies - Job failed: %s" % self.id_job

    def send_mail(self):
        # Retrieve infos:
        job = Job.get(Job.id_job == self.id_job)
        if self.email is None:
            self.email = job.email
        status = job.status
        self.error = job.error

        # Send:
        self.mailer.send_mail([self.email], self.get_mail_subject(status), self.get_mail_content(status),
                              self.get_mail_content_html(status))

    def search_error(self):
        logs = os.path.join(self.output_dir, "logs.txt")
        if os.path.exists(logs):
            lines = subprocess.check_output(['tail', '-2', logs]).decode("utf-8").split("\n")
            if re.match(r"\[morecore] \d+ bytes requested but not available.", lines[1]) or \
                    re.match(r"\[morecore] \d+ bytes requested but not available.", lines[1]) or \
                    re.match(r"\[morecore] insufficient memory", lines[0]) or \
                    re.match(r"\[morecore] insufficient memory", lines[1]):
                return "Your job #ID# has failed because of memory limit exceeded. May be your sequences are too big?" \
                       "<br/>You can contact the support for more information."
        return "Your job #ID# has failed. You can try again.<br/>If the problem persists, please contact the support."

    def __launch_local(self):
        cmd = ["run_minimap2.sh", self.config.minimap2_exec, self.config.nb_threads, self.target.get_path(),
               self.get_query_split() if self.query is not None else "NONE", self.paf_raw]
        with open(self.logs, "w") as logs:
            p = subprocess.Popen(cmd, stdout=logs, stderr=logs)
        job = Job.get(Job.id_job == self.id_job)
        job.id_process = p.pid
        job.status = "started"
        job.save()
        p.wait()
        if p.returncode == 0:
            status = self.check_job_success()
            job.status = status
            job.save()
            return status == "success"
        job.status = "fail"
        self.error = self.search_error()
        job.error = self.error
        job.save()
        return False

    def check_job_status_slurm(self):
        """
        Check status of a SLURM job run
        :return: True if the job has successfully ended
        """
        status = subprocess.check_output("sacct --format=state -j %s | tail -n3" % self.id_process, shell=True)\
            .decode("utf-8").strip("\n")

        status = status.split("\n")

        success = True
        for statu in status:
            if statu.replace(" ", "") != "COMPLETED":
                success = False
                break

        return success

    def check_job_status_sge(self):
        """
        Check status of a SGE job run
        :return: True if the job jas successfully ended
        """
        status = subprocess.check_output("qacct -j %s | grep 'failed' | tr -s ' ' | cut -d' ' -f2" % self.id_process,
                                         shell=True).decode("utf-8").strip("\n")

        return status == "0"

    def update_job_status(self, status, id_process=None):
        job = Job.get(Job.id_job == self.id_job)
        job.status = status
        if id_process is not None:
            job.id_process = id_process
        job.save()

    def __launch_drmaa(self, batch_system_type):
        import drmaa
        from lib.drmaasession import DrmaaSession
        drmaa_session = DrmaaSession()

        s = drmaa_session.session
        jt = s.createJobTemplate()
        jt.remoteCommand = "run_minimap2.sh"
        jt.args = [self.config.minimap2_cluster_exec, self.config.nb_threads, self.target.get_path(),
                   self.get_query_split() if self.query is not None else "NONE", self.paf_raw]
        jt.joinFiles = False

        native_specs = self.config.drmaa_native_specs
        if batch_system_type == "slurm":
            if native_specs == "###DEFAULT###":
                native_specs = "--mem-per-cpu={0} --ntasks={1} --time={2}"
            jt.nativeSpecification = native_specs.format(8000, 4, "01:00:00")
        else:
            if native_specs == "###DEFAULT###":
                native_specs = "-l mem={0},h_vmem={0} -pe parallel_smp {1}"
            jt.nativeSpecification = native_specs.format(8000, 4)
        jt.workingDirectory = self.output_dir
        jobid = s.runJob(jt)
        self.id_process = jobid

        self.update_job_status("scheduled-cluster", jobid)

        retval = s.wait(jobid, drmaa.Session.TIMEOUT_WAIT_FOREVER)
        if retval.hasExited and (self.check_job_status_slurm() if batch_system_type == "slurm" else
                                 self.check_job_status_sge()):
            status = self.check_job_success()
            # job = Job.get(id_job=self.id_job)
            # job.status = status
            # db.commit()
            self.update_job_status(status)
            s.deleteJobTemplate(jt)
            return status == "success"
        self.update_job_status("fail")
        s.deleteJobTemplate(jt)
        return False

    def __getting_local_file(self, fasta: Fasta, type_f):
        finale_path = os.path.join(self.output_dir, type_f + "_" + os.path.basename(fasta.get_path()))
        shutil.move(fasta.get_path(), finale_path)
        with open(os.path.join(self.output_dir, "." + type_f), "w") as save_file:
            save_file.write(finale_path)
        return finale_path

    def __getting_file_from_url(self, fasta: Fasta, type_f):
        dl_path = wget.download(fasta.get_path(), self.output_dir, None)
        filename = os.path.basename(dl_path)
        name = os.path.splitext(filename.replace(".gz", ""))[0]
        finale_path = os.path.join(self.output_dir, type_f + "_" + filename)
        shutil.move(dl_path, finale_path)
        with open(os.path.join(self.output_dir, "." + type_f), "w") as save_file:
            save_file.write(finale_path)
        return finale_path, name

    def __check_url(self, fasta: Fasta):
        url = fasta.get_path()
        if url.startswith("http://") or url.startswith("https://"):
            filename = requests.head(url, allow_redirects=True).url.split("/")[-1]
        elif url.startswith("ftp://"):
            filename = url.split("/")[-1]
        else:
            filename = None
        if filename is not None:
            allowed = Functions.allowed_file(filename)
            if not allowed:
                job = Job.get(Job.id_job == self.id_job)
                job.status = "fail"
                job.error = "<p>File <b>%s</b> downloaded from <b>%s</b> is not a Fasta file!</p>" \
                            "<p>If this is unattended, please contact the support.</p>" % (filename, url)
                job.save()
        else:
            allowed = False
            job = Job.get(Job.id_job == self.id_job)
            job.status = "fail"
            job.error = "<p>Url <b>%s</b> is not a valid URL!</p>" \
                        "<p>If this is unattended, please contact the support.</p>" % (url)
            job.save()
        return allowed

    def getting_files(self):
        job = Job.get(Job.id_job == self.id_job)
        job.status = "getfiles"
        job.save()
        correct = True
        if self.query is not None:
            if self.query.get_type() == "local":
                self.query.set_path(self.__getting_local_file(self.query, "query"))
            elif self.__check_url(self.query):
                finale_path, filename = self.__getting_file_from_url(self.query, "query")
                self.query.set_path(finale_path)
                self.query.set_name(filename)
            else:
                correct = False
        if correct and self.target is not None:
            if self.target.get_type() == "local":
                self.target.set_path(self.__getting_local_file(self.target, "target"))
            elif self.__check_url(self.target):
                finale_path, filename = self.__getting_file_from_url(self.target, "target")
                self.target.set_path(finale_path)
                self.target.set_name(filename)
            else:
                correct = False
        return correct

    def send_mail_post(self):
        """
        Send mail using POST url (we have no access to mailer)
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
        thread = threading.Timer(1, self.run_job, kwargs={"batch_system_type": batch_system_type})
        thread.start()  # Start the execution

    def prepare_data_in_thread(self):
        thread = threading.Timer(1, self.prepare_data)
        thread.start()  # Start the execution

    def prepare_data(self):
        job = Job.get(Job.id_job == self.id_job)
        job.status = "preparing"
        job.save()
        error_tail = "Please check your input file and try again."
        if self.query is not None:
            with open(os.path.join(self.output_dir, "logs.txt"), "w") as logs:
                logs.write(self.query.get_path())
            fasta_in = self.query.get_path()
            splitter = Splitter(input_f=fasta_in, name_f=self.query.get_name(), output_f=self.get_query_split(),
                                query_index=self.query_index_split)
            if not splitter.split():
                job.status = "fail"
                job.error = "<br/>".join(["Query fasta file is not valid!", error_tail])
                job.save()
                if self.config.send_mail_status:
                    self.send_mail_post()
                return False
        if not Functions.index_file(self.target, self.idx_t):
            job.status = "fail"
            job.error = "<br/>".join(["Target fasta file is not valid!", error_tail])
            job.save()
            if self.config.send_mail_status:
                self.send_mail_post()
            return False
        job.status = "prepared"
        job.save()

    def run_job(self, batch_system_type):
        success = False
        if batch_system_type == "local":
            success = self.__launch_local()
        elif batch_system_type in ["slurm", "sge"]:
            success = self.__launch_drmaa(batch_system_type)
        if success:
            job = Job.get(Job.id_job == self.id_job)
            job.status = "merging"
            job.save()
            if self.query is not None:
                paf_raw = self.paf_raw + ".split"
                os.remove(self.get_query_split())
                merger = Merger(self.paf_raw, paf_raw, self.query_index_split,
                                self.idx_q)
                merger.merge()
                os.remove(self.paf_raw)
                os.remove(self.query_index_split)
                self.paf_raw = paf_raw
            else:
                shutil.copyfile(self.idx_t, self.idx_q)
                Path(os.path.join(self.output_dir, ".all-vs-all")).touch()
            sorter = Sorter(self.paf_raw, self.paf)
            sorter.sort()
            os.remove(self.paf_raw)
            if self.target is not None and os.path.exists(self.target.get_path()):
                os.remove(self.target.get_path())
            job = Job.get(Job.id_job == self.id_job)
            job.status = "success"
            job.save()
        if self.config.send_mail_status:
            self.send_mail_post()

    def start_job(self):
        try:
            success = self.getting_files()
            if success:
                job = Job.get(Job.id_job == self.id_job)
                job.status = "waiting"
                job.save()
            else:
                job = Job.get(Job.id_job == self.id_job)
                job.status = "fail"
                job.error = "<p>Error while getting input files. Please contact the support to report the bug.</p>"
                job.save()
                if self.config.send_mail_status:
                    self.send_mail()

        except Exception:
            print(traceback.print_exc())
            job = Job.get(Job.id_job == self.id_job)
            job.status = "fail"
            job.error = "<p>An unexpected error has occurred. Please contact the support to report the bug.</p>"
            job.save()
            if self.config.send_mail_status:
                self.send_mail()

    def launch(self):
        j1 = Job.select().where(Job.id_job == self.id_job)
        if len(j1) > 0:
            print("Old job found without result dir existing: delete it from BDD!")
            for j11 in j1:
                j11.delete_instance()
        if self.target is not None:
            job = Job.create(id_job=self.id_job, email=self.email, batch_type=self.config.batch_system_type,
                             date_created=datetime.datetime.now())
            job.save()
            if not os.path.exists(self.output_dir):
                os.mkdir(self.output_dir)
            thread = threading.Timer(1, self.start_job)
            thread.start()
        else:
            job = Job.create(id_job=self.id_job, email=self.email, batch_type=self.config.batch_system_type,
                             date_created=datetime.datetime.now(), status="fail")
            job.save()

    def status(self):
        try:
            job = Job.get(Job.id_job == self.id_job)
            return job.status, job.error
        except DoesNotExist:
            return "unknown", ""
