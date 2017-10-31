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
        self.reader = RawConfigParser()
        self.reader.read(os.path.join(os.path.dirname(inspect.getfile(self.__class__)), self.CONFIG_FILE_PATH))

    def get_app_data(self):
        try:
            return self.reader.get("global", "data_folder")
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
            return self.reader.get("softwares", "minimap2")
        except NoOptionError:
            return "minimap2"

    def get_samtools_exec(self):
        try:
            return self.reader.get("softwares", "samtools")
        except NoOptionError:
            return "samtools"

    def get_database(self):
        try:
            return self.reader.get("database", "sqlite_file")
        except NoOptionError:
            return ":memory:"
