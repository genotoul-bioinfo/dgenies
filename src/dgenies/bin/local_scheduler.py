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
if config_reader.drmaa_lib_path is not None and config_reader.batch_system_type != "local":
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
    """
    print messages to stdout or to a file (according to LOG_FILE global constant)

    :param messages: messages to print
    """
    if DEBUG:
        if LOG_FILE == "stdout":
            print(*messages)
        else:
            with open(LOG_FILE, "a") as log_f:
                print(*messages, file=log_f)


def start_job(id_job, batch_system_type="local"):
    """
    Start a job (mapping step)

    :param id_job: job id
    :type id_job: str
    :param batch_system_type: local, slurm or sge
    :type batch_system_type: str
    """
    _printer("Start job", id_job)
    with Job.connect():
        job = Job.get(Job.id_job == id_job)
        job.status = "starting"
        job.save()
        job_mng = JobManager(id_job=id_job, email=job.email, tool=job.tool, options=job.options)
        job_mng.set_inputs_from_res_dir()
        job_mng.run_job_in_thread(batch_system_type)


def get_scheduled_local_jobs():
    """
    Get list of jobs ready to be started (for local runs)

    :return: list of jobs
    :rtype: list
    """
    all_jobs = []
    with Job.connect():
        jobs = Job.select().where((Job.batch_type == "local") & ((Job.status == "prepared") | (Job.status == "scheduled"))).\
            order_by(Job.date_created)
        for job in jobs:
            all_jobs.append(job.id_job)
            job.status = "scheduled"
            job.save()
    return all_jobs


def get_scheduled_cluster_jobs():
    """
    Get list of jobs ready to be started (for cluster runs)

    :return: list of jobs
    :rtype: list
    """
    all_jobs = []
    with Job.connect():
        jobs = Job.select().where((Job.batch_type != "local") & ((Job.status == "prepared") | (Job.status == "scheduled"))).\
            order_by(Job.date_created)
        for job in jobs:
            all_jobs.append({"job_id": job.id_job, "batch_type": job.batch_type})
            job.status = "scheduled"
            job.save()
    return all_jobs


def prepare_job(id_job):
    """
    Launch job preparation of data

    :param id_job: job id
    :type id_job: str
    """
    _printer("Prepare data for job:", id_job)
    with Job.connect():
        job = Job.get(Job.id_job == id_job)
        job.status = "preparing"
        job.save()
        job_mng = JobManager(id_job=id_job, email=job.email, tool=job.tool)
#        job_mng = JobManager(id_job=id_job, email=job.email, tool=job.tool, options=job.options)
        job_mng.set_inputs_from_res_dir()
        job_mng.prepare_data_in_thread()


def get_prep_scheduled_jobs():
    """
    Get list of jobs ready to be prepared (all data is downloaded and parsed)

    :return: list of jobs
    :rtype: list
    """
    with Job.connect():
        jobs = Job.select().where(Job.status == "waiting").order_by(Job.date_created)
        return [(j.id_job, j.batch_type) for j in jobs]


def get_preparing_jobs_nb():
    """
    Get number of jobs in preparation step (for local runs)

    :return: number of jobs
    :rtype: int
    """
    with Job.connect():
        return len(Job.select().where(Job.status == "preparing"))


def get_preparing_jobs_cluster_nb():
    """
    Get number of jobs in preparation step (for cluster runs)

    :return: number of jobs
    :rtype: int
    """
    with Job.connect():
        return len(Job.select().where(Job.status == "preparing-cluster")), \
               len(Job.select().where(Job.status == "prepare-scheduled"))


