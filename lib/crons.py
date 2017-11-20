import getpass
from crontab import CronTab


class Crons:

    def __init__(self, base_dir=None):
        self.base_dir = base_dir
        self.my_cron = CronTab(user=getpass.getuser())
        self.clear()

    def clear(self):
        # Remove old crons:
        self.my_cron.remove_all(comment="dgenies")
        self.my_cron.write()

    def init_menage_cron(self):
        """
        Menage cron is launched at 1h00am each day
        """
        if self.base_dir is not None:
            job = self.my_cron.new("python3 {0}/bin/clean_jobs.py > {0}/logs/menage.log".format(self.base_dir),
                                   comment="dgenies")
            job.day.every(1)
            job.hour.on(1)
            job.minute.on(0)
            self.my_cron.write()
        else:
            raise Exception("Crons: base_dir must not be None")
