import os
import json
import shutil
import operator
from dgenies.config_reader import AppConfigReader
from datetime import datetime
import dateutil.parser


class Job:
    config = AppConfigReader()

    def __init__(self, id_job: str, _load=True):
        if os.path.sep in id_job:
            raise ValueError("Invalid caracter for job id: %s" % os.path.sep)
        self.id_job = id_job
        self._loaded = False
        self._j_email = None,
        self._j_date_created = None
        self._j_id_process = -1
        self._j_batch_type = "local"
        self._j_status = "submitted"
        self._j_error = ""
        self._j_mem_peak = -1
        self._j_time_elapsed = -1
        self._old_status = None
        if _load:
            self._load()

    ##############
    # PROPERTIES #
    #############################

    @property
    def email(self):
        return self._j_email

    @email.setter
    def email(self, value):
        self._j_email = value

    @property
    def date_created(self):
        return self._j_date_created

    @date_created.setter
    def date_created(self, value):
        self._j_date_created = value

    @property
    def id_process(self):
        return self._j_id_process

    @id_process.setter
    def id_process(self, value):
        self._j_id_process = value

    @property
    def batch_type(self):
        return self._j_batch_type

    @batch_type.setter
    def batch_type(self, value):
        self._j_batch_type = value

    @property
    def status(self):
        return self._j_status

    @status.setter
    def status(self, value):
        self.change_status(value, False)

    @property
    def error(self):
        return self._j_error

    @error.setter
    def error(self, value):
        self._j_error = value

    @property
    def mem_peak(self):
        return self._j_mem_peak

    @mem_peak.setter
    def mem_peak(self, value):
        self._j_mem_peak = value

    @property
    def time_elapsed(self):
        return self._j_time_elapsed

    @time_elapsed.setter
    def time_elapsed(self, value):
        self._j_time_elapsed = value

    @property
    def output_dir(self):
        return self._get_data_dir()

    ###########
    # METHODS #
    #############################

    @classmethod
    def new(cls, id_job: str, email: str, batch_type: str="local", status: str="submitted", id_process: int=-1):
        props = locals()
        del props["cls"]

        id_job_orig = id_job
        n = 2
        while cls.exists(id_job):
            id_job = "%s_%d" % (id_job_orig, n)
            n += 1

        job = Job(id_job, False)

        for prop, value in props.items():
            job.__setattr__("_j_" + prop, value)

        job._j_date_created = datetime.now()
        job._j_error = ""
        job._j_mem_peak = -1
        job._j_time_elapsed = -1

        job._loaded = True
        job.save()

        # Link in status dir:
        job._create_status_link()

        return job

    def save(self):
        if not self._loaded:
            raise NotInitialized("Job is not loaded")
        props = {}
        for attr in dir(self):
            if attr.startswith("_j_"):
                if attr.startswith("_j_date_"):
                    props[attr[3:]] = self.__getattribute__(attr).isoformat()
                else:
                    props[attr[3:]] = self.__getattribute__(attr)
        with open(self._get_data_file(), "w") as data:
            data.write(json.dumps(props))
        if self._old_status is not None:
            self._change_status_link()
            self._old_status = None

    @staticmethod
    def get_by_status(status):
        status_dir = Job._get_status_dir(status)
        if os.path.exists(status_dir) and os.path.isdir(status_dir):
            return [Job(x) for x in os.listdir(status_dir)]
        return []

    @staticmethod
    def get_by_statuses(statuses):
        jobs = []
        for status in statuses:
            jobs += Job.get_by_status(status)
        return jobs

    def change_status(self, new_status, save=True):
        self._old_status = self._j_status
        self._j_status = new_status
        if save:
            self.save()

    def remove(self):
        self._loaded = False
        job_dir = self._get_data_dir()
        if os.path.exists(job_dir) and os.path.isdir(job_dir):
            shutil.rmtree(job_dir)
        # Remove status link:
        status_link = self._get_status_link(self._j_status)
        if os.path.islink(status_link):
            os.remove(status_link)

    @staticmethod
    def select(properties: dict):
        """
        Select jobs with some properties
        :param properties: dict of properties with in values the value and the operator:
            {"prop1": [">", 25], "prop2": ["==", "success"], ...}
        :return:
        """
        ops = {
            "==": operator.eq,
            "!=": operator.ne,
            ">=": operator.ge,
            ">": operator.gt,
            "<=": operator.le,
            "<": operator.lt,
            "in": lambda a, b: a in b,
            "not in": lambda a, b: a not in b
        }

        if "id_job" in properties:
            jobs = [properties["id_job"]]
            del properties["id_job"]
        else:
            jobs = [Job(x, False) for x in os.listdir(Job.config.app_data)]

        k = 0
        while k < len(jobs):
            job = jobs[k]
            try:
                job._load()
            except (ValueError, TypeError):
                jobs.remove(job)
            else:
                match = True
                for my_property, value in properties.items():
                    if value[0] not in ops:
                        raise ValueError("Invalid operator: %s" % value[0])
                    try:
                        j_value = job.__getattribute__(my_property)
                    except AttributeError:
                        match = False
                        break
                    else:
                        if not ops[value[0]](j_value, value[1]):
                            match = False
                            break
                if not match:
                    jobs.remove(job)
                else:
                    k += 1

        return jobs

    @classmethod
    def exists(cls, id_job):
        app_data = cls.config.app_data
        job_dir = os.path.join(app_data, id_job)
        if os.path.exists(job_dir):
            if not os.path.isdir(job_dir):
                raise TypeError("Folder %s exists but is not a folder")
            return True
        return False

    @staticmethod
    def sort_jobs(jobs: "list of Job", key_sort):
        return sorted(jobs, key=lambda x: x.__getattribute__(key_sort))

    ###################
    # PRIVATE METHODS #
    #############################

    def _load(self):
        if not self._loaded:
            with open(self._get_data_file(True), "r") as data:
                data = json.loads(data.read())
                for prop, value in data.items():
                    if prop.startswith("date_"):
                        self.__setattr__("_j_" + prop, dateutil.parser.parse(value))
                    else:
                        self.__setattr__("_j_" + prop, value)
                self._loaded = True

    def _get_data_dir(self):
        return os.path.join(self.config.app_data, self.id_job)

    @staticmethod
    def _get_status_dir(status):
        return os.path.join(Job.config.app_data, "status", status)

    def _get_status_link(self, status):
        return os.path.join(self._get_status_dir(status), self.id_job)

    def _unlink_old_status(self):
        old_status_link = self._get_status_link(self._old_status)
        if os.path.islink(old_status_link):
            os.remove(old_status_link)

    def _create_status_link(self):
        new_status_dir = self._get_status_dir(self._j_status)
        if not os.path.exists(new_status_dir):
            os.makedirs(new_status_dir)
        os.symlink(self._get_data_dir(), self._get_status_link(self._j_status))

    def _change_status_link(self):
        if self._old_status is not None and self._old_status != self._j_status:
            self._unlink_old_status()
            self._create_status_link()
        self._old_status = None

    def _get_data_file(self, exists=False):
        job_dir = self._get_data_dir()

        if not os.path.exists(job_dir):
            if exists:
                raise DoesNotExist("Job %s does not exists" % self.id_job)
            os.makedirs(job_dir)
        elif not os.path.isdir(job_dir):
            raise TypeError("Job dir %s is not a directory!" % job_dir)

        job_data = os.path.join(job_dir, ".data")

        if exists and (not os.path.exists(job_data) or not os.path.isfile(job_data)):
            raise ValueError("Data file %s does not exists or is not a file!" % job_data)

        return job_data


