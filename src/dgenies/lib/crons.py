import os
import sys
import re
import getpass
import psutil
from crontab import CronTab
from dgenies.config_reader import AppConfigReader


class Crons:

    def __init__(self, base_dir, debug):
        self.base_dir = base_dir
        self.debug = debug
        self.my_cron = CronTab(user=getpass.getuser())
        self.config = AppConfigReader()
        self.local_scheduler_pid_file = os.path.join(self.config.config_dir, ".local_scheduler_pid")

    def clear(self, kill_scheduler=True):
        # Remove old crons:
        self.my_cron.remove_all(comment="dgenies")
        self.my_cron.write()
        if kill_scheduler:
            # Kill local scheduler:
            if os.path.exists(self.local_scheduler_pid_file):
                with open(self.local_scheduler_pid_file) as p_f:
                    pid = int(p_f.readline().strip("\n"))
                    if psutil.pid_exists(pid):
                        p = psutil.Process(pid)
                        p.terminate()

    def start_all(self):
        self.clear(False)
        self.init_clean_cron()
        self.init_launch_local_cron()

    @staticmethod
    def _get_python_exec():
        pyexec = sys.executable
        match = re.match(r"^(.+)/lib/(python[^/]+)/((site-packages/bin/python)|())$", pyexec)
        if match:
            pyexec = "%s/bin/%s" % (match.group(1), match.group(2))
        return pyexec

    def init_clean_cron(self):
        """
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
        :return:
        """
        if self.base_dir is not None:
            pyexec = self._get_python_exec()
            logs = os.path.join(self.config.log_dir, "local_scheduler.log") if self.debug else "/dev/null"
            job = self.my_cron.new("{0}/bin/start_local_scheduler.sh {0} {1} {2} {3} > /dev/null 2>&1 &".
                                   format(self.base_dir, pyexec, self.local_scheduler_pid_file, logs),
                                   comment="dgenies")
            job.minute.every(1)
            self.my_cron.write()