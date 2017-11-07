import os
import shutil
import subprocess
import datetime
import threading
import gzip
import io
from config_reader import AppConfigReader
from pony.orm import db_session, select
from database import db, Job
from lib.Fasta import Fasta
from lib.functions import Functions
import requests
import wget
from jinja2 import Template
from flask_mail import Message


class JobManager:

    def __init__(self, id_job: str, email: str=None, query: Fasta=None, target: Fasta=None, mailer: "Mail"=None):
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
        return "error"

    def check_job_success(self):
        if self.batch_system_type == "local":
            return self.__check_job_success_local()

    def get_mail_content(self):
        message = "D-Genies\n\n"
        if self.status == "success":
            message += "Your job %s has successfully ended!\n\n" % self.id_job
            message += str("Your job {0} is finished. You can see  the results by clicking on the link below:\n"
                           "{1}/results/{0}\n\n").format(self.id_job, self.web_url)
        else:
            message += "Your job %s has failed!\n\n" % self.id_job
            message += "Your job %s has failed. If the problem persists, please contact the support.\n\n" % self.id_job
        message += "See you soon on D-Genies,\n"
        message += "The team"

    def get_mail_content_html(self):
        template_str = """<h1>D-Genies</h1>
<h3>{% if status == "success" %}Your job {{ job_name }} has successfully ended!{% else %}Your job {{ job_name }} has failed{% endif %}</h3>
<p>Hi,</p>
{% if status == "success" %}
<p>Your job {{ job_name }} is finished. You can <a href="{{ url_base }}/results/{{ job_name }}">click here</a> to see results.</p>
{% else %}
<p>Your job {{ job_name }} has failed. If the problem persists, please contact the support.</p>
{% endif %}
<p>See you soon on D-Genies,</p>
<p>The team</p>
        """
        template = Template(template_str)
        return template.render(job_name=self.id_job, status=self.status, url_base=self.web_url)

    def get_mail_subject(self):
        if self.status == "success":
            return "DGenies - Job %s finished" % self.id_job
        else:
            return "DGenies - Job %s failed" % self.id_job

    def send_mail(self):
        msg = Message(
            subject=self.get_mail_subject(),
            recipients=[self.email],
            html=self.get_mail_content_html(),
            body=self.get_mail_content(),
            sender=(self.mail_org, self.mail_status) if self.mail_org is not None else self.mail_status,
            reply_to=self.mail_reply
        )
        self.mailer.send(msg)

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

    def __getting_local_file(self, fasta: Fasta):
        finale_path = os.path.join(self.output_dir, os.path.basename(fasta.get_path()))
        shutil.move(fasta.get_path(), finale_path)
        return finale_path

    def __getting_file_from_url(self, fasta: Fasta):
        finale_path = wget.download(fasta.get_path(), self.output_dir, None)
        return finale_path

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
                self.query.set_path(self.__getting_local_file(self.query))
            elif self.__check_url(self.query):
                finale_path = self.__getting_file_from_url(self.query)
                filename = os.path.splitext(os.path.basename(finale_path).replace(".gz", ""))[0]
                self.query.set_path(finale_path)
                self.query.set_name(filename)
            else:
                correct = False
        if correct and self.target is not None:
            if self.target.get_type() == "local":
                self.target.set_path(self.__getting_local_file(self.target))
            elif self.__check_url(self.target):
                finale_path = self.__getting_file_from_url(self.target)
                filename = os.path.splitext(os.path.basename(finale_path).replace(".gz", ""))[0]
                self.target.set_path(finale_path)
                self.target.set_name(filename)
            else:
                correct = False
        return correct

    @db_session
    def start_job(self):
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
                self.index_file(self.query, query_index)
                target_index = os.path.join(self.output_dir, "target.idx")
                if self.target is not None:
                    self.index_file(self.target, target_index)
                else:
                    shutil.copyfile(query_index, target_index)
                job = Job.get(id_job=self.id_job)
                job.status = "success"
                db.commit()
        if self.do_send:
            self.send_mail()

    @staticmethod
    def index_file(fasta: Fasta, out):
        compressed = fasta.get_path().endswith(".gz")
        with (gzip.open(fasta.get_path()) if compressed else open(fasta.get_path())) as in_file, \
                open(out, "w") as out_file:
            out_file.write(fasta.get_name() + "\n")
            with (io.TextIOWrapper(in_file) if compressed else in_file) as fasta:
                contig = None
                len_c = 0
                for line in fasta:
                    line = line.strip("\n")
                    if line.startswith(">"):
                        if contig is not None:
                            out_file.write("%s\t%d\n" % (contig, len_c))
                        contig = line[1:].split(" ")[0]
                        len_c = 0
                    elif len(line) > 0:
                        len_c += len(line)
                if contig is not None and len_c > 0:
                    out_file.write("%s\t%d\n" % (contig, len_c))

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
