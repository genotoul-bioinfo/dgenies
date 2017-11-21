import os
import re
import inspect
from configparser import RawConfigParser, NoOptionError, NoSectionError


class AppConfigReader(object):
    """
    """

    CONFIG_FILE_PATH = "../application.properties"

    def __init__(self):
        """
        """
        config_file = os.path.join(os.path.dirname(inspect.getfile(self.__class__)), self.CONFIG_FILE_PATH)
        if not os.path.exists(config_file):
            raise FileNotFoundError("ERROR: application.properties not found. Please copy the example file and check "
                                    "properties are correct for you!")
        self.reader = RawConfigParser()
        self.reader.read(config_file)

    @staticmethod
    def replace_vars(path):
        return path.replace("###USER###", os.path.expanduser("~"))\
            .replace("###PROGRAM###", os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

    def get_upload_folder(self):
        try:
            return self.replace_vars(self.reader.get("global", "upload_folder"))
        except NoOptionError:
            raise Exception("No upload folder found in application.properties (global section)")

    def get_app_data(self):
        try:
            return self.replace_vars(self.reader.get("global", "data_folder"))
        except NoOptionError:
            raise Exception("No data folder found in application.properties (global section)")

    def get_batch_system_type(self):
        try:
            return self.reader.get("global", "batch_system_type")
        except NoOptionError:
            return "local"

    def get_nb_threads(self):
        try:
            return self.reader.get("global", "threads")
        except NoOptionError:
            return "4"

    def get_web_url(self):
        try:
            return self.replace_vars(self.reader.get("global", "web_url"))
        except NoOptionError:
            return "http://localhost:5000"

    def get_minimap2_exec(self):
        try:
            entry = self.reader.get("softwares", "minimap2")
            return entry if entry != "###DEFAULT###" else "minimap2"
        except NoOptionError:
            return "minimap2"

    def get_database(self):
        try:
            return self.replace_vars(self.reader.get("database", "sqlite_file"))
        except NoOptionError:
            return ":memory:"

    def get_mail_status_sender(self):
        try:
            return self.replace_vars(self.reader.get("mail", "status"))
        except NoOptionError:
            return "status@dgenies"

    def get_mail_reply(self):
        try:
            return self.replace_vars(self.reader.get("mail", "reply"))
        except NoOptionError:
            return "status@dgenies"

    def get_mail_org(self):
        try:
            return self.replace_vars(self.reader.get("mail", "org"))
        except NoOptionError:
            return None

    def get_send_mail_status(self):
        try:
            return self.reader.get("mail", "send_mail_status").lower() == "true"
        except NoOptionError:
            return True

    def get_disable_mail(self):
        try:
            return self.reader.get("mail", "disable").lower() == "true"
        except NoOptionError:
            return False

    def get_cron_menage_hour(self):
        try:
            value = self.reader.get("cron", "menage_hour").lower()
            match = re.match(r"(([0-9])|([0-1][0-9])|(2[0-3]))[hH]([0-5][0-9])", value)
            if match is not None:
                return [int(match.group(1)), int(match.group(5))]
            else:
                print("Incorrect menage hour format!")
                return [1, 0]
        except (NoOptionError, NoSectionError):
            return [1, 0]

    def get_cron_menage_freq(self):
        try:
            return int(self.reader.get("cron", "menage_freq"))
        except (NoOptionError, NoSectionError):
            return 1

    def get_local_nb_runs(self):
        try:
            return int(self.reader.get("jobs", "run_local"))
        except (NoOptionError, NoSectionError):
            return 1
