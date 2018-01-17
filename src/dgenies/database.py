import os
import json
import shutil
import operator
from dgenies.config_reader import AppConfigReader
from peewee import SqliteDatabase, Model, CharField, IntegerField, DateTimeField, BooleanField, MySQLDatabase
from datetime import datetime
import dateutil.parser

config = AppConfigReader()
db_url = config.database_url
db_type = config.database_type

if db_type == "sqlite":
    db = SqliteDatabase(db_url)
elif db_type == "mysql":
    db = MySQLDatabase(host=config.database_url, port=config.database_port, user=config.database_user,
                       passwd=config.database_password, database=config.database_db)
else:
    raise Exception("Unsupported database type: " + db_type)
db.connect()


class Job:
    config = AppConfigReader()

    def __init__(self, id_job: str):
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

    ##############
    # PROPERTIES #
    #############################

    @property
    def email(self):
        self.load()
        return self._j_email

    @email.setter
    def email(self, value):
        self.load()
        self._j_email = value

    @property
    def date_created(self):
        self.load()
        return self._j_date_created

    @date_created.setter
    def date_created(self, value):
        self.load()
        self._j_date_created = value

    @property
    def id_process(self):
        self.load()
        return self._j_id_process

    @id_process.setter
    def id_process(self, value):
        self.load()
        self._j_id_process = value

    @property
    def batch_type(self):
        self.load()
        return self._j_batch_type

    @batch_type.setter
    def batch_type(self, value):
        self.load()
        self._j_batch_type = value

    @property
    def status(self):
        self.load()
        return self._j_status

    @status.setter
    def status(self, value):
        self.change_status(value, False)

    @property
    def error(self):
        self.load()
        return self._j_error

    @error.setter
    def error(self, value):
        self.load()
        self._j_error = value

    @property
    def mem_peak(self):
        self.load()
        return self._j_mem_peak

    @mem_peak.setter
    def mem_peak(self, value):
        self.load()
        self._j_mem_peak = value

    @property
    def time_elapsed(self):
        self.load()
        return self._j_time_elapsed

    @time_elapsed.setter
    def time_elapsed(self, value):
        self.load()
        self._j_time_elapsed = value

    ###########
    # METHODS #
    #############################

    def new(self, email: str, batch_type: str="local", status: str="submitted", id_process: int=-1):
        props = locals()
        del props["self"]

        for prop, value in props.items():
            self.__setattr__("_j_" + prop, value)

        self._j_date_created = datetime.now()
        self._j_error = ""
        self._j_mem_peak = -1
        self._j_time_elapsed = -1

        self._loaded = True
        self.save()

        # Link in status dir:
        self._create_status_link()

    def load(self):
        if not self._loaded:
            with open(self._get_data_file(True), "r") as data:
                data = json.loads(data.read())
                for prop, value in data.items():
                    if prop.startswith("date_"):
                        self.__setattr__("_j_" + prop, dateutil.parser.parse(value))
                    else:
                        self.__setattr__("_j_" + prop, value)
                self._loaded = True

    def set(self, prop, value, save=False):
        if not self._loaded:
            self.load()
        c_prop = "_j_" + prop
        if hasattr(self, c_prop):
            if prop == "status":
                self._old_status = self._j_status
            self.__setattr__(c_prop, value)
            if save:
                self.save()
        raise AttributeError("Job has no property %s" % prop)

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
        self.load()
        self._old_status = self._j_status
        self._j_status = new_status
        if save:
            self.save()

    def remove(self):
        self.load()
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
            jobs = [Job(x) for x in os.listdir(config.app_data)]

        k = 0
        while k < len(jobs):
            job = jobs[k]
            try:
                job.load()
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

    @staticmethod
    def exists(id_job):
        app_data = Job.config.app_data
        job_dir = os.path.join(app_data, id_job)
        if os.path.exists(job_dir):
            if not os.path.isdir(job_dir):
                raise TypeError("Folder %s exists but is not a folder")
            return True
        return False

    @staticmethod
    def sort_jobs(jobs: "list of Job", key_sort):
        return sorted(jobs, key=lambda x: x.__getattribute__(key_sort))

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

    def _get_data_dir(self):
        return os.path.join(self.config.app_data, self.id_job)

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


class Session(Model):
    s_id = CharField(max_length=20, unique=True)
    date_created = DateTimeField()
    upload_folder = CharField(max_length=20)
    allow_upload = BooleanField(default=False)
    last_ping = DateTimeField()
    position = IntegerField(default=-1)
    keep_active = BooleanField(default=False)  # Uploads made by the server must be keep active

    @classmethod
    def new(cls, keep_active=False):
        from dgenies.lib.functions import Functions
        my_s_id = Functions.random_string(20)
        while len(cls.select().where(cls.s_id == my_s_id)) > 0:
            my_s_id = Functions.random_string(20)
        upload_folder = Functions.random_string(20)
        tmp_dir = config.upload_folder
        upload_folder_path = os.path.join(tmp_dir, upload_folder)
        while os.path.exists(upload_folder_path):
            upload_folder = Functions.random_string(20)
            upload_folder_path = os.path.join(tmp_dir, upload_folder)
        cls.create(s_id=my_s_id, date_created=datetime.now(), upload_folder=upload_folder, last_ping=datetime.now(),
                   keep_active=keep_active)
        return my_s_id

    def ask_for_upload(self, change_status=False):
        all_asked = Session.select().where(Session.position >= 0).order_by(Session.position)
        nb_asked = len(all_asked)
        if self.position == -1:
            if nb_asked == 0:
                position = 0
            else:
                position = all_asked[-1].position + 1
        else:
            change_status = False
            position = self.position

        allow_upload = self.allow_upload
        if not allow_upload and change_status and nb_asked < 5:
            allow_upload = True

        self.allow_upload = allow_upload
        self.position = position
        self.last_ping = datetime.now()
        self.save()

        return allow_upload, position

    def ping(self):
        self.last_ping = datetime.now()
        self.save()

    class Meta:
        database = db


if not Session.table_exists():
    Session.create_table()
