#!/usr/bin/env python3

import os
import time
import psutil
import atexit
from datetime import datetime
from tendo import singleton
import argparse

from dgenies.database import Job, Session
from dgenies.config_reader import AppConfigReader
from dgenies.lib.job_manager import JobManager

# Allow only one instance:
me = singleton.SingleInstance()

config_reader = AppConfigReader()

# Add DRMAA lib in env:
if config_reader.drmaa_lib_path is not None:
    os.environ["DRMAA_LIBRARY_PATH"] = config_reader.drmaa_lib_path
    try:
        import drmaa
        from dgenies.lib.drmaasession import DrmaaSession
        DRMAA_SESSION = DrmaaSession()
    except ImportError:
        pass

NB_RUN = config_reader.local_nb_runs
NB_PREPARE = config_reader.nb_data_prepare

DEBUG = config_reader.debug

LOG_FILE = "stdout"


def _printer(*messages):
    if DEBUG:
        if LOG_FILE == "stdout":
            print(*messages)
        else:
            with open(LOG_FILE, "a") as log_f:
                print(*messages, file=log_f)


def start_job(id_job, batch_system_type="local"):
    _printer("Start job", id_job)
    job = Job(id_job)
    job.change_status("starting")
    job_mng = JobManager(job=job)
    job_mng.set_inputs_from_res_dir()
    job_mng.run_job_in_thread(batch_system_type)


def get_scheduled_jobs():
    local_jobs = []
    cluster_jobs = []
    jobs = Job.get_by_statuses(["prepared", "scheduled"])
    jobs = Job.sort_jobs(jobs, "date_created")
    for job in jobs:
        if job.batch_type == "local":
            local_jobs.append(job)
        else:
            cluster_jobs.append(job)
        if job.status != "scheduled":
            job.change_status("scheduled")
    return local_jobs, cluster_jobs


def prepare_job(id_job):
    _printer("Prepare data for job:", id_job)
    job = Job(id_job)
    job.change_status("preparing")
    job_mng = JobManager(job=job)
    job_mng.set_inputs_from_res_dir()
    job_mng.prepare_data_in_thread()


def get_prep_scheduled_jobs():
    jobs = Job.sort_jobs(Job.get_by_status("waiting"), "date_created")
    return jobs


def get_preparing_jobs_nb():
    return len(Job.get_by_status("preparing"))


def get_preparing_jobs_cluster_nb():
    return len(Job.get_by_status("preparing-cluster")), \
           len(Job.get_by_status("prepare-scheduled"))


def parse_started_jobs():
    jobs_started = []  # Only local jobs
    cluster_jobs_started = []  # Only cluster jobs
    jobs = Job.get_by_statuses(["started", "starting", "merging", "scheduled-cluster", "prepare-scheduled",
                                "prepare-cluster"])
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
            if job.status in ["started", "scheduled-cluster", "prepare-scheduled", "preparing-cluster"]:
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
                        job.change_status("started")
                        cluster_jobs_started.append(job.id_job)
                    elif job.status == "prepare-scheduled" and status == drmaa.JobState.RUNNING:
                        job.change_status("preparing-cluster")
            else:
                cluster_jobs_started.append(job.id_job)
    return jobs_started, cluster_jobs_started


def parse_uploads_asks():
    now = datetime.now()
    # Get allowed:
    sessions = Session.get_by_status("active")
    nb_active_dl = len(sessions)
    _printer("Active_dl:", nb_active_dl)
    for session in sessions:
        if not session.keep_active and (now - session.last_ping).total_seconds() > 30:
            _printer("Delete 1 active session:", session.s_id)
            session.remove()  # We consider the user has left
            nb_active_dl -= 1
    # Get pending:
    sessions = Session.sort_sessions(Session.get_by_status("pending"), "position")
    _printer("Pending:", len(sessions))
    for session in sessions:
        delay = (now - session.last_ping).total_seconds()
        if delay > 30:
            session.reset()  # Reset position, the user has probably left
            _printer("Reset 1 session:", session.s_id)
        elif nb_active_dl < config_reader.max_concurrent_dl:
            session.enable()
            nb_active_dl += 1
            _printer("Enable 1 session:", session.s_id)
    # Remove old sessions:
    all_sessions = Session.all()
    nb_sessions = len(all_sessions)
    _printer("All sessions:", nb_sessions)
    for session in all_sessions:
        delay = (now - session.last_ping).total_seconds()
        if delay > 86400:  # Session has more than 1 day
            _printer("Delete 1 outdated session:", session.s_id)
            session.remove()  # Session has expired


