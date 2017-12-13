#!/usr/bin/env python3

import os
import sys
import shutil
import time
from _datetime import datetime, timedelta
import traceback
import argparse

app_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "srv")
sys.path.insert(0, app_folder)

from config_reader import AppConfigReader
from lib.functions import Functions
from database import Job

config_reader = AppConfigReader()

UPLOAD_FOLDER = config_reader.upload_folder
APP_DATA = config_reader.app_data
NOW = time.time()
FAKE = False

max_age = {
    "uploads": 1,
    "error": 1,
    "data": 7,
    "fasta_sorted": 1
}


def parse_upload_folders():
    for file in os.listdir(UPLOAD_FOLDER):
        file = os.path.join(UPLOAD_FOLDER, file)
        create_date = os.path.getctime(file)
        age = (NOW - create_date) / 86400  # Age in days
        if age > max_age["uploads"]:
            try:
                if os.path.isdir(file):
                    print("Removing folder %s..." % file)
                    if not FAKE:
                        shutil.rmtree(file)
                else:
                    print("Removing file %s..." % file)
                    if not FAKE:
                        os.remove(file)
            except OSError:
                print(traceback.print_exc(), file=sys.stderr)


def parse_database():
    old_jobs = Job.select().where(
                  ((Job.status == "success") & (Job.date_created < datetime.now() - timedelta(days=max_age["data"])))
                  |
                  ((Job.status != "success") & (Job.date_created < datetime.now() - timedelta(days=max_age["error"])))
              )
    for job in old_jobs:
        id_job = job.id_job
        print("Removing job %s..." % id_job)
        data_dir = os.path.join(APP_DATA, id_job)
        if os.path.exists(data_dir) and os.path.isdir(data_dir):
            if not FAKE:
                shutil.rmtree(data_dir)
        else:
            print("Job %s has no data folder!" % id_job)
        if not FAKE:
            job.delete_instance()


def parse_data_folders():
    for file in os.listdir(APP_DATA):
        file = os.path.join(APP_DATA, file)
        create_date = os.path.getctime(file)
        age = (NOW - create_date) / 86400  # Age in days
        if age > max_age["data"]:
            try:
                if os.path.isdir(file):
                    print("Removing folder %s..." % file)
                    if not FAKE:
                        shutil.rmtree(file)
                else:
                    print("Removing file %s..." % file)
                    if not FAKE:
                        os.remove(file)
            except OSError:
                print(traceback.print_exc())
        elif os.path.isdir(file):
            query_name_file = os.path.join(file, ".query")
            if os.path.exists(query_name_file):
                with open(query_name_file) as query_file:
                    sorted_file = Functions.get_fasta_file(file, "query", True)
                    if not sorted_file.endswith(".sorted"):
                        sorted_file = None
                    if sorted_file is not None:
                        create_date = os.path.getctime(sorted_file)
                        age = (NOW - create_date) / 86400  # Age in days
                        if age > max_age["fasta_sorted"]:
                            print("Removing fasta file %s..." % sorted_file)
                            if not FAKE:
                                os.remove(sorted_file)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Clean old jobs and files")
    parser.add_argument('-f', '--fake', type=bool, const=True, nargs="?", required=False, default=False,
                        help="Fake mode: don't really delete the files (ONLY for debug)")
    args = parser.parse_args()
    FAKE = args.fake
    if FAKE:
        print("RUNNING IN FAKE MODE...")
        print("")

    print("#########################")
    print("# Parsing Upload folder #")
    print("#########################")
    print("")
    parse_upload_folders()
    print("")

    print("######################")
    print("# Parsing Jobs in DB #")
    print("######################")
    print("")
    parse_database()
    print("")

    print("#######################")
    print("# Parsing Data folder #")
    print("#######################")
    print("")
    parse_data_folders()
    print("")
