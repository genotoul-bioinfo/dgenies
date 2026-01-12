from __future__ import annotations

import os
import sys
import re
import inspect
from os import environ
from pathlib import Path
import logging
from configparser import RawConfigParser, NoOptionError, NoSectionError
from .lib.decorators import Singleton
from typing import Callable, Iterator

@Singleton
class AppConfigReader:
    """
    Store all configs
    """

    def __init__(self, config_file=[]):
        """
        All "get_*" functions results are stored in the "self.*" corresponding attribute
        Example: results of the get_upload_folder function is stored in self.upload_folder
        """
        self.logger = logging.getLogger(__name__)
        self.app_dir = os.path.dirname(inspect.getfile(self.__class__))
        if not config_file:
            config_file_search = [os.path.join(os.path.abspath(os.sep), "dgenies", "application.properties"),
                                  "/etc/dgenies/application.properties",
                                  "/etc/dgenies/application.properties.local",
                                  os.path.join(str(Path.home()), ".dgenies", "application.properties"),
                                  os.path.join(str(Path.home()), ".dgenies", "application.properties.local"),
                                  os.path.join(self.app_dir, '..', 'etc', 'dgenies', 'application.properties')]

            if os.name == "nt":
                config_file.insert(1, os.path.join(sys.executable, '..', "application.properties"))
                config_file.insert(1, os.path.join(sys.executable, '..', "application.properties.local"))

            for my_config_file in config_file_search:
                if os.path.exists(my_config_file):
                    config_file.append(my_config_file)

            config_file.append(os.path.join(self.app_dir, "application-dev.properties"))
            config_file.append(os.path.join(self.app_dir, "application-dev.properties.local"))

        config_file = [f for f in config_file if os.path.exists(f)]
        if len(config_file) == 0:
            raise FileNotFoundError("ERROR: application.properties not found.")
        self.reader = None
        self.reset_config(config_file)

    def _options_iterator(self) -> Iterator[tuple[str, Callable]]:
        """
        Iterator over self attributes related to configuration
        :return: iterator producing a tuple (attribute, callable)
        """
        for attr in dir(self):
            attr_o = getattr(self, attr)
            if attr.startswith("_get_") and callable(attr_o):
                yield attr[5:], attr_o

    def ___str___(self) -> str|None:
        """
        Representation of the configuration, except password attributes
        :return: string representation of self
        """
        try:
            return "\n".join((f"{attr}: {method()}" for attr, method in self._options_iterator() if "pass" not in attr))
        except Exception as e:
            print(e)

    def reset_config(self, config_files: list[Path|str]) -> None:
        """
        Override a previous configuration with new config files
        :param config_files: the list of config files. Parameters in last files override parameters in previous files.
        """
        self.reader = RawConfigParser()
        self.logger.info("Reset config")
        for f in config_files:
            self.logger.info("Override config with {}".format(f))
        self.reader.read(config_files)
        for attr, attr_o in self._options_iterator():
            try:
                setattr(self, attr, attr_o())
            except Exception as e:
                print(e)
        self.logger.info(self.___str___())

    def _replace_vars(self, path: str, config: bool=False) -> str:
        """
        In a path related to configuration, replaces each variable by its value
        :param path: the path.
        :param config: is the path is the config path?
        """
        new_path = path.replace("###USER###", os.path.expanduser("~"))\
            .replace("###PROGRAM###", os.path.dirname(os.path.dirname(os.path.realpath(__file__))))\
            .replace("###SYSEXEC###", os.path.dirname(sys.executable))
        if "###CONFIG###" in new_path:
            if config:
                raise Exception("###CONFIG### tag not allowed for config dir")
            else:
                return new_path.replace("###CONFIG###", self._get_config_dir())
        return new_path

    def _get_config_dir(self) -> str:
        try:
             config_dir = self._replace_vars(self.reader.get("global", "config_dir"))
        except NoOptionError:
            config_dir = self._replace_vars("###USER###/.dgenies")
        return os.getenv('CONFIG_DIR', config_dir)

    def _get_upload_folder(self) -> str:
        try:
            return os.getenv('UPLOAD_DIR', self._replace_vars(self.reader.get("global", "upload_folder")))
        except NoOptionError:
            raise Exception("No upload folder found in application.properties (global section)")

    def _get_app_data(self) -> str:
        try:
            return os.getenv('DATA_DIR', self._replace_vars(self.reader.get("global", "data_folder")))
        except NoOptionError:
            raise Exception("No data folder found in application.properties (global section)")

    def _get_runner_type(self) -> str:
        try:
            runner = os.getenv('RUNNER_TYPE')
            if runner is None:
                runner = self.reader.get("global", "runner_type")
            return runner
        except NoOptionError:
            return "local"

    def _get_web_url(self) -> str:
        try:
            web_url = self.reader.get("global", "web_url")
        except NoOptionError:
            web_url = "http://localhost:5000"
        return os.getenv('WEB_URL', web_url)

    def _get_send_mail_url(self) -> str:
        try:
            send_mail_url = self.reader.get("global", "send_mail_url")
        except NoOptionError:
            send_mail_url = self._get_web_url()
        return os.getenv('SEND_MAIL_URL', send_mail_url)

    @staticmethod
    def _parse_size(size_b: str) -> int:
        if size_b == "-1":
            return -1
        size_v = float(size_b[:-1])
        size_unit = size_b[-1].upper()
        if size_unit not in ["M", "G"]:
            raise ValueError("Max size unit must be M or G")
        size = int(size_v * 1024 * 1024)
        if size_unit == "G":
            size *= 1024
        return size

    def _get_max_upload_size(self) -> int:
        try:
            size = os.getenv('MAX_UPLOAD_SIZE')
            if size is None:
                size = self.reader.get("global", "max_upload_size")
            return self._parse_size(size)
        except NoOptionError:
            return -1

    def _get_max_upload_size_ava(self) -> int:
        try:
            size = os.getenv('MAX_UPLOAD_SIZE_AVA')
            if size is None:
                size = self.reader.get("global", "max_upload_size_ava")
            return self._parse_size(size)
        except NoOptionError:
            return -1

    def _get_max_upload_file_size(self) -> int:
        try:
            size = os.getenv('MAX_UPLOAD_FILE_SIZE')
            if size is None:
                size = self.reader.get("global", "max_upload_file_size")
            return self._parse_size(size)
        except NoOptionError:
            return 1024 * 1024 * 1024

    def _get_max_nb_lines(self) -> int:
        try:
            nb = os.getenv('MAX_NB_LINES')
            if nb is None:
                nb = self.reader.get("global", "max_nb_lines")
            return int(nb)
        except NoOptionError:
            return 100000

    def _get_max_nb_jobs_in_batch_mode(self) -> int:
        try:
            nb = os.getenv('MAX_NB_JOBS_IN_BATCH_MODE')
            if nb is None:
                nb = self.reader.get("global", "max_nb_jobs_in_batch_mode")
            return int(nb)
        except NoOptionError:
            return 10

    def _get_max_download_sessions(self) -> int:
        try:
            return int(self.reader.get("session", "max_download_sessions"))
        except NoOptionError:
            return 5

    def _get_delete_allowed_session_delay(self) -> int:
        try:
            return int(self.reader.get("session", "delete_allowed_session_delay"))
        except NoOptionError:
            return 50

    def _get_reset_pending_session_delay(self) -> int:
        try:
            return int(self.reader.get("session", "reset_pending_session_delay"))
        except NoOptionError:
            return 30

    def _get_delete_session_delay(self) -> int:
        try:
            return int(self.reader.get("session", "delete_session_delay"))
        except NoOptionError:
            return 86400

    def _get_database_type(self) -> str:
        try:
            db_type = self.reader.get("database", "type")
        except (NoSectionError, NoOptionError):
            db_type = "sqlite"
        return os.getenv('DATABASE_TYPE', db_type)

    def _get_database_url(self) -> str:
        try:
            url = self._replace_vars(self.reader.get("database", "url"))
            if self._get_database_type() == "sqlite" and url != ":memory:":
                parent_dir = os.path.dirname(url)
                if not os.path.exists(parent_dir):
                    try:
                        os.makedirs(parent_dir)
                    except FileNotFoundError:
                        pass
        except (NoSectionError, NoOptionError):
            url = self._replace_vars("###USER###/.dgenies/database.sqlite")
        return os.getenv('DATABASE_URL', url)

    def _get_database_port(self) -> int:
        try:
            db_type = self._get_database_type()
            if db_type == "sqlite":
               default_port = -1
            else:
                default_port = 3306
            if 'DATABASE_PORT' in os.environ:
                port = os.getenv('DATABASE_PORT', default_port)
            else:
                port = int(self.reader.get("database", "port"))
            return port
        except (NoSectionError, NoOptionError, ValueError):
            raise Exception("Missing parameter: database port")

    def _get_database_db(self) -> str:
        try:
            db = self.reader.get("database", "db")
            if db == "":
                raise ValueError()
            return db
        except (NoSectionError, NoOptionError, ValueError):
            db = os.getenv('DATABASE_BASE', "")
            if db or self._get_database_type() == "sqlite":
                return db
            raise Exception("Missing parameter: database db name")

    def _get_database_user(self) -> str:
        try:
            user = self.reader.get("database", "user")
            if user == "":
                raise ValueError()
            return user
        except (NoSectionError, NoOptionError, ValueError):
            user = os.getenv('DATABASE_USER', "")
            if user or self._get_database_type() == "sqlite":
                return user
            raise Exception("Missing parameter: database user")

    def _get_database_password(self) -> str:
        try:
            if 'DATABASE_PASSWORD' in os.environ:
                passwd = os.getenv('DATABASE_PASSWORD', "")
            else:
                passwd = self.reader.get("database", "password")
            if passwd == "":
                raise ValueError()
            return passwd
        except (NoSectionError, NoOptionError, ValueError):
            if passwd or self._get_database_type() == "sqlite":
                return ""
            raise Exception("Missing parameter: database password")

    def _get_mail_status_sender(self) -> str:
        try:
            return self.reader.get("mail", "status")
        except (NoSectionError, NoOptionError):
            return "status@dgenies"

    def _get_mail_reply(self) -> str:
        try:
            return self.reader.get("mail", "reply")
        except (NoSectionError, NoOptionError):
            return "status@dgenies"

    def _get_mail_org(self) -> str:
        try:
            return self.reader.get("mail", "org")
        except (NoSectionError, NoOptionError):
            return None

    def _get_send_mail_status(self) -> str:
        try:
            return self.reader.get("mail", "send_mail_status").lower() == "true"
        except (NoSectionError, NoOptionError):
            return True

    def _get_disable_mail(self) -> str:
        try:
            return self.reader.get("mail", "disable").lower() == "true"
        except (NoSectionError, NoOptionError):
            return False

    def _get_cron_clean_time(self) -> list[int]:
        try:
            value = self.reader.get("cron", "clean_time").lower()
            match = re.match(r"(([0-9])|([0-1][0-9])|(2[0-3]))[hH]([0-5][0-9])", value)
            if match is not None:
                return [int(match.group(1)), int(match.group(5))]
            else:
                print("Incorrect clean hour format!")
                return [1, 0]
        except (NoOptionError, NoSectionError):
            return [1, 0]

    def _get_cron_clean_freq(self) -> int:
        try:
            return int(self.reader.get("cron", "clean_freq"))
        except (NoOptionError, NoSectionError):
            return 1

    def _get_local_nb_runs(self) -> int:
        try:
            return int(self.reader.get("jobs", "run_local"))
        except (NoOptionError, NoSectionError):
            return 1

    def _get_nb_data_prepare(self) -> int:
        try:
            return int(self.reader.get("jobs", "data_prepare"))
        except (NoOptionError, NoSectionError):
            return 2

    def _get_max_concurrent_dl(self) -> int:
        try:
            return int(self.reader.get("jobs", "max_concurrent_dl"))
        except (NoOptionError, NoSectionError):
            return 5

    def _get_drmaa_lib_path(self) -> str|None:
        try:
            path = os.getenv('DRMAA_LIB_PATH')
            if path is None:
                path = self.reader.get("cluster", "drmaa_lib_path")
            if path != "###SET_IT###":
                return path
            return None
        except (NoOptionError, NoSectionError):
            if self._get_runner_type() != "local":
                raise Exception("No drmaa library set. It is required if the runner type is not 'local'")
            return None

    def _get_drmaa_native_specs(self) -> str:
        try:
            specs = os.getenv('DRMAA_NATIVE_SPECS')
            if specs is None:
                specs = self.reader.get("cluster", "native_specs")
            return specs
        except (NoOptionError, NoSectionError):
            return "###DEFAULT###"

    def _get_max_run_local(self) -> int:
        try:
            local = os.getenv('MAX_RUN_LOCAL')
            if local is None:
                local = self.reader.get("cluster", "max_run_local")
            return int(local)
        except (NoOptionError, NoSectionError):
            return 10

    def _get_max_wait_local(self) -> int:
        """
        Get the maximum number of jobs that can run on local runner
        """
        try:
            local = os.getenv('MAX_WAIT_LOCAL')
            if local is None:
                local = self.reader.get("cluster", "max_wait_local")
            return int(local)
        except (NoOptionError, NoSectionError):
            return 5

    def _get_min_query_size(self) -> int:
        """
        Get the query size limit above which a job must run on cluster
        """
        try:
            size_b = os.getenv('MIN_QUERY_SIZE')
            if size_b is None:
                size_b = self.reader.get("cluster", "min_query_size")
            return self._parse_size(size_b)
        except (NoOptionError, NoSectionError):
            return 0

    def _get_min_target_size(self) -> int:
        """
        Get the target size limit above which a job must run on cluster
        """
        try:
            size_b = os.getenv('MIN_TARGET_SIZE')
            if size_b is None:
                size_b = self.reader.get("cluster", "min_target_size")
            return self._parse_size(size_b)
        except (NoOptionError, NoSectionError):
            return 0

    def _get_cluster_prepare_script(self) -> str:
        """
        Get the (absolute) path to the all_prepare.py script
        """
        try:
            script = os.getenv('PREPARE_SCRIPT')
            if script is None:
                script = self.reader.get("cluster", "prepare_script")
            return self._replace_vars(script)
        except (NoOptionError, NoSectionError):
            return self._replace_vars("###PROGRAM###/bin/all_prepare.py")

    def _get_cluster_python_exec(self) -> str:
        """
        Get the python executable path on the cluster nodes.
        """
        try:
            python = os.getenv('PYTHON3_EXEC')
            if python is None:
                python = self.reader.get("cluster", "python3_exec")
            return self._replace_vars(python)
        except (NoOptionError, NoSectionError):
            return "python3"

    def _get_cluster_memory(self) -> int:
        """
        Get max memory in GiB to reserve on the cluster
        """
        try:
            memory = os.getenv('MAX_MEMORY')
            if memory is None:
                memory = self.reader.get("cluster", "memory")
            return int(memory)
        except (NoOptionError, NoSectionError):
            return 32

    def _get_cluster_memory_ava(self) -> int:
        """
        Get max memory in GiB to reserve on the cluster in all-vs-all mode
        """
        try:
            memory = os.getenv('MAX_MEMORY_AVA')
            if memory is None:
                memory = self.reader.get("cluster", "memory_ava")
            return int(memory)
        except (NoOptionError, NoSectionError):
            return self._get_cluster_memory()

    def _get_cluster_walltime(self) -> str:
        try:
            walltime = os.getenv('WALLTIME')
            if walltime is None:
                walltime = self.reader.get("cluster", "walltime")
            return walltime
        except (NoOptionError, NoSectionError):
            return "02:00:00"

    def _get_cluster_walltime_prepare(self) -> str:
        try:
            walltime = os.getenv('WALLTIME_PREPARE')
            if walltime is None:
                walltime = self.reader.get("cluster", "walltime_prepare")
            return walltime
        except (NoOptionError, NoSectionError):
            return self._get_cluster_walltime()

    def _get_cluster_walltime_align(self) -> str:
        try:
            walltime = os.getenv('WALLTIME_ALIGN')
            if walltime is None:
                walltime = self.reader.get("cluster", "walltime_align")
            return walltime
        except (NoOptionError, NoSectionError):
            return self._get_cluster_walltime()

    def _get_debug(self) -> bool:
        try:
            debug = os.getenv('DEBUG')
            if debug is None:
                debug = self.reader.get("debug", "enable")
            return debug.lower() in ["true", "1"]
        except (NoOptionError, NoSectionError):
            return False

    def _get_log_dir(self) -> str:
        try:
            log_dir = os.getenv('LOG_DIR')
            if log_dir is None:
                log_dir = self.reader.get("debug", "log_dir")
            log_dir = self._replace_vars(log_dir)
        except (NoOptionError, NoSectionError):
            log_dir = self._replace_vars("###CONFIG###/logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        elif not os.path.isdir(log_dir):
            raise TypeError("Log dir must be a directory")
        return log_dir

    def _get_allowed_ip_tests(self) -> set[str]:
        allowed_ip = {"127.0.0.1"}
        try:
            allowed_ip_txt = self.reader.get("debug", "allowed_ip_tests")
            for ip in re.split(r",(\s+)?", allowed_ip_txt):
                allowed_ip.add(ip)
        except (NoOptionError, NoSectionError):
            pass
        return allowed_ip

    def _get_example_query(self) -> str:
        try:
            example = os.getenv('EXAMPLE_QUERY')
            if example is None:
                example = self.reader.get("example", "query")
            return example
        except (NoOptionError, NoSectionError):
            return ""

    def _get_example_target(self) -> str:
        try:
            example = os.getenv('EXAMPLE_TARGET')
            if example is None:
                example = self.reader.get("example", "target")
            return example
        except (NoOptionError, NoSectionError):
            return ""

    def _get_example_backup(self) -> str:
        try:
            example = os.getenv('EXAMPLE_BACKUP')
            if example is None:
                self.reader.get("example", "backup")
            return example
        except (NoOptionError, NoSectionError):
            return ""

    def _get_example_batch(self) -> str:
        try:
            example = os.getenv('EXAMPLE_BATCH')
            if example is None:
                self.reader.get("example", "batch")
            return example
        except (NoOptionError, NoSectionError):
            return ""

    def _get_analytics_enabled(self) -> bool:
        try:
            analytics = os.getenv('ANALYTICS')
            if analytics is None:
                self.reader.get("analytics", "enable_logging_runs")
            return analytics.lower() in ["true", "1"]
        except (NoOptionError, NoSectionError):
            return False

    def _get_disable_anonymous_analytics(self) -> bool:
        try:
            disable = os.getenv('DISABLE_ANONYMOUS_ANALYTICS')
            if disable is None:
                disable = self.reader.get("analytics", "disable_anonymous_analytics")
            return not disable.lower() in ["true", "1"]
        except (NoOptionError, NoSectionError):
            return True

    def _get_anonymous_analytics(self) -> str:
        try:
            anon_strat = os.getenv('ANONYMOUS_ANALYTICS')
            if anon_strat is None:
                anon_strat = self.reader.get("analytics", "anonymous_analytics")
            return anon_strat.strip().lower()
        except (NoOptionError, NoSectionError):
            return "groups"

    def _get_analytics_groups(self) -> list[tuple[str, str]]:
        try:
            return [(option, self.reader.get("analytics_groups", option)) for option in self.reader.options("analytics_groups")]
        except (NoOptionError, NoSectionError):
            return []

    def _get_cookie_wall(self) -> str|None:
        try:
            return self.reader.get("legal", "cookie_wall")
        except (NoOptionError, NoSectionError):
            return None

    def _get_legal(self) -> dict[str, str]:
        try:
            return {option: self.reader.get("legal", option) for option in self.reader.options("legal")
                    if option not in ["cookie_wall"]}
        except (NoOptionError, NoSectionError):
            return {}
