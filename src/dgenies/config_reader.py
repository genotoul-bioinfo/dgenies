import os
import re
import inspect
from configparser import RawConfigParser, NoOptionError, NoSectionError
from dgenies.lib.decorators import Singleton


@Singleton
class AppConfigReader:
    """
    Store all configs
    """

    config_file = "/etc/dgenies/application.properties"
    config_file_local = config_file + ".local"

    def __init__(self):
        """
        All "get_*" functions results are stored in the "self.*" corresponding attribute
        Example: results of the get_upload_folder function is stored in self.upload_folder
        """
        self.app_dir = os.path.dirname(inspect.getfile(self.__class__))
        config_file = []
        if os.path.exists(self.config_file):
            config_file.append(self.config_file)
        if os.path.exists(self.config_file_local):
            config_file.append(self.config_file_local)
        if len(config_file) > 0:
            self.config_file = config_file
        else:
            raise FileNotFoundError("ERROR: application.properties not found. Please copy the example file and "
                                    "check properties are correct for you!")
        self.reader = RawConfigParser()
        self.reader.read(self.config_file)
        for attr in dir(self):
            attr_o = getattr(self, attr)
            if attr.startswith("_get_") and callable(attr_o):
                try:
                    setattr(self, attr[5:], attr_o())
                except Exception as e:
                    print(e)

    def _replace_vars(self, path, config=False):
        new_path = path.replace("###USER###", os.path.expanduser("~"))\
            .replace("###PROGRAM###", os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        if "###CONFIG###" in new_path:
            if config:
                raise Exception("###CONFIG### tag not allowed for config dir")
            else:
                return new_path.replace("###CONFIG###", self._get_config_dir())
        return new_path

    def _get_config_dir(self):
        try:
            return self._replace_vars(self.reader.get("global", "config_dir"), True)
        except NoOptionError:
            return self._replace_vars("###USER###/.dgenies")

    def _get_upload_folder(self):
        try:
            return self._replace_vars(self.reader.get("global", "upload_folder"))
        except NoOptionError:
            raise Exception("No upload folder found in application.properties (global section)")

    def _get_app_data(self):
        try:
            return self._replace_vars(self.reader.get("global", "data_folder"))
        except NoOptionError:
            raise Exception("No data folder found in application.properties (global section)")

    def _get_batch_system_type(self):
        try:
            return self.reader.get("global", "batch_system_type")
        except NoOptionError:
            return "local"

    def _get_nb_threads(self):
        try:
            return self.reader.get("global", "threads_local")
        except NoOptionError:
            return "4"

    def _get_web_url(self):
        try:
            return self._replace_vars(self.reader.get("global", "web_url"))
        except NoOptionError:
            return "http://localhost:5000"

    def _get_max_upload_size(self):
        try:
            max_size_b = self._replace_vars(self.reader.get("global", "max_upload_size"))
            if max_size_b == "-1":
                return -1
            size_v = float(max_size_b[:-1])
            size_unit = max_size_b[-1].upper()
            if size_unit not in ["M", "G"]:
                raise ValueError("Max size unit must be M or G")
            max_size = int(size_v * 1024 * 1024)
            if size_unit == "G":
                max_size *= 1024
            return max_size
        except NoOptionError:
            return -1

    def _get_max_upload_file_size(self):
        try:
            max_size_b = self._replace_vars(self.reader.get("global", "max_upload_file_size"))
            if max_size_b == "-1":
                return -1
            size_v = float(max_size_b[:-1])
            size_unit = max_size_b[-1].upper()
            if size_unit not in ["M", "G"]:
                raise ValueError("Max size unit must be M or G")
            max_size = int(size_v * 1024 * 1024)
            if size_unit == "G":
                max_size *= 1024
            return max_size
        except NoOptionError:
            return 1024 * 1024 * 1024

    def _get_minimap2_exec(self):
        try:
            entry = self.reader.get("softwares", "minimap2")
            return entry if entry != "###DEFAULT###" else os.path.join(self.app_dir, "bin", "minimap2")
        except NoOptionError:
            return os.path.join(self.app_dir, "bin", "minimap2")

    def _get_minimap2_cluster_exec(self):
        try:
            entry = self.reader.get("softwares", "minimap2_cluster")
            return entry if entry != "###DEFAULT###" else "minimap2"
        except NoOptionError:
            return self._get_minimap2_exec()

    def _get_database_type(self):
        try:
            return self.reader.get("database", "type")
        except NoOptionError:
            return "sqlite"

    def _get_database_url(self):
        try:
            url = self._replace_vars(self.reader.get("database", "url"))
            if self._get_database_type() == "sqlite" and url != ":memory:":
                parent_dir = os.path.dirname(url)
                if not os.path.exists(parent_dir):
                    try:
                        os.makedirs(parent_dir)
                    except FileNotFoundError:
                        pass
            return url
        except NoOptionError:
            return ":memory:"

    def _get_database_port(self):
        try:
            return int(self.reader.get("database", "port"))
        except (NoOptionError, ValueError):
            db_type = self._get_database_type()
            if db_type == "mysql":
                return 3306
            elif db_type == "sqlite":
                return -1
            raise Exception("Missing parameter: database port")

    def _get_database_db(self):
        try:
            db = self.reader.get("database", "db")
            if db == "":
                raise ValueError()
            return db
        except (NoOptionError, ValueError):
            if self._get_database_type() == "sqlite":
                return ""
            raise Exception("Missing parameter: database db name")

    def _get_database_user(self):
        try:
            user = self.reader.get("database", "user")
            if user == "":
                raise ValueError()
            return user
        except (NoOptionError, ValueError):
            if self._get_database_type() == "sqlite":
                return ""
            raise Exception("Missing parameter: database user")

    def _get_database_password(self):
        try:
            passwd = self.reader.get("database", "password")
            if passwd == "":
                raise ValueError()
            return passwd
        except (NoOptionError, ValueError):
            if self._get_database_type() == "sqlite":
                return ""
            raise Exception("Missing parameter: database password")

    def _get_mail_status_sender(self):
        try:
            return self._replace_vars(self.reader.get("mail", "status"))
        except NoOptionError:
            return "status@dgenies"

    def _get_mail_reply(self):
        try:
            return self._replace_vars(self.reader.get("mail", "reply"))
        except NoOptionError:
            return "status@dgenies"

    def _get_mail_org(self):
        try:
            return self._replace_vars(self.reader.get("mail", "org"))
        except NoOptionError:
            return None

    def _get_send_mail_status(self):
        try:
            return self.reader.get("mail", "send_mail_status").lower() == "true"
        except NoOptionError:
            return True

    def _get_disable_mail(self):
        try:
            return self.reader.get("mail", "disable").lower() == "true"
        except NoOptionError:
            return False

    def _get_cron_menage_hour(self):
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

    def _get_cron_menage_freq(self):
        try:
            return int(self.reader.get("cron", "menage_freq"))
        except (NoOptionError, NoSectionError):
            return 1

    def _get_local_nb_runs(self):
        try:
            return int(self.reader.get("jobs", "run_local"))
        except (NoOptionError, NoSectionError):
            return 1

    def _get_nb_data_prepare(self):
        try:
            return int(self.reader.get("jobs", "data_prepare"))
        except (NoOptionError, NoSectionError):
            return 2

    def _get_max_concurrent_dl(self):
        try:
            return int(self.reader.get("jobs", "max_concurrent_dl"))
        except (NoOptionError, NoSectionError):
            return 5

    def _get_drmaa_lib_path(self):
        try:
            path = self.reader.get("cluster", "drmaa_lib_path")
            if path != "###SET_IT###":
                return path
            return None
        except (NoOptionError, NoSectionError):
            if self._get_batch_system_type() != "local":
                raise Exception("No drmaa library set. It is required if the batch system type is not 'local'")
            return None

    def _get_drmaa_native_specs(self):
        try:
            return self.reader.get("cluster", "native_specs")
        except (NoOptionError, NoSectionError):
            return "###DEFAULT###"

    def _get_max_run_local(self):
        try:
            return int(self.reader.get("cluster", "max_run_local"))
        except (NoOptionError, NoSectionError):
            return 10

    def _get_max_wait_local(self):
        try:
            return int(self.reader.get("cluster", "max_wait_local"))
        except (NoOptionError, NoSectionError):
            return 5

    def _get_min_query_size(self):
        try:
            size_b = self.reader.get("cluster", "min_query_size")
            size_v = int(size_b[:-1])
            size_unit = size_b[-1].upper()
            if size_unit not in ["M", "G"]:
                raise ValueError("Min query size unit must be M or G")
            min_size = size_v * 1024 * 1024
            if size_unit == "G":
                min_size *= 1024
            return min_size
        except (NoOptionError, NoSectionError):
            return 0

    def _get_min_target_size(self):
        try:
            size_b = self.reader.get("cluster", "min_target_size")
            size_v = int(size_b[:-1])
            size_unit = size_b[-1].upper()
            if size_unit not in ["M", "G"]:
                raise ValueError("Min query size unit must be M or G")
            min_size = size_v * 1024 * 1024
            if size_unit == "G":
                min_size *= 1024
            return min_size
        except (NoOptionError, NoSectionError):
            return 0

    def _get_cluster_prepare_script(self):
        try:
            return self._replace_vars(self.reader.get("cluster", "prepare_script"))
        except (NoOptionError, NoSectionError):
            return self._replace_vars("###PROGRAM###/bin/prepare_data.sh")

    def _get_cluster_python_script(self):
        try:
            return self._replace_vars(self.reader.get("cluster", "python3_script"))
        except (NoOptionError, NoSectionError):
            return "python3"

    def _get_cluster_memory(self):
        try:
            memory = int(self.reader.get("cluster", "memory"))
            if memory % self._get_cluster_threads() != 0:
                raise ValueError("ERROR in config: cluster memory must be divisible by the number of cluster threads!")
            return memory
        except (NoOptionError, NoSectionError):
            return 32

    def _get_cluster_threads(self):
        try:
            return int(self.reader.get("cluster", "threads"))
        except (NoOptionError, NoSectionError):
            return 4

    def _get_debug(self):
        try:
            return self.reader.get("debug", "enable").lower() == "true"
        except (NoOptionError, NoSectionError):
            return False

    def _get_log_dir(self):
        try:
            log_dir = self._replace_vars(self.reader.get("debug", "log_dir"))
        except (NoOptionError, NoSectionError):
            log_dir = self._replace_vars("###CONFIG###/logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        elif not os.path.isdir(log_dir):
            raise TypeError("Log dir must be a directory")
        return log_dir

    def _get_allowed_ip_tests(self):
        allowed_ip = {"127.0.0.1"}
        try:
            allowed_ip_txt = self.reader.get("debug", "allowed_ip_tests")
            for ip in re.split(r",(\s+)?", allowed_ip_txt):
                allowed_ip.add(ip)
        except (NoOptionError, NoSectionError):
            pass
        return allowed_ip
