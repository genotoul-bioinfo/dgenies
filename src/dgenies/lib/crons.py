import os
import sys
import re
import getpass
import psutil
from crontab import CronTab
from dgenies.config_reader import AppConfigReader


class Crons:

    """
    Manage crontab jobs (webserver mode)
    """

    def __init__(self, base_dir, debug):
        """

        :param base_dir: software base directory path
        :type base_dir: str
        :param debug: True to enable debug mode
        :type debug: bool
        """
        self.base_dir = base_dir
        self.debug = debug
        self.my_cron = CronTab(user=getpass.getuser())
        self.config = AppConfigReader()
        self.local_scheduler_pid_file = os.path.join(self.config.config_dir, ".local_scheduler_pid")

    def clear(self, kill_scheduler=True, remove_pid_file=True):
        """
        Clear all crons

        :param kill_scheduler: if True, kill local scheduler currently running
        :type kill_scheduler: bool
        :param remove_pid_file: if True, remove pid file if local scheduler was killed successfully
        :type remove_pid_file: bool
        """
        # Remove old crons:
        self.my_cron.remove_all(comment="dgenies")
        self.my_cron.write()
        if kill_scheduler:
            # Kill local scheduler:
            if os.path.exists(self.local_scheduler_pid_file):
                with open(self.local_scheduler_pid_file) as p_f:
                    pid = int(p_f.readline().strip("\n"))
                if psutil.pid_exists(pid) and remove_pid_file:
                    p = psutil.Process(pid)
                    p.terminate()
                    os.remove(self.local_scheduler_pid_file)

    def start_all(self):
        """
        Start all crons
        """
        self.clear(False)
        self.init_clean_cron()
        self.init_launch_local_cron()

    @staticmethod
    def _get_python_exec():
        """
        Get python executable path
        """
        pyexec = sys.executable
        match = re.match(r"^(.+)/lib/(python[^/]+)/((site-packages/bin/python)|())$", pyexec)
        if match:
            pyexec = "%s/bin/%s" % (match.group(1), match.group(2))
        return pyexec

    def init_clean_cron(self):
        """
        Initialize clean cron: will clear old jobs.
        Clean cron is launched at 1h00am each day
        """
        clean_time = self.config.cron_clean_time
        clean_freq = self.config.cron_clean_freq
        if self.base_dir is not None:
            job = self.my_cron.new(self._get_python_exec() +
                                   " {0}/bin/clean_jobs.py > {1}/clean.log 2>&1".format(self.base_dir,
                                                                                        self.config.log_dir),
                                   comment="dgenies")
            job.day.every(clean_freq)
            job.hour.on(clean_time[0])
            job.minute.on(clean_time[1])
            self.my_cron.write()
        else:
            raise Exception("Crons: base_dir must not be None")

    def init_launch_local_cron(self):
        """
        Try to launch local scheduler (if not already launched)
        """
        if self.base_dir is not None:
            pyexec = self._get_python_exec()
            logs = os.path.join(self.config.log_dir, "local_scheduler.log") if self.debug else "/dev/null"
            job = self.my_cron.new("{0}/bin/start_local_scheduler.sh {0} {1} {2} {3} > /dev/null 2>&1 &".
                                   format(self.base_dir, pyexec, self.local_scheduler_pid_file, logs),
                                   comment="dgenies")
            job.minute.every(1)
            self.my_cron.write()