@atexit.register
def cleaner():
    if "DRMAA_SESSION" in globals():
        DRMAA_SESSION.exit()


def parse_args():
    global DEBUG, LOG_FILE

    parser = argparse.ArgumentParser(description="Start local scheduler")
    parser.add_argument('-d', '--debug', type=str, required=False, help="Set to True to enable debug")
    parser.add_argument('-l', '--log-dir', type=str, required=False, help="Folder into store logs")
    args = parser.parse_args()

    if args.debug is not None:
        if args.debug.lower() == "true" or args.debug.lower == "1":
            DEBUG = True
        elif args.debug.lower() == "false" or args.debug.lower == "0":
            DEBUG = False
        else:
            raise Exception("Invalid value for debug: %s (valid values: True, False)" % args.debug)

    if args.log_dir is not None:
        log_dir = args.log_dir
    else:
        log_dir = config_reader.log_dir

    if DEBUG:
        if log_dir == "stdout":
            LOG_FILE = "stdout"
        else:
            LOG_FILE = os.path.join(config_reader.log_dir, "local_scheduler.log")


def move_job_to_cluster(id_job):
    job = Job(id_job)
    job.batch_type = config_reader.batch_system_type
    job.save()


if __name__ == '__main__':
    parse_args()

    while True:
        _printer("Check uploads...")
        parse_uploads_asks()
        _printer("")
        _printer("Checking jobs...")
        scheduled_jobs_local, scheduled_jobs_cluster = get_scheduled_jobs()
        prep_scheduled_jobs = get_prep_scheduled_jobs()
        _printer("Waiting for preparing:", len(prep_scheduled_jobs))
        nb_preparing_jobs = get_preparing_jobs_nb()
        nb_preparing_jobs_cluster = get_preparing_jobs_cluster_nb()
        _printer("Preparing:", nb_preparing_jobs, "(local)", "".join([str(nb_preparing_jobs_cluster[0]),
                 "[", str(nb_preparing_jobs_cluster[1]), "]"]), "(cluster)")
        _printer("Scheduled:", len(scheduled_jobs_local), "(local),", len(scheduled_jobs_cluster), "(cluster)")
        started_jobs, cluster_started_jobs = parse_started_jobs()
        nb_started = len(started_jobs)
        _printer("Started:", nb_started, "(local),", len(cluster_started_jobs), "(cluster)")
        nj = 0
        local_waiting_jobs = []
        while nj < len(prep_scheduled_jobs):
            job = prep_scheduled_jobs[nj]
            job_batch_type = job.batch_type
            if nb_preparing_jobs < NB_PREPARE or job_batch_type != "local":
                prepare_job(job.id_job)
                if job_batch_type == "local":
                    nb_preparing_jobs += 1
                del prep_scheduled_jobs[nj]
            else:
                if job_batch_type == "local":
                    local_waiting_jobs.append(job.id_job)
                nj += 1
        if config_reader.batch_system_type != "local" and len(local_waiting_jobs) > config_reader.max_wait_local:
            for id_job in local_waiting_jobs[config_reader.max_wait_local:]:
                move_job_to_cluster(id_job)
        while len(scheduled_jobs_local) > 0 and nb_started < NB_RUN:
            start_job(scheduled_jobs_local.pop(0).id_job)
            nb_started += 1
        if config_reader.batch_system_type != "local" and len(scheduled_jobs_local) > config_reader.max_wait_local:
            for id_job in scheduled_jobs_local[config_reader.max_wait_local:]:
                move_job_to_cluster(id_job)
        for job in scheduled_jobs_cluster:
            start_job(job.id_job, job.batch_type)
        # Wait before return
        _printer("Sleeping...")
        time.sleep(15)
        _printer("\n")
