import getpass
from crontab import CronTab
from config_reader import AppConfigReader


class Crons:

    def __init__(self, base_dir=None):
        self.base_dir = base_dir
        self.my_cron = CronTab(user=getpass.getuser())
        self.config_reader = AppConfigReader()

    def clear(self):
        # Remove old crons:
        self.my_cron.remove_all(comment="dgenies")
        self.my_cron.write()

    def start_all(self):
        self.clear()
        self.init_menage_cron()

    def init_menage_cron(self):
        """
        Menage cron is launched at 1h00am each day
        """
        menage_hour = self.config_reader.get_cron_menage_hour()
        menage_freq = self.config_reader.get_cron_menage_freq()
        if self.base_dir is not None:
            job = self.my_cron.new("python3 {0}/bin/clean_jobs.py > {0}/logs/menage.log 2>&1".format(self.base_dir),
                                   comment="dgenies")
            job.day.every(menage_freq)
            job.hour.on(menage_hour[0])
            job.minute.on(menage_hour[1])
            self.my_cron.write()
        else:
            raise Exception("Crons: base_dir must not be None")
