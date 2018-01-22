import os
import json
from json.decoder import JSONDecodeError
import shutil
import operator
from dgenies.config_reader import AppConfigReader
from datetime import datetime
import time
import dateutil.parser
import threading
import abc


class Database:

    _ops = {
        "==": operator.eq,
        "!=": operator.ne,
        ">=": operator.ge,
        ">": operator.gt,
        "<=": operator.le,
        "<": operator.lt,
        "in": lambda a, b: a in b,
        "not in": lambda a, b: a not in b
    }

    def __init__(self, d_id, type):
        self.id = d_id
        self.type = type

    @abc.abstractmethod
    def _get_lock_write_file(self):
        return ""

    def _lock_write(self):
        lock_file = self._get_lock_write_file()
        locked = False
        tries = 0
        while not locked and tries < 50:
            try:
                with open(lock_file, "x") as lock_f:
                    lock_f.write(datetime.now().isoformat())
                locked = True
            except FileExistsError:
                time.sleep(0.05)
                tries += 1
        if not locked:
            raise LockError("Unable to lock %s %s" % (self.type, self.id))

    def _unlock_write(self):
        lock_file = self._get_lock_write_file()
        if os.path.exists(lock_file):
            os.remove(lock_file)


class Job(Database):
    config = AppConfigReader()

    def __init__(self, id_job: str, _load=True):
        if os.path.sep in id_job:
            raise ValueError("Invalid caracter for job id: %s" % os.path.sep)
        super().__init__(id_job, "job")
        self.id_job = self.id
        self._changes = []
        self._loaded = False
        # !!!
        # WARN!!!! Never change _j_ attributes values directly, use properties instead
        # !!!
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
        self._changes.append("email")

    @property
    def date_created(self):
        return self._j_date_created

    @date_created.setter
    def date_created(self, value):
        self._j_date_created = value
        self._changes.append("date_created")

    @property
    def id_process(self):
        return self._j_id_process

    @id_process.setter
    def id_process(self, value):
        self._j_id_process = value
        self._changes.append("id_process")

    @property
    def batch_type(self):
        return self._j_batch_type

    @batch_type.setter
    def batch_type(self, value):
        self._j_batch_type = value
        self._changes.append("batch_type")

    @property
    def status(self):
        return self._j_status

    @status.setter
    def status(self, value):
        self._j_status = value
        self._changes.append("status")

    @property
    def error(self):
        return self._j_error

    @error.setter
    def error(self, value):
        self._j_error = value
        self._changes.append("error")

    @property
    def mem_peak(self):
        return self._j_mem_peak

    @mem_peak.setter
    def mem_peak(self, value):
        self._j_mem_peak = value
        self._changes.append("mem_peak")

    @property
    def time_elapsed(self):
        return self._j_time_elapsed

    @time_elapsed.setter
    def time_elapsed(self, value):
        self._j_time_elapsed = value
        self._changes.append("time_elapsed")

    @property
    def output_dir(self):
        return self._get_data_dir()

    ###########
    # METHODS #
    #############################

    @classmethod
    def new(cls, id_job: str, email: str, batch_type: str="local", status: str="submitted", id_process: int=-1):
        """
        Create a new job
        Note: it's the only method we can change _j_ attributes directly
        :param id_job:
        :param email:
        :param batch_type:
        :param status:
        :param id_process:
        :return:
        """
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
        job.save(False)

        # Link in status dir:
        job._create_status_link()

        return job

    def save(self, exists=True):
        if not self._loaded:
            raise NotInitialized("Job is not loaded")
        props = {}
        for attr in dir(self):
            if attr.startswith("_j_"):
                if attr.startswith("_j_date_"):
                    props[attr[3:]] = self.__getattribute__(attr).isoformat()
                else:
                    props[attr[3:]] = self.__getattribute__(attr)
        data_file = self._get_data_file()
        if exists and not os.path.exists(data_file):
            raise DoesNotExist("Job does not exists anymore")
        if exists:
            self._lock_write()
            data = self._get_data()
            if "status" in self._changes:
                self._old_status = data["status"]
            else:
                self._old_status = None
            for prop in self._changes:
                data[prop] = props[prop]
            with open(data_file, "w") as data_f:
                data_f.write(json.dumps(data))
            self._unlock_write()
        else:
            with open(data_file, "w") as data:
                data.write(json.dumps(props))
        if self._old_status is not None:
            self._change_status_link()
            self._old_status = None

    @staticmethod
    def get_by_status(status):
        status_dir = Job._get_status_dir(status)
        if os.path.exists(status_dir) and os.path.isdir(status_dir):
            jobs = []
            for folder in os.listdir(status_dir):
                try:
                    jobs.append(Job(folder))
                except DoesNotExist:
                    pass
            return jobs
        return []

    @staticmethod
    def get_by_statuses(statuses):
        jobs = []
        for status in statuses:
            jobs += Job.get_by_status(status)
        return jobs

    def change_status(self, new_status, save=True):
        self.status = new_status
        if save:
            self.save()

    def remove(self, safe=True):
        self._loaded = False
        job_dir = self._get_data_dir()
        if os.path.exists(job_dir) and os.path.isdir(job_dir):
            shutil.rmtree(job_dir)
        # Remove status link:
        status_link = self._get_status_link(self.status)
        if os.path.islink(status_link):
            os.remove(status_link)
        if safe:
            thread = threading.Timer(2, self.remove, kwargs={"safe": False})
            thread.start()

    @classmethod
    def select(cls, properties: dict):
        """
        Select jobs with some properties
        :param properties: dict of properties with in values the value and the operator:
            {"prop1": [">", 25], "prop2": ["==", "success"], ...}
        :return:
        """

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
            except (ValueError, TypeError, DoesNotExist):
                jobs.remove(job)
            else:
                match = True
                for my_property, value in properties.items():
                    if value[0] not in cls._ops:
                        raise ValueError("Invalid operator: %s" % value[0])
                    try:
                        j_value = job.__getattribute__(my_property)
                    except AttributeError:
                        match = False
                        break
                    else:
                        if not cls._ops[value[0]](j_value, value[1]):
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
            try:
                Job(id_job)
                return True
            except (ValueError, TypeError, DoesNotExist):
                return False
        return False

    @staticmethod
    def sort_jobs(jobs: "list of Job", key_sort):
        return sorted(jobs, key=lambda x: x.__getattribute__(key_sort))

    ###################
    # PRIVATE METHODS #
    #############################

    def _get_data(self):
        j_file = self._get_data_file(True)
        i = 0
        while i < 50:
            if not os.path.exists(j_file):
                raise DoesNotExist("Job does not exists or is not initialized")
            try:
                with open(j_file, "r") as data:
                    return json.loads(data.read())
            except JSONDecodeError:
                time.sleep(0.05)
                i += 1
        raise DoesNotExist("Job does not exists or is not initialized")

    def _load(self):
        if not self._loaded:
            data = self._get_data()
            for prop, value in data.items():
                if prop.startswith("date_"):
                    self.__setattr__("_j_" + prop, dateutil.parser.parse(value))
                else:
                    self.__setattr__("_j_" + prop, value)
            self._loaded = True

    def _get_lock_write_file(self):
        lock_dir = os.path.join(self._get_data_dir(), "lock")
        if not os.path.exists(lock_dir):
            os.makedirs(lock_dir)
        return os.path.join(lock_dir, self.id_job)

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
        new_status_dir = self._get_status_dir(self.status)
        if not os.path.exists(new_status_dir):
            os.makedirs(new_status_dir)
        os.symlink(self._get_data_dir(), self._get_status_link(self.status))

    def _change_status_link(self):
        if self._old_status is not None and self._old_status != self.status:
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


