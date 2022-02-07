from dgenies import MODE

import os
from dgenies.config_reader import AppConfigReader
from datetime import datetime

config = AppConfigReader()

if MODE == "webserver":
    from peewee import SqliteDatabase, Model, CharField, IntegerField, DateTimeField, BooleanField, MySQLDatabase, \
    OperationalError, ForeignKeyField, __exception_wrapper__

    db_url = config.database_url
    db_type = config.database_type

    # restore RetryOperationalError from peewee 2.10.x
    # https://github.com/coleifer/peewee/issues/1472
    class RetryOperationalError(object):

        def execute_sql(self, sql, params=None, commit=True):
            try:
                cursor = super(RetryOperationalError, self).execute_sql(
                    sql, params, commit)
            except OperationalError:
                if not self.is_closed():
                    self.close()
                with __exception_wrapper__:
                    cursor = self.cursor()
                    cursor.execute(sql, params or ())
                    if commit and not self.in_transaction():
                        self.commit()
            return cursor


    class MyRetryDB(RetryOperationalError, MySQLDatabase):
        pass


    if db_type == "sqlite":
        db = SqliteDatabase(db_url)
    elif db_type == "mysql":
        db = MyRetryDB(host=config.database_url, port=config.database_port, user=config.database_user,
                       passwd=config.database_password, database=config.database_db)
    else:
        raise Exception("Unsupported database type: " + db_type)


    class Database:

        nb_open = 0

        def __init__(self):
            pass

        def __enter__(self):
            Database.nb_open += 1
            try:
                db.connect()
            except OperationalError:
                pass

        def __exit__(self, exc_type, exc_val, exc_tb):
            Database.nb_open -= 1
            if Database.nb_open == 0:
                db.close()


    class BaseModel(Model):

        class Meta:
            database = db

        @classmethod
        def connect(cls):
            return Database()


    class Job(BaseModel):
        id_job = CharField(max_length=50, unique=True)
        email = CharField()
        id_process = IntegerField(null=True)
        batch_type = CharField(max_length=20, default="local")
        status = CharField(max_length=20, default="submitted")
        date_created = DateTimeField()
        error = CharField(default="")
        mem_peak = IntegerField(null=True)
        time_elapsed = IntegerField(null=True)
        tool = CharField(default="minimap2", max_length=50, null=True)
        options = CharField(max_length=127, null=True)


    class Gallery(BaseModel):
        job = ForeignKeyField(Job)
        name = CharField()
        query = CharField()
        target = CharField()
        picture = CharField()


    class Session(BaseModel):
        s_id = CharField(max_length=20, unique=True)
        date_created = DateTimeField()
        upload_folder = CharField(max_length=20)
        last_ping = DateTimeField()
        status = CharField(default="reset")
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
            all_asked = Session.select().where((Session.status == "pending") | (Session.status == "active")).\
                order_by(Session.date_created)
            nb_asked = len(all_asked)
            if self.status != "reset":
                change_status = False

            status = "pending"
            if self.status == "active" or (change_status and nb_asked < 5):
                status = "active"

            self.status = status
            self.last_ping = datetime.now()
            self.save()

            return self.status == "active"

        def ping(self):
            self.last_ping = datetime.now()
            self.save()


    if config.analytics_enabled:

        class Analytics(BaseModel):
            id_job = CharField(max_length=50, default="unknown")
            date_created = DateTimeField()
            target_size = IntegerField()
            query_size = IntegerField(null=True)
            mail_client = CharField()
            batch_type = CharField(max_length=20)
            job_type = CharField(max_length=5, default="unk")
            status = CharField(max_length=20, default="unknown")
            tool = CharField(default="undefined", max_length=50, null=True)

        if not Analytics.table_exists():
            Analytics.create_table()

    if not Job.table_exists():
        Job.create_table()

    if not Gallery.table_exists():
        Gallery.create_table()

    if not Session.table_exists():
        Session.create_table()

else:

    class Database:

        nb_open = 0

        def __init__(self):
            pass

        def __enter__(self):
            pass

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    class Job:

        @classmethod
        def connect(cls):
            return Database()