def parse_started_jobs():
    """
    Parse all started jobs: check all is OK, change jobs status if needed. Look for died jobs

    :return: (list of id of jobs started locally, list of id of jobs started on cluster)
    :rtype: (list, list)
    """
    with Job.connect():
        jobs_started = []  # Only local jobs
        cluster_jobs_started = []  # Only cluster jobs
        jobs = Job.select().where((Job.status == "started") | (Job.status == "starting") | (Job.status == "succeed") |
                                  (Job.status == "merging") | (Job.status == "scheduled-cluster") |
                                  (Job.status == "prepare-scheduled") | (Job.status == "prepare-cluster"))
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
                            job.status = "started"
                            job.save()
                            cluster_jobs_started.append(job.id_job)
                        elif job.status == "prepare-scheduled" and status == drmaa.JobState.RUNNING:
                            job.status = "preparing-cluster"
                            job.save()
                        elif job.status == "started":
                            cluster_jobs_started.append(job.id_job)
                else:
                    cluster_jobs_started.append(job.id_job)
    return jobs_started, cluster_jobs_started


def parse_uploads_asks():
    """
    Parse asks for an upload: allow new uploads when other end, remove expired sessions, ...
    """
    with Session.connect():
        now = datetime.now()
        # Get allowed:
        all_sessions = Session.select()
        nb_sessions = len(all_sessions)
        _printer("All sessions:", nb_sessions)
        sessions = Session.select().where(Session.status == "active")
        nb_active_dl = len(sessions)
        _printer("Active_dl:", nb_active_dl)
        for session in sessions:
            if not session.keep_active and (now - session.last_ping).total_seconds() > 50:
                _printer("Delete 1 active session:", session.s_id)
                session.delete_instance()  # We consider the user has left
                nb_active_dl -= 1
        # Get pending:
        sessions = Session.select().where(Session.status == "pending").order_by(Session.date_created)
        _printer("Pending:", len(sessions))
        for session in sessions:
            delay = (now - session.last_ping).total_seconds()
            if delay > 30:
                session.status = "reset"  # Reset position, the user has probably left
                session.save()
                _printer("Reset 1 session:", session.s_id)
            elif nb_active_dl < config_reader.max_concurrent_dl:
                session.status = "active"
                session.save()
                nb_active_dl += 1
                _printer("Enable 1 session:", session.s_id)
        # Remove old sessions:
        for session in all_sessions:
            delay = (now - session.last_ping).total_seconds()
            if delay > 86400:  # Session has more than 1 day
                _printer("Delete 1 outdated session:", session.s_id)
                session.delete_instance()  # Session has expired


@atexit.register
def cleaner():
    """
    Exit DRMAA session at program exit
    """
    if "DRMAA_SESSION" in globals():
        DRMAA_SESSION.exit()


def move_job_to_cluster(id_job):
    """
    Change local job to be run on the cluster

    :param id_job:
    :return:
    """
    with Job.connect():
        job = Job.get(Job.id_job == id_job)
        job.batch_type = config_reader.batch_system_type
        job.save()


def parse_args():
    """
    Parse command line arguments and define DEBUG and LOG_FILE constants
    """

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


if __name__ == '__main__':
    parse_args()

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
            job_batch_type = prep_scheduled_jobs[nj][1]
            if nb_preparing_jobs < NB_PREPARE or job_batch_type != "local":
                prepare_job(prep_scheduled_jobs[nj][0])
                if job_batch_type == "local":
                    nb_preparing_jobs += 1
                del prep_scheduled_jobs[nj]
            else:
                if job_batch_type == "local":
                    local_waiting_jobs.append(prep_scheduled_jobs[nj][0])
                nj += 1
        if config_reader.batch_system_type != "local" and len(local_waiting_jobs) > config_reader.max_wait_local:
            for id_job in local_waiting_jobs[config_reader.max_wait_local:]:
                move_job_to_cluster(id_job)
        while len(scheduled_jobs_local) > 0 and nb_started < NB_RUN:
            start_job(scheduled_jobs_local.pop(0))
            nb_started += 1
        if config_reader.batch_system_type != "local" and len(scheduled_jobs_local) > config_reader.max_wait_local:
            for id_job in scheduled_jobs_local[config_reader.max_wait_local:]:
                move_job_to_cluster(id_job)
        for job in scheduled_jobs_cluster:
            start_job(job["job_id"], job["batch_type"])
        # Wait before return
        _printer("Sleeping...")
        time.sleep(15)
        _printer("\n")
