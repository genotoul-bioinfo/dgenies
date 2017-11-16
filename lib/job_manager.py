import os
import shutil
import subprocess
import datetime
import threading
from config_reader import AppConfigReader
from pony.orm import db_session, select
from database import db, Job
from lib.Fasta import Fasta
from lib.functions import Functions
import requests
import wget
from jinja2 import Template
import traceback


class JobManager:

    def __init__(self, id_job: str, email: str=None, query: Fasta=None, target: Fasta=None, mailer=None):
        self.id_job = id_job
        self.email = email
        self.query = query
        self.target = target
        config_reader = AppConfigReader()
        # Get configs:
        self.batch_system_type = config_reader.get_batch_system_type()
        self.minimap2 = config_reader.get_minimap2_exec()
        self.threads = config_reader.get_nb_threads()
        self.app_data = config_reader.get_app_data()
        self.web_url = config_reader.get_web_url()
        self.mail_status = config_reader.get_mail_status_sender()
        self.mail_reply = config_reader.get_mail_reply()
        self.mail_org = config_reader.get_mail_org()
        self.do_send = config_reader.get_send_mail_status()
        # Outputs:
        self.output_dir = os.path.join(self.app_data, id_job)
        self.paf = os.path.join(self.output_dir, "map.paf")
        self.paf_raw = os.path.join(self.output_dir, "map_raw.paf")
        self.idx_q = os.path.join(self.output_dir, "query.idx")
        self.idx_t = os.path.join(self.output_dir, "target.idx")
        self.logs = os.path.join(self.output_dir, "logs.txt")
        self.mailer = mailer

    def __check_job_success_local(self):
        if os.path.exists(self.paf):
            if os.path.getsize(self.paf) > 0:
                return "success"
            else:
                return "no-match"
        return "error"

    def check_job_success(self):
        if self.batch_system_type == "local":
            return self.__check_job_success_local()

    def get_mail_content(self, status):
        message = "D-Genies\n\n"
        if status == "success":
            message += "Your job %s was completed successfully!\n\n" % self.id_job
            message += str("Your job {0} is finished. You can see  the results by clicking on the link below:\n"
                           "{1}/result/{0}\n\n").format(self.id_job, self.web_url)
        else:
            message += "Your job %s has failed!\n\n" % self.id_job
            message += "Your job %s has failed. You can try again. " \
                       "If the problem persists, please contact the support.\n\n" % self.id_job
        message += "See you soon on D-Genies,\n"
        message += "The team"

    def get_mail_content_html(self, status):
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "mail_templates", "job_notification.html")) \
                as t_file:
            template = Template(t_file.read())
            return template.render(job_name=self.id_job, status=status, url_base=self.web_url)

    def get_mail_subject(self, status):
        if status == "success" or status == "no-match":
            return "DGenies - Job completed: %s" % self.id_job
        else:
            return "DGenies - Job failed: %s" % self.id_job

    def send_mail(self, status):
        self.mailer.send_mail([self.email], self.get_mail_subject(status), self.get_mail_content(status),
                              self.get_mail_content_html(status))

    @db_session
    def __launch_local(self):
        cmd = ["run_minimap2.sh", self.minimap2, self.threads,
               self.target.get_path() if self.target is not None else "NONE", self.query.get_path(),
               self.query.get_name(), self.target.get_name() if self.target is not None else "NONE", self.paf,
               self.paf_raw, self.output_dir]
        with open(self.logs, "w") as logs:
            p = subprocess.Popen(cmd, stdout=logs, stderr=logs)
        job = Job.get(id_job=self.id_job)
        job.id_process = p.pid
        job.status = "started"
        db.commit()
        p.wait()
        status = self.check_job_success()
        job.status = status
        db.commit()
        return status == "success"

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

    @db_session
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
                job = Job.get(id_job=self.id_job)
                job.status = "error"
                job.error = "<p>File <b>%s</b> downloaded from <b>%s</b> is not a Fasta file!</p>" \
                            "<p>If this is unattended, please contact the support.</p>" % (filename, url)
                db.commit()
        else:
            allowed = False
            job = Job.get(id_job=self.id_job)
            job.status = "error"
            job.error = "<p>Url <b>%s</b> is not a valid URL!</p>" \
                        "<p>If this is unattended, please contact the support.</p>" % (url)
            db.commit()
        return allowed

    @db_session
    def getting_files(self):
        job = Job.get(id_job=self.id_job)
        job.status = "getfiles"
        db.commit()
        correct = True
        if self.query is not None:
            if self.query.get_type() == "local":
                self.query.set_path(self.__getting_local_file(self.query, "query"))
            elif self.__check_url(self.query):
                finale_path, filename = self.__getting_file_from_url(self.query)
                self.query.set_path(finale_path)
                self.query.set_name(filename)
            else:
                correct = False
        if correct and self.target is not None:
            if self.target.get_type() == "local":
                self.target.set_path(self.__getting_local_file(self.target, "target"))
            elif self.__check_url(self.target):
                finale_path, filename = self.__getting_file_from_url(self.target)
                self.target.set_path(finale_path)
                self.target.set_name(filename)
            else:
                correct = False
        return correct

    @db_session
    def start_job(self):
        try:
            success = self.getting_files()
            if success:
                job = Job.get(id_job=self.id_job)
                job.status = "waiting"
                db.commit()
                success = True
                if self.batch_system_type == "local":
                    success = self.__launch_local()
                if success:
                    job = Job.get(id_job=self.id_job)
                    job.status = "indexing"
                    db.commit()
                    query_index = os.path.join(self.output_dir, "query.idx")
                    Functions.index_file(self.query, query_index)
                    target_index = os.path.join(self.output_dir, "target.idx")
                    if self.target is not None:
                        Functions.index_file(self.target, target_index)
                    else:
                        shutil.copyfile(query_index, target_index)
                    job = Job.get(id_job=self.id_job)
                    job.status = "success"
                    db.commit()
        except Exception:
            print(traceback.print_exc())
            job = Job.get(id_job=self.id_job)
            job.status = "error"
            job.error = "<p>An unexpected error has occurred. Please contact the support to report the bug.</p>"
            db.commit()
        if self.do_send:
            job = Job.get(id_job=self.id_job)
            self.send_mail(job.status)

    @db_session
    def launch(self):
        j1 = select(j for j in Job if j.id_job == self.id_job)
        if len(j1) > 0:
            print("Old job found without result dir existing: delete it from BDD!")
            j1.delete()
        if self.query is not None:
            job = Job(id_job=self.id_job, email=self.email, batch_type=self.batch_system_type,
                      date_created=datetime.datetime.now())
            db.commit()
            if not os.path.exists(self.output_dir):
                os.mkdir(self.output_dir)
            thread = threading.Timer(1, self.start_job)
            thread.start()
        else:
            job = Job(id_job=self.id_job, email=self.email, batch_type=self.batch_system_type,
                      date_created=datetime.datetime.now(), status="error")
            db.commit()

    @db_session
    def status(self):
        job = Job.get(id_job=self.id_job)
        if job is not None:
            return job.status, job.error
        else:
            return "unknown", ""
