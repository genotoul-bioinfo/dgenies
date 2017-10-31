import os
import subprocess
import datetime
import threading
import gzip
import urllib.request
import traceback
from config_reader import AppConfigReader
from pony.orm import db_session, select
from database import db, Job


class JobManager:

    def __init__(self, id_job, email=None, fasta_q=None, fasta_t=None, query_name=None, target_name=None):
        self.id_job = id_job
        self.email = email
        self.fasta_q = fasta_q if (fasta_q is None or not fasta_q.endswith(".gz")) else self._decompress(fasta_q)
        self.fasta_t = fasta_t if (fasta_t is None or not fasta_t.endswith(".gz")) else self._decompress(fasta_t)
        self.query = query_name
        self.target = target_name
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
               self.fasta_t if self.fasta_t is not None else "NONE", self.fasta_q, self.query,
               self.target, self.paf, self.paf_raw, self.output_dir]
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

    @db_session
    def launch(self):
        j1 = select(j for j in Job if j.id_job == self.id_job)
        if len(j1) > 0:
            print("Old job found without result dir existing: delete it from BDD!")
            j1.delete()
        if self.fasta_q is not None:
            job = Job(id_job=self.id_job, email=self.email, batch_type=self.batch_system_type,
                      date_created=datetime.datetime.now())
            db.commit()
            if not os.path.exists(self.output_dir):
                os.mkdir(self.output_dir)
            if self.batch_system_type == "local":
                thread = threading.Timer(1, self.__launch_local)
                thread.start()
        else:
            job = Job(id_job=self.id_job, email=self.email, batch_type=self.batch_system_type,
                      date_created=datetime.datetime.now(), status="error")
            db.commit()

    @db_session
    def status(self):
        job = Job.get(id_job=self.id_job)
        if job is not None:
            return job.status
        else:
            return "unknown"
