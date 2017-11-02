import os
import inspect
from configparser import RawConfigParser, NoOptionError


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
