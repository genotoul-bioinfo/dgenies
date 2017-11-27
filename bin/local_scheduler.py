#!/usr/bin/env python3

import os
import threading
import time
import sys
import psutil
from pony.orm import db_session, select
from tendo import singleton

# Allow only one instance:
me = singleton.SingleInstance()

app_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "srv")
os.environ["PATH"] = os.path.join(app_folder, "bin") + ":" + os.environ["PATH"]
sys.path.insert(0, app_folder)

from database import Job, db
from config_reader import AppConfigReader
from lib.job_manager import JobManager

config_reader = AppConfigReader()
NB_RUN = config_reader.get_local_nb_runs()


@db_session
def start_job(id_job):
    print("Start job", id_job)
    job = Job.get(id_job=id_job)
    job.status = "starting"
    db.commit()
    job_mng = JobManager(id_job=id_job, email=job.email)
    job_mng.set_inputs_from_res_dir()
    job_mng.run_job_in_thread()
    # thread = threading.Timer(1, job_mng.start_job, kwargs={"batch_system_type": "local"})
    # thread.daemon = True  # Daemonize thread
    # thread.start()  # Start the execution


@db_session
def get_scheduled_jobs():
    all_jobs = []
    jobs = select(j for j in Job if j.batch_type == "local" and (j.status == "waiting" or j.status == "scheduled")).\
        sort_by(Job.date_created)
    for job in jobs:
        all_jobs.append(job.id_job)
        job.status = "scheduled"
    db.commit()
    return all_jobs


@db_session
def parse_started_jobs():
    jobs_started = []
    jobs = select(j for j in Job if j.batch_type == "local" and j.status == "started" or j.status == "starting"
                  or j.status == "indexing")
    for job in jobs:
        pid = job.id_process
        if job.status != "started" or psutil.pid_exists(pid):
            jobs_started.append(job.id_job)
        else:
            print("Job %s (pid: %d) has died!" % (job.id_job, job.id_process))
            job.status = "fail"
            job.error = "<p>Your job has failed for an unexpected reason. Please contact the support.</p>"
            db.commit()
            # Todo: send mail about the error
    return jobs_started


if __name__ == '__main__':
    while True:
        print("Checking jobs...")
        scheduled_jobs = get_scheduled_jobs()
        print("Scheduled:", len(scheduled_jobs))
        started_jobs = parse_started_jobs()
        nb_started = len(started_jobs)
        print("Started:", nb_started)
        while len(scheduled_jobs) > 0 and nb_started < NB_RUN:
            start_job(scheduled_jobs.pop(0))
            nb_started += 1

        # Wait before return
        print("Sleeping...")
        time.sleep(15)
