import os
import subprocess
import datetime
import threading
from config_reader import AppConfigReader
from pony.orm import db_session
from database import db, Job


class JobManager:

    def __init__(self, id_job, email, fasta_q, fasta_t):
        self.id_job = id_job
        self.email = email
        self.fasta_q = fasta_q
        self.fasta_t = fasta_t
        config_reader = AppConfigReader()
        # Get configs:
        self.batch_system_type = config_reader.get_batch_system_type()
        self.minimap2 = config_reader.get_minimap2_exec()
        self.samtools = config_reader.get_samtools_exec()
        self.threads = config_reader.get_nb_threads()
        self.app_data = config_reader.get_app_data()
        # Outputs:
        self.output_dir = os.path.join(self.app_data, id_job)
        self.paf_raw = os.path.join(self.output_dir, "map_raw.paf")
        self.idx_q = os.path.join(self.output_dir, "query.idx")
        self.idx_t = os.path.join(self.output_dir, "target.idx")
        self.logs = os.path.join(self.output_dir, "logs.err")

    @db_session
    def __launch_local(self):
        cmd = ["run_minimap2.sh", self.minimap2, self.samtools, self.threads, self.fasta_t, self.fasta_q, self.paf_raw]
        with open(self.logs, "w") as logs:
            p = subprocess.Popen(cmd, stdout=logs, stderr=logs)
            pid = p.pid
        job = Job(id_job=self.id_job, email=self.email, id_process=pid, batch_type="local",
                  date_created=datetime.datetime.now())
        db.commit()
        p.wait()

    def launch(self):
        if not os.path.exists(self.output_dir):
            os.mkdir(self.output_dir)
        if self.batch_system_type == "local":
            thread = threading.Timer(1, self.__launch_local)
            thread.start()
