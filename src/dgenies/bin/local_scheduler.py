#!/usr/bin/env python3

import os
import time
import psutil
import atexit
from datetime import datetime
from tendo import singleton
import argparse
import logging
from logging.config import dictConfig

from dgenies.config_reader import AppConfigReader
import dgenies.database as database
from dgenies.database import Job, Session
from dgenies.lib.job_manager import JobManager

# Allow only one instance:
me = singleton.SingleInstance()

config_reader = AppConfigReader()
DRMAA_SESSION = None
NB_RUN = config_reader.local_nb_runs  # Max number of jobs running locally
NB_PREPARE = config_reader.nb_data_prepare  # Max number of data preparing jobs launched locally
DEBUG = config_reader.debug


class Scheduler:

    def __init__(self, logger=None):
        self.logger = logger if logger else logging.getLogger(__name__)
        self.enable = True

    def start(self):
        while self.enable:
            self.logger.info("Check uploads...")
            self.parse_uploads_asks()
            self.logger.info("Check jobs...")
            # jobs ready to be run locally
            scheduled_jobs_local = self.get_scheduled_local_jobs()
            # jobs ready to be run on cluster
            scheduled_jobs_cluster = self.get_scheduled_cluster_jobs()
            # jobs ready to be prepared
            prep_scheduled_jobs = self.get_prep_scheduled_jobs()
            self.logger.info("Waiting for preparing: {}".format(len(prep_scheduled_jobs)))
            # number of jobs in preparation for local run
            nb_preparing_jobs = self.get_preparing_jobs_nb()
            # number of jobs in preparation for cluster run
            nb_preparing_jobs_cluster = self.get_preparing_jobs_cluster_nb()
            self.logger.info("Preparing: {} (local) {}[{}] (cluster)".format(
                len(prep_scheduled_jobs), nb_preparing_jobs_cluster[0], nb_preparing_jobs_cluster[1]))
            self.logger.info(
                "Scheduled: {} (local) {} (cluster)".format(len(scheduled_jobs_local), len(scheduled_jobs_cluster)))
            # started jobs locally and on cluster
            started_jobs, cluster_started_jobs = self.parse_started_jobs()
            nb_started = len(started_jobs)
            self.logger.info("Started: {} (local) {} (cluster)".format(nb_started, len(cluster_started_jobs)))

            # Managing preparing jobs
            nj = 0
            # Local waiting list
            local_waiting_jobs = []
            # We scan the list of 'waiting to prepare' jobs for launching them until limits are reached
            while nj < len(prep_scheduled_jobs):
                job_runner_type = prep_scheduled_jobs[nj][1]
                # We launch local ones util the local limit is reach and all cluster ones
                if nb_preparing_jobs < NB_PREPARE or job_runner_type != "local":
                    self.prepare_job(prep_scheduled_jobs[nj][0])
                    if job_runner_type == "local":
                        nb_preparing_jobs += 1
                    del prep_scheduled_jobs[nj]
                else:
                    # We add remaining local ones into local waiting list
                    if job_runner_type == "local":
                        local_waiting_jobs.append(prep_scheduled_jobs[nj][0])
                    nj += 1
            # If local waiting limit is reached, switch waiting jobs to cluster
            if config_reader.runner_type != "local" and len(local_waiting_jobs) > config_reader.max_wait_local:
                for id_job in local_waiting_jobs[config_reader.max_wait_local:]:
                    self.move_job_to_cluster(id_job)

            # Managing scheduled jobs
            # We start local scheduled jobs until limit of number running jobs is reached
            while len(scheduled_jobs_local) > 0 and nb_started < NB_RUN:
                self.start_align(scheduled_jobs_local.pop(0))
                nb_started += 1

            # If local running limit is reached, switch jobs to cluster
            if config_reader.runner_type != "local" and len(scheduled_jobs_local) > config_reader.max_wait_local:
                for id_job in scheduled_jobs_local[config_reader.max_wait_local:]:
                    self.move_job_to_cluster(id_job)

            # Start scheduled jobs
            for job in scheduled_jobs_cluster:
                self.start_align(job["job_id"], job["runner_type"])

            # Wait before return
            self.logger.info("Sleeping for 15s...")
            time.sleep(15)

    def start_align(self, id_job, runner_type="local"):
        """
        Start an align job (mapping step)

        :param id_job: job id
        :type id_job: str
        :param runner_type: local, slurm or sge
        :type runner_type: str
        """
        self.logger.info("Start job: {}".format(id_job))
        with Job.connect():
            job = Job.get(Job.id_job == id_job)
            job.status = "starting"
            job.save()
            job_mng = JobManager(id_job=id_job, email=job.email, tool=job.tool, options=job.options)
            job_mng.set_inputs_from_res_dir()
            job_mng.run_align_in_thread(runner_type)

    @staticmethod
    def get_scheduled_local_jobs():
        """
        Get list of jobs ready to be started (for local runs)

        :return: list of jobs
        :rtype: list
        """
        all_jobs = []
        with Job.connect():
            jobs = Job.select().where((Job.runner_type == "local") & ((Job.status == "prepared") | (Job.status == "scheduled"))).\
                order_by(Job.date_created)
            for job in jobs:
                all_jobs.append(job.id_job)
                job.status = "scheduled"
                job.save()
        return all_jobs

    @staticmethod
    def get_scheduled_cluster_jobs():
        """
        Get list of jobs ready to be started (for cluster runs)

        :return: list of jobs
        :rtype: list
        """
        all_jobs = []
        with Job.connect():
            jobs = Job.select().where((Job.runner_type != "local") & ((Job.status == "prepared") | (Job.status == "scheduled"))).\
                order_by(Job.date_created)
            for job in jobs:
                all_jobs.append({"job_id": job.id_job, "runner_type": job.runner_type})
                job.status = "scheduled"
                job.save()
        return all_jobs

    def prepare_job(self, id_job):
        """
        Launch job preparation of data

        :param id_job: job id
        :type id_job: str
        """
        self.logger.info("Prepare data for job: {}".format(id_job))
        with Job.connect():
            job = Job.get(Job.id_job == id_job)
            job.status = "preparing"
            job.save()
            job_mng = JobManager(id_job=id_job, email=job.email, tool=job.tool)
    #        job_mng = JobManager(id_job=id_job, email=job.email, tool=job.tool, options=job.options)
            job_mng.set_inputs_from_res_dir()
            job_mng.prepare_job_in_thread()

    @staticmethod
    def get_prep_scheduled_jobs():
        """
        Get list of jobs ready to be prepared (all data is downloaded and parsed)

        :return: list of (job id, batch type)
        :rtype: list
        """
        with Job.connect():
            jobs = Job.select().where(Job.status == "waiting").order_by(Job.date_created)
            return [(j.id_job, j.runner_type) for j in jobs]

    @staticmethod
    def get_preparing_jobs_nb():
        """
        Get number of jobs in preparation step (for local runs)

        :return: number of jobs
        :rtype: int
        """
        with Job.connect():
            return len(Job.select().where(Job.status == "preparing"))

    @staticmethod
    def get_preparing_jobs_cluster_nb():
        """
        Get number of jobs in preparation step (for cluster runs)

        :return: number of jobs
        :rtype: int
        """
        with Job.connect():
            return len(Job.select().where(Job.status == "preparing-cluster")), \
                   len(Job.select().where(Job.status == "prepare-scheduled"))

    def update_batch_status(self):
        with Job.connect():
            batch_jobs = Job.select().where((Job.status == "started-batch"))
            for job in batch_jobs:
                # We refresh the batch job status
                j = JobManager(id_job=job.id_job)
                status = j.refresh_batch_status()
                job.status = status
                if job.status == "fail":
                    job.error = "<p>At least one of your jobs has failed.</p>"
                job.save()
                if status in {"success", "succeed", "fail"}:
                    self.logger.info("{}: Send email".format(job.id_job))
                    j.send_mail_post_if_allowed()

    def parse_started_jobs(self):
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
                                      (Job.status == "prepare-scheduled") | (Job.status == "preparing-cluster"))
            for job in jobs:
                pid = job.id_process
                if job.runner_type == "local":
                    if job.status != "started" or psutil.pid_exists(pid):
                        jobs_started.append(job.id_job)
                    else:
                        self.logger.info("Job %s (pid: %d) has died!" % (job.id_job, job.id_process))
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
                            if job.runner_type == "slurm":
                                os.system("scancel %s" % job.id_process)
                            elif job.runner_type == "sge":
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
        # We update batch jobs status as state of individual jobs was just updated
        self.update_batch_status()
        return jobs_started, cluster_jobs_started

    def parse_uploads_asks(self):
        """
        Parse asks for an upload: allow new uploads when other end, remove expired sessions, ...
        """
        with Session.connect():
            now = datetime.now()
            # Get allowed:
            all_sessions = Session.select()
            nb_sessions = len(all_sessions)
            self.logger.info("All sessions: {}".format(nb_sessions))
            sessions = Session.select().where(Session.status == "active")
            nb_active_dl = len(sessions)
            self.logger.info("Active downloads: {}".format(nb_active_dl))
            for session in sessions:
                if not session.keep_active \
                        and (now - session.last_ping).total_seconds() > config_reader.delete_allowed_session_delay:
                    self.logger.info("Delete 1 active session: {}".format(session.s_id))
                    session.delete_instance()  # We consider the user has left
                    nb_active_dl -= 1
            # Get pending:
            sessions = Session.select().where(Session.status == "pending").order_by(Session.date_created)
            self.logger.info("Pending sessions: {}".format(len(sessions)))
            for session in sessions:
                delay = (now - session.last_ping).total_seconds()
                if delay > config_reader.reset_pending_session_delay:
                    session.status = "reset"  # Reset position, the user has probably left
                    session.save()
                    self.logger.info("Reset 1 session: {}".format(session.s_id))
                elif nb_active_dl < config_reader.max_concurrent_dl:
                    session.status = "active"
                    session.save()
                    nb_active_dl += 1
                    self.logger.info("Enable 1 session: {}".format(session.s_id))
            # Remove old sessions:
            for session in all_sessions:
                delay = (now - session.last_ping).total_seconds()
                if delay > config_reader.delete_session_delay:
                    self.logger.info("Delete 1 outdated session: {}".format(session.s_id))
                    session.delete_instance()  # Session has expired

    @staticmethod
    def move_job_to_cluster(id_job):
        """
        Change local job to be run on the cluster

        :param id_job:
        :return:
        """
        with Job.connect():
            job = Job.get(Job.id_job == id_job)
            job.runner_type = config_reader.runner_type
            job.save()