class Session(Database):
    config = AppConfigReader()
    allowed_statuses = ["reset", "pending", "active"]

    def __init__(self, s_id=None, _load=True):
        super().__init__(s_id, "session")
        self.s_id = self.id
        self._changes = []
        # !!!
        # WARN!!!! Never change _s_ attributes values directly, use properties instead
        # !!!
        self._s_date_created = None
        self._s_status = "reset"
        self._s_upload_folder = None
        self._s_date_last_ping = None
        self._s_keep_active = False
        self._old_status = None
        self._loaded = False
        if _load:
            self._load()

    ##############
    # PROPERTIES #
    #############################

    @property
    def date_created(self):
        return self._s_date_created

    @date_created.setter
    def date_created(self, value):
        self._s_date_created = value
        self._changes.append("date_created")

    @property
    def status(self):
        return self._s_status

    @status.setter
    def status(self, value):
        if value in Session.allowed_statuses:
            self._s_status = value
            self._changes.append("status")
        else:
            raise ValueError("Invalid status: %s" % value)

    @property
    def upload_folder(self):
        return self._s_upload_folder

    @upload_folder.setter
    def upload_folder(self, value):
        self._s_upload_folder = value
        self._changes.append("upload_folder")

    @property
    def last_ping(self):
        return self._s_date_last_ping

    @last_ping.setter
    def last_ping(self, value):
        self._s_date_last_ping = value
        self._changes.append("date_last_ping")

    @property
    def keep_active(self):
        return self._s_keep_active

    @keep_active.setter
    def keep_active(self, value):
        self._s_keep_active = value
        self._changes.append("keep_active")

    ###########
    # METHODS #
    #############################

    @staticmethod
    def new(keep_active=False, status="reset"):
        """
        Create a new session
        Note: it's the only function we can change _s_ attributes directly
        :param keep_active:
        :param status:
        :return:
        """
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
        session.save(False)
        session._create_status_link()
        return session

    def save(self, exists=True):
        if not self._loaded:
            raise NotInitialized("Session is not loaded")
        props = {}
        for attr in dir(self):
            if attr.startswith("_s_"):
                if attr.startswith("_s_date_"):
                    props[attr[3:]] = self.__getattribute__(attr).isoformat()
                else:
                    props[attr[3:]] = self.__getattribute__(attr)
        s_file = self._get_session_file()
        if exists and not os.path.exists(s_file):
            raise DoesNotExist("Session does not exists anymore")
        if exists:
            self._lock_write()
            data = self._get_data()
            if "status" in self._changes:
                self._old_status = data["status"]
            else:
                self._old_status = None
            for prop in self._changes:
                data[prop] = props[prop]
            with open(s_file, "w") as data_f:
                data_f.write(json.dumps(data))
            self._unlock_write()
        else:
            with open(s_file, "w") as data:
                data.write(json.dumps(props))
        if self._old_status is not None:
            self._change_status_link()
            self._old_status = None
        self._changes = []

    def change_status(self, new_status, save=True):
        self.status = new_status
        if save:
            self.save()

    @classmethod
    def get_by_status(cls, status, conditions=()):
        """
        Get all Session objects with a given status
        :param status:
        :param conditions: list of conditions to apply to selection
        :return: list of Session objects
        """
        status_dir = Session._get_session_status_dir(status)
        sessions = []
        for file in os.listdir(status_dir):
            try:
                session = Session(file)
                accept = True
                for condition in conditions:
                    if condition[1] not in cls._ops:
                        raise ValueError("Invalid operator: %s" % condition[1])
                    try:
                        s_value = session.__getattribute__(condition[0])
                    except AttributeError:
                        accept = False
                        break
                    else:
                        if not cls._ops[condition[1]](s_value, condition[2]):
                            accept = False
                            break
                if accept:
                    sessions.append(session)
            except DoesNotExist:
                pass
        return sessions

    @classmethod
    def get_by_statuses(cls, statuses, conditions=()):
        """
        Get all Session objects with status in the given list
        :param statuses: list of accepted statuses
        :param conditions: list of conditions to apply to selection
        :return: list of Session objects
        """
        sessions = []
        for status in statuses:
            sessions += cls.get_by_status(status, conditions)
        return sessions

    @classmethod
    def all(cls):
        """
        Get all Session objects, with any status
        :return: list of Session objects
        """
        session_dir = Session._get_session_dir()
        sessions = []
        for file in os.listdir(session_dir):
            if file not in ["status", "lock"]:
                try:
                    sessions.append(Session(file))
                except DoesNotExist:
                    pass
        return sessions

    def ask_for_upload(self, change_status=False):
        all_asked = self.get_by_statuses(["pending", "active"], [["date_created", "<=", self.date_created]])
        nb_asked = len(all_asked)
        if self.status != "reset":
            change_status = False

        status = "pending"
        if self.status == "active" or (change_status and nb_asked < 5):
            status = "active"

        if status != self.status:
            self.status = status
        self.last_ping = datetime.now()
        self.save()

        return status == "active"

    def ping(self):
        self.last_ping = datetime.now()
        self.save()

    def exists(self):
        s_file = self._get_session_file()
        return os.path.exists(s_file) and os.path.isfile(s_file)

    def remove(self, safe=True):
        # We check in all available status (to be sure we delete all):
        try:
            os.remove(self._get_session_file())
        except FileNotFoundError:
            pass
        status_file = self._get_session_status_file(self.status)
        if os.path.islink(status_file):
            os.remove(status_file)
        self._loaded = False
        if safe:
            thread = threading.Timer(1, self.remove, kwargs={"safe": False})
            thread.start()

    def reset(self):
        self.status = "reset"
        self.save()

    def enable(self):
        self.change_status("active", True)

    @staticmethod
    def sort_sessions(sessions: "list of Sessions", key_sort):
        return sorted(sessions, key=lambda x: x.__getattribute__("_s_" + key_sort))

    ###################
    # PRIVATE METHODS #
    #############################

    def _get_lock_write_file(self):
        lock_dir = os.path.join(self._get_session_dir(), "lock")
        if not os.path.exists(lock_dir):
            os.makedirs(lock_dir)
        return os.path.join(lock_dir, self.s_id)

    def _get_data(self):
        s_file = self._get_session_file(True)
        i = 0
        while i < 50:
            if not os.path.exists(s_file):
                raise DoesNotExist("Session has been deleted")
            try:
                with open(s_file, "r") as data_f:
                    return json.loads(data_f.read())
            except JSONDecodeError:
                time.sleep(0.05)
                i += 1
        raise DoesNotExist("Session does not exists or is not initialized")

    def _load(self):
        if not self._loaded:
            data = self._get_data()
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
        new_status_dir = self._get_session_status_dir(self.status)
        if not os.path.exists(new_status_dir):
            os.makedirs(new_status_dir)
        os.symlink(self._get_session_file(), self._get_session_status_file(self.status))

    def _change_status_link(self):
        if self._old_status is not None and self._old_status != self.status:
            self._unlink_old_status()
            self._create_status_link()
        self._old_status = None


class LockError(Exception):
    pass
