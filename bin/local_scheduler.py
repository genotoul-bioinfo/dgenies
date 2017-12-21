#!/usr/bin/env python3

import os
import time
import sys
import psutil
import atexit
from datetime import datetime
from tendo import singleton

# Allow only one instance:
me = singleton.SingleInstance()

app_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "srv")
os.environ["PATH"] = os.path.join(app_folder, "bin") + ":" + os.environ["PATH"]
sys.path.insert(0, app_folder)

from database import Job, Session
from config_reader import AppConfigReader
from lib.job_manager import JobManager

config_reader = AppConfigReader()

# Add DRMAA lib in env:
if config_reader.drmaa_lib_path is not None:
    os.environ["DRMAA_LIBRARY_PATH"] = config_reader.drmaa_lib_path
    try:
        import drmaa
        from lib.drmaasession import DrmaaSession
        DRMAA_SESSION = DrmaaSession()
    except ImportError:
        pass

NB_RUN = config_reader.local_nb_runs
NB_PREPARE = config_reader.nb_data_prepare

DEBUG=True


def _printer(*messages):
    if DEBUG:
        print(*messages)


def start_job(id_job, batch_system_type="local"):
    _printer("Start job", id_job)
    job = Job.get(Job.id_job == id_job)
    job.status = "starting"
    job.save()
    job_mng = JobManager(id_job=id_job, email=job.email)
    job_mng.set_inputs_from_res_dir()
    job_mng.run_job_in_thread(batch_system_type)


def get_scheduled_local_jobs():
    all_jobs = []
    jobs = Job.select().where((Job.batch_type == "local") & ((Job.status == "prepared") | (Job.status == "scheduled"))).\
        order_by(Job.date_created)
    for job in jobs:
        all_jobs.append(job.id_job)
        job.status = "scheduled"
        job.save()
    return all_jobs


def get_scheduled_cluster_jobs():
    all_jobs = []
    jobs = Job.select().where((Job.batch_type != "local") & ((Job.status == "prepared") | (Job.status == "scheduled"))).\
        order_by(Job.date_created)
    for job in jobs:
        all_jobs.append({"job_id": job.id_job, "batch_type": job.batch_type})
        job.status = "scheduled"
        job.save()
    return all_jobs


def prepare_job(id_job):
    _printer("Prepare data for job:", id_job)
    job = Job.get(Job.id_job == id_job)
    job.status = "preparing"
    job.save()
    job_mng = JobManager(id_job=id_job, email=job.email)
    job_mng.set_inputs_from_res_dir()
    job_mng.prepare_data_in_thread()


def get_prep_scheduled_jobs():
    jobs = Job.select().where(Job.status == "waiting").order_by(Job.date_created)
    return [j.id_job for j in jobs]


def get_preparing_jobs_nb():
    return len(Job.select().where(Job.status == "preparing"))


def parse_started_jobs():
    jobs_started = []  # Only local jobs
    cluster_jobs_started = []  # Only cluster jobs
    jobs = Job.select().where((Job.status == "started") | (Job.status == "starting") | (Job.status == "merging") |
                              (Job.status == "scheduled-cluster"))
    for job in jobs:
        pid = job.id_process
        if job.batch_type == "local":
            if job.status != "started" or psutil.pid_exists(pid):
                jobs_started.append(job.id_job)
            else:
                print("Job %s (pid: %d) has died!" % (job.id_job, job.id_process))
                job.status = "fail"
                job.error = "<p>Your job has failed for an unexpected reason. Please contact the support.</p>"
                job.save()
                # Todo: send mail about the error
        else:
            if job.status in ["started", "scheduled-cluster"]:
                s = DRMAA_SESSION.session
                status = s.jobStatus(str(job.id_process))
                if status not in [drmaa.JobState.RUNNING, drmaa.JobState.DONE, drmaa.JobState.QUEUED_ACTIVE,
                                  drmaa.JobState.SYSTEM_ON_HOLD, drmaa.JobState.USER_ON_HOLD,
                                  drmaa.JobState.USER_SYSTEM_ON_HOLD]:
                    if job.batch_type == "slurm":
                        os.system("scancel %s" % job.id_process)
                    elif job.batch_type == "sge":
                        os.system("qdel %s" % job.id_process)
                    print("Job %s (id on cluster: %d) has died!" % (job.id_job, job.id_process))
                    job.status = "fail"
                    job.error = "<p>Your job has failed for an unexpected reason. Please contact the support.</p>"
                    job.save()
                    # Todo: send mail about the error
                else:
                    if job.status == "scheduled-cluster" and status == drmaa.JobState.RUNNING:
                        job.status = "started"
                        job.save()
                    cluster_jobs_started.append(job.id_job)
            else:
                cluster_jobs_started.append(job.id_job)
    return jobs_started, cluster_jobs_started