@atexit.register
def cleaner():
    """
    Exit DRMAA session at program exit
    """
    if "DRMAA_SESSION" in globals() and DRMAA_SESSION:
        DRMAA_SESSION.exit()


def set_logger(log_file=None, level="INFO"):
    if log_file:
        handler = {
            'class': 'logging.FileHandler',
            'filename': log_file,
            'formatter': 'default',
            'encoding': 'utf8',
            'mode': 'a'
        }
    else:
        handler = {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stderr',
            'formatter': 'default'
        }
    dictConfig({
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'default': {
                'format': '[%(asctime)s] %(levelname)s in %(module)s (%(threadName)s): %(message)s',
            }
        },
        'handlers': {'handler': handler},
        'loggers': {
            'dgenies': {
                'level': level,
                'handlers': ['handler']
            },
            __name__: {
                'level': level,
                'handlers': ['handler']
            }
        }
    })


def parse_args():
    """
    Parse command line arguments and define DEBUG constants
    """

    global DEBUG, NB_RUN, NB_PREPARE

    parser = argparse.ArgumentParser(description="Start local scheduler")
    parser.add_argument('-d', '--debug', action="store_true", required=False, default=False,
                        help="Set to True to enable debug")
    parser.add_argument('-l', '--log-file', type=str, required=False, default=None,
                        help="Log file (default: stdout)")
    parser.add_argument("--config", nargs="+", metavar='application.properties', type=str, required=False,
                        help="D-Genies configuration file")
    parser.add_argument("--tools-config", dest="tools_config", metavar='tools.yaml', type=str,
                        required=False, help="D-Genies tools configuration file")
    args = parser.parse_args()

    DEBUG = args.debug

    set_logger(args.log_file, "DEBUG" if DEBUG else 'INFO')

    if args.config:
        config_reader.reset_config(args.config)
        DEBUG = DEBUG or config_reader.debug

        # We update parameters in case config file has changed
        NB_RUN = config_reader.local_nb_runs  # Max number of jobs running locally
        NB_PREPARE = config_reader.nb_data_prepare  # Max number of data preparing jobs launched locally

    database.initialize()
    if args.tools_config:
        from dgenies.tools import Tools
        Tools(args.tools_config)


if __name__ == '__main__':
    parse_args()
    logger = logging.getLogger(__name__)
    logger.debug("DEBUG")
    #  We set drmaa information if needed
    if config_reader.drmaa_lib_path is not None and config_reader.runner_type != "local":
        os.environ["DRMAA_LIBRARY_PATH"] = config_reader.drmaa_lib_path
        try:
            import drmaa
            from dgenies.lib.drmaasession import DrmaaSession
            DRMAA_SESSION = DrmaaSession()
        except ImportError:
            pass

    scheduler = Scheduler(logger)
    scheduler.start()
