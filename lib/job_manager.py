import os
import shutil
import subprocess
import datetime
import threading
import gzip
import traceback
from config_reader import AppConfigReader
from pony.orm import db_session, select
from database import db, Job
from lib.Fasta import Fasta
from lib.functions import allowed_file
import requests
import wget


class JobManager:

    def __init__(self, id_job: str, email: str=None, query: Fasta=None, target: Fasta=None):
        self.id_job = id_job
        self.email = email
        self.query = query
        self.target = target
        config_reader = AppConfigReader()
        # Get configs:
        self.batch_system_type = config_reader.get_batch_system_type()
        self.minimap2 = config_reader.get_minimap2_exec()
        self.samtools = config_reader.get_samtools_exec()
        self.threads = config_reader.get_nb_threads()
        self.app_data = config_reader.get_app_data()
        # Outputs:
        self.output_dir = os.path.join(self.app_data, id_job)
        self.paf = os.path.join(self.output_dir, "map.paf")
        self.paf_raw = os.path.join(self.output_dir, "map_raw.paf")
        self.idx_q = os.path.join(self.output_dir, "query.idx")
        self.idx_t = os.path.join(self.output_dir, "target.idx")
        self.logs = os.path.join(self.output_dir, "logs.txt")

    @staticmethod
    def _decompress(filename):
        try:
            uncompressed = filename.rsplit('.', 1)[0]
            parts = uncompressed.rsplit("/", 1)
            file_path = parts[0]
            basename = parts[1]
            n = 2
            while os.path.exists(uncompressed):
                uncompressed = "%s/%d_%s" % (file_path, n, basename)
                n += 1
            with open(filename, "rb") as infile, open(uncompressed, "wb") as outfile:
                outfile.write(gzip.decompress(infile.read()))
            os.remove(filename)
            return uncompressed
        except Exception as e:
            print(traceback.format_exc())
            return None

    def __check_job_success_local(self):
        if os.path.exists(self.paf):
            if os.path.getsize(self.paf) > 0:
                if os.path.exists(self.idx_q):
                    if os.path.getsize(self.idx_q) > 0:
                        if os.path.exists(self.idx_t):
                            if os.path.getsize(self.idx_t) > 0:
                                return "success"
        return "error"

    def check_job_success(self):
        if self.batch_system_type == "local":
            return self.__check_job_success_local()

    @db_session
    def __launch_local(self):
        cmd = ["run_minimap2.sh", self.minimap2, self.samtools, self.threads,
               self.target.get_path() if self.target is not None else "NONE", self.query.get_path(),
               self.query.get_name(), self.target.get_name(), self.paf, self.paf_raw, self.output_dir]
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

    def __getting_local_file(self, fasta: Fasta):
        finale_path = os.path.join(self.output_dir, os.path.basename(fasta.get_path()))
        shutil.move(fasta.get_path(), finale_path)
        if finale_path.endswith(".gz"):
            finale_path = self._decompress(finale_path)
        return finale_path

    def __getting_file_from_url(self, fasta: Fasta):
        finale_path = wget.download(fasta.get_path(), self.output_dir, None)
        if finale_path.endswith(".gz"):
            finale_path = self._decompress(finale_path)
        return finale_path

    @db_session
    def __check_url(self, fasta: Fasta):
        filename = requests.head(fasta.get_path(), allow_redirects=True).url.split("/")[-1]
        allowed = allowed_file(filename)
        if not allowed:
            job = Job.get(id_job=self.id_job)
            job.status = "error"
            job.error = "<p>File <b>%s</b> downloaded from <b>%s</b> is not a Fasta file!</p>" \
                        "<p>If this is unattended, please contact the support.</p>" % (filename, fasta.get_path())
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
        if correct:
            job = Job.get(id_job=self.id_job)
            job.status = "waiting"
            db.commit()
            if self.batch_system_type == "local":
                self.__launch_local()

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
            thread = threading.Timer(1, self.getting_files)
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
