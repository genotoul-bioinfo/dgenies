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

    def get_upload_folder(self):
        try:
            return self.reader.get("global", "upload_folder")
        except NoOptionError:
            return None

    def get_app_data(self):
        try:
            return self.reader.get("global", "data_folder")
        except NoOptionError:
            return None
