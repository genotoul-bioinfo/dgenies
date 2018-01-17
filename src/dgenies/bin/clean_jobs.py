#!/usr/bin/env python3

import os
import sys
import shutil
import time
from _datetime import datetime, timedelta
import traceback
import argparse

from dgenies.config_reader import AppConfigReader
from dgenies.lib.functions import Functions
from dgenies.database import Job

config_reader = AppConfigReader()


def parse_upload_folders(upload_folder, now, max_age, fake=False):
    for file in os.listdir(upload_folder):
        file = os.path.join(upload_folder, file)
        create_date = os.path.getctime(file)
        age = (now - create_date) / 86400  # Age in days
        if age > max_age["uploads"]:
            try:
                if os.path.isdir(file):
                    print("Removing folder %s..." % file)
                    if not fake:
                        shutil.rmtree(file)
                else:
                    print("Removing file %s..." % file)
                    if not fake:
                        os.remove(file)
            except OSError:
                print(traceback.print_exc(), file=sys.stderr)


def parse_database(app_data, max_age, fake=False):
    # old_jobs = Job.select().where(
    #               ((Job.status == "success") & (Job.date_created < datetime.now() - timedelta(days=max_age["data"])))
    #               |
    #               ((Job.status != "success") & (Job.date_created < datetime.now() - timedelta(days=max_age["error"])))
    #           )
    old_jobs = Job.select({
        "status": ["==", "success"], "date_created": ["<", datetime.now() - timedelta(days=max_age["data"])]
    })
    old_jobs += Job.select({
        "status": ["!=", "success"], "date_created": ["<", datetime.now() - timedelta(days=max_age["error"])]
    })
    for job in old_jobs:
        id_job = job.id_job
        print("Removing job %s..." % id_job)
        if not fake:
            job.remove()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Clean old jobs and files")
    parser.add_argument('-f', '--fake', type=bool, const=True, nargs="?", required=False, default=False,
                        help="Fake mode: don't really delete the files (ONLY for debug)")
    parser.add_argument("-d", "--max-age", type=int, required=False, help="Max age of jobs to delete", default=7)
    args = parser.parse_args()
    fake = args.fake

    upload_folder = config_reader.upload_folder
    app_data = config_reader.app_data
    now = time.time()

    max_age = {
        "uploads": 1,
        "error": 1,
        "data": args.max_age,
        "fasta_sorted": 1
    }

    print("#########################")
    print("# Parsing Upload folder #")
    print("#########################")
    print("")
    parse_upload_folders(
        upload_folder=upload_folder,
        now=now,
        max_age=max_age,
        fake=fake
    )
    print("")

    print("######################")
    print("# Parsing Jobs in DB #")
    print("######################")
    print("")
    parse_database(
        app_data=app_data,
        max_age=max_age,
        fake=fake
    )
    print("")
