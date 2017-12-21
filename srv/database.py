import os
from config_reader import AppConfigReader
from peewee import SqliteDatabase, Model, CharField, IntegerField, DateTimeField, BooleanField
from datetime import datetime

config = AppConfigReader()
file_path = config.database

db = SqliteDatabase(file_path)
db.connect()


class Job(Model):
    id_job = CharField(max_length=50, unique=True)
    email = CharField()
    id_process = IntegerField(null=True)
    batch_type = CharField(max_length=20, default="local")
    status = CharField(max_length=20, default="submitted")
    date_created = DateTimeField()
    error = CharField(default="")
    mem_peak = IntegerField(null=True)
    time_elapsed = IntegerField(null=True)

    class Meta:
        database = db


class Session(Model):
    s_id = CharField(max_length=20, unique=True)
    date_created = DateTimeField()
    upload_folder = CharField(max_length=20)
    allow_upload = BooleanField(default=False)
    last_ping = DateTimeField()
    position = IntegerField(default=-1)

    @classmethod
    def new(cls):
        from lib.functions import Functions
        my_s_id = Functions.random_string(20)
        while len(cls.select().where(cls.s_id == my_s_id)) > 0:
            my_s_id = Functions.random_string(20)
        upload_folder = Functions.random_string(20)
        tmp_dir = config.upload_folder
        upload_folder_path = os.path.join(tmp_dir, upload_folder)
        while os.path.exists(upload_folder_path):
            upload_folder = Functions.random_string(20)
            upload_folder_path = os.path.join(tmp_dir, upload_folder)
        cls.create(s_id=my_s_id, date_created=datetime.now(), upload_folder=upload_folder, last_ping=datetime.now())
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
        if change_status and nb_asked < 5:
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


if not Job.table_exists():
    Job.create_table()

if not Session.table_exists():
    Session.create_table()