class NotInitialized(Exception):
    pass


class DoesNotExist(Exception):
    pass


class Session:
    config = AppConfigReader()
    allowed_statuses = ["reset", "pending", "active"]

    def __init__(self, s_id=None, _load=True):
        self.s_id = s_id
        self._s_date_created = None
        self._s_status = "reset"
        self._s_upload_folder = None
        self._s_date_last_ping = None
        self._s_position = -1
        self._s_keep_active = False
        self._old_status = None
        self._loaded = False
        if _load:
            self._load()

    ##############
    # PROPERTIES #
    #############################

    @property
    def upload_folder(self):
        return self._s_upload_folder

    @property
    def last_ping(self):
        return self._s_date_last_ping

    @property
    def keep_active(self):
        return self._s_keep_active

    ###########
    # METHODS #
    #############################

    @staticmethod
    def new(keep_active=False, status="reset"):
        from dgenies.lib.functions import Functions
        my_s_id = Functions.random_string(20)
        session = Session(my_s_id, False)
        while session.exists():
            my_s_id = Functions.random_string(20)
            session = Session(my_s_id)
        upload_folder = Functions.random_string(20)
        tmp_dir = Session.config.upload_folder
        upload_folder_path = os.path.join(tmp_dir, upload_folder)
        while os.path.exists(upload_folder_path):
            upload_folder = Functions.random_string(20)
            upload_folder_path = os.path.join(tmp_dir, upload_folder)
        session._s_date_created = datetime.now()
        session._s_status = status
        session._s_upload_folder = upload_folder
        session._s_date_last_ping = datetime.now()
        session._s_keep_active = keep_active
        session._loaded = True
        session.save()
        session._create_status_link()
        return session

    def save(self):
        if not self._loaded:
            raise NotInitialized("Session is not loaded")
        props = {}
        for attr in dir(self):
            if attr.startswith("_s_"):
                if attr.startswith("_s_date_"):
                    props[attr[3:]] = self.__getattribute__(attr).isoformat()
                else:
                    props[attr[3:]] = self.__getattribute__(attr)
        with open(self._get_session_file(), "w") as data:
            data.write(json.dumps(props))
        if self._old_status is not None:
            self._change_status_link()
            self._old_status = None

    def change_status(self, new_status, save=True):
        if new_status in Session.allowed_statuses:
            if self._s_status != new_status:
                self._old_status = self._s_status
                self._s_status = new_status
                if save:
                    self.save()
        else:
            raise ValueError("Invalid status: %s" % new_status)

    @staticmethod
    def get_by_status(status):
        """
        Get all Session objects with a given status
        :param status:
        :return: list of Session objects
        """
        status_dir = Session._get_session_status_dir(status)
        return [Session(x) for x in os.listdir(status_dir)]

    @staticmethod
    def get_by_statuses(statuses):
        """
        Get all Session objects with status in the given list
        :param statuses: list of accepted statuses
        :return: list of Session objects
        """
        sessions = []
        for status in statuses:
            sessions += Session.get_by_status(status)
        return sessions

    @classmethod
    def all(cls):
        """
        Get all Session objects, with any status
        :return: list of Session objects
        """
        session_dir = Session._get_session_dir()
        return [Session(x) for x in os.listdir(session_dir) if x != "status"]

    def ask_for_upload(self, change_status=False):
        all_asked = self.get_by_statuses(["pending", "active"])
        nb_asked = len(all_asked)
        if self._s_position == -1:
            if nb_asked == 0:
                position = 0
            else:
                position = all_asked[-1].position + 1
        else:
            change_status = False
            position = self._s_position

        status = "pending"
        if self._s_status == "active" or (change_status and nb_asked < 5):
            status = "active"

        if status != self._s_status:
            self.change_status(status, False)
        self._s_position = position
        self._s_date_last_ping = datetime.now()
        self.save()

        return status == "active", position

    def ping(self):
        self._s_date_last_ping = datetime.now()
        self.save()

    def exists(self):
        s_file = self._get_session_file()
        return os.path.exists(s_file) and os.path.isfile(s_file)

    def remove(self):
        # We check in all available status (to be sure we delete all):
        os.remove(self._get_session_file())
        os.remove(self._get_session_status_file(self._s_status))
        self._loaded = False

    def reset(self):
        self.change_status("reset", False)
        self._s_position = -1
        self.save()

    def enable(self):
        self.change_status("active", True)

    @staticmethod
    def sort_sessions(sessions: "list of Sessions", key_sort):
        return sorted(sessions, key=lambda x: x.__getattribute__("_s_" + key_sort))

    ###################
    # PRIVATE METHODS #
    #############################

    def _load(self):
        if not self._loaded:
            with open(self._get_session_file(True), "r") as data_f:
                data = json.loads(data_f.read())
                for prop, value in data.items():
                    attr = "_s_" + prop
                    if hasattr(self, attr):
                        if prop.startswith("date_"):
                            self.__setattr__(attr, dateutil.parser.parse(value))
                        else:
                            self.__setattr__(attr, value)
                    else:
                        raise ValueError("Invalid property: %s" % prop)
            self._loaded = True

    @staticmethod
    def _get_session_dir():
        s_dir = os.path.join(Session.config.app_data, "sessions")
        if not os.path.exists(s_dir):
            os.makedirs(s_dir)
        return s_dir

    def _get_session_file(self, exists=False):
        s_file = os.path.join(self._get_session_dir(), self.s_id)
        if not os.path.exists(s_file) and exists:
            raise DoesNotExist("Session %s does not exists" % self.s_id)
        return s_file

    @staticmethod
    def _get_session_status_dir(status):
        status_dir = os.path.join(Session._get_session_dir(), "status", status)
        if not os.path.exists(status_dir):
            os.makedirs(status_dir)
        return status_dir

    def _get_session_status_file(self, status):
        return os.path.join(self._get_session_status_dir(status), self.s_id)

    def _unlink_old_status(self):
        old_status_link = self._get_session_status_file(self._old_status)
        if os.path.islink(old_status_link):
            os.remove(old_status_link)

    def _create_status_link(self):
        new_status_dir = self._get_session_status_dir(self._s_status)
        if not os.path.exists(new_status_dir):
            os.makedirs(new_status_dir)
        os.symlink(self._get_session_file(), self._get_session_status_file(self._s_status))

    def _change_status_link(self):
        if self._old_status is not None and self._old_status != self._s_status:
            self._unlink_old_status()
            self._create_status_link()
        self._old_status = None
