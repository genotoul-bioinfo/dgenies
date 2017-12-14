from config_reader import AppConfigReader
from peewee import SqliteDatabase, Model, CharField, IntegerField, DateTimeField

config = AppConfigReader()
file_path = config.database

db = SqliteDatabase(file_path)
db.connect()


class Job(Model):
    id_job = CharField(max_length=50)
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


if not Job.table_exists():
    Job.create_table()