def parse_uploads_asks():
    now = datetime.now()
    # Get allowed:
    all_sessions = Session.select()
    nb_sessions = len(all_sessions)
    _printer("All sessions:", nb_sessions)
    sessions = Session.select().where(Session.allow_upload)
    nb_active_dl = len(sessions)
    _printer("Active_dl:", nb_active_dl)
    for session in sessions:
        if (now - session.last_ping).total_seconds() > 30:
            _printer("Delete 1 active session")
            session.delete_instance()  # We consider the user has left
            nb_active_dl -= 1
    # Get pending:
    sessions = Session.select().where((Session.allow_upload == False) & (Session.position >= 0)).order_by(Session.position)
    _printer("Pending:", len(sessions))
    for session in sessions:
        delay = (now - session.last_ping).total_seconds()
        if delay > 30:
            session.position = -1  # Reset position, the user has probably left
            session.save()
            _printer("Reset 1 session")
        elif nb_active_dl < config_reader.max_concurrent_dl:
            session.allow_upload = True
            session.save()
            nb_active_dl += 1
            _printer("Enable 1 session")
    # Remove old sessions:
    for session in all_sessions:
        delay = (now - session.last_ping).total_seconds()
        if delay > 86400:  # Session has more than 1 day
            session.delete_instance()  # Session has expired
            _printer("Delete 1 outdated session")


@atexit.register
def cleaner():
    if "DRMAA_SESSION" in globals():
        DRMAA_SESSION.exit()


if __name__ == '__main__':

    while True:
        _printer("Check uploads...")
        parse_uploads_asks()
        _printer("")
        _printer("Checking jobs...")
        scheduled_jobs_local = get_scheduled_local_jobs()
        scheduled_jobs_cluster = get_scheduled_cluster_jobs()
        prep_scheduled_jobs = get_prep_scheduled_jobs()
        _printer("Waiting for preparing:", len(prep_scheduled_jobs))
        nb_preparing_jobs = get_preparing_jobs_nb()
        _printer("Preparing:", nb_preparing_jobs)
        _printer("Scheduled:", len(scheduled_jobs_local), "(local),", len(scheduled_jobs_cluster), "(cluster)")
        started_jobs, cluster_started_jobs = parse_started_jobs()
        nb_started = len(started_jobs)
        _printer("Started:", nb_started, "(local),", len(cluster_started_jobs), "(cluster)")
        while len(prep_scheduled_jobs) > 0 and nb_preparing_jobs < NB_PREPARE:
            prepare_job(prep_scheduled_jobs.pop(0))
            nb_preparing_jobs += 1
        while len(scheduled_jobs_local) > 0 and nb_started < NB_RUN:
            start_job(scheduled_jobs_local.pop(0))
            nb_started += 1
        for job in scheduled_jobs_cluster:
            start_job(job["job_id"], job["batch_type"])
        # Wait before return
            _printer("Sleeping...")
        time.sleep(15 if nb_preparing_jobs == 0 else 5)
        _printer("\n")
