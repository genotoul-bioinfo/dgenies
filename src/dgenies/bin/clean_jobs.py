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

config_reader = AppConfigReader()


def parse_upload_folders(upload_folder, now, max_age, fake=False):
    """
    Parse upload folders and remove too old files and folders

    :param upload_folder: upload folder path
    :type upload_folder: str
    :param now: current timestamp
    :type now: float
    :param max_age: remove all files & folders older than this age. Define it for each category
        (uploads, data, error, ...)
    :type max_age: dict
    :param fake: if True, just print files to delete, without delete them
    :type fake: bool
    """
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
    """
    Parse database and remove too old jobs (from database and from disk)

    :param app_data: folder where jobs are stored
    :type app_data: str
    :param max_age: remove all files & folders older than this age. Define it for each category
        (uploads, data, error, ...)
    :type max_age: dict
    :param fake: if True, just print files to delete, without delete them
    :type fake: bool
    :return: id jobs which are in the gallery (not removed independently of their age)
    :rtype: list
    """
    from dgenies.database import Job, Gallery
    gallery_jobs = []
    with Job.connect():
        old_jobs = Job.select().where(
                      ((Job.status == "success") & (Job.date_created < datetime.now() - timedelta(days=max_age["data"])))
                      |
                      ((Job.status != "success") & (Job.date_created < datetime.now() - timedelta(days=max_age["error"])))
                  )
        for job in old_jobs:
            id_job = job.id_job
            is_gallery = len(Gallery.select().join(Job).where(Job.id_job == id_job)) > 0
            if is_gallery:
                gallery_jobs.append(id_job)
            else:
                print("Removing job %s..." % id_job)
                data_dir = os.path.join(app_data, id_job)
                if os.path.exists(data_dir) and os.path.isdir(data_dir):
                    if not fake:
                        shutil.rmtree(data_dir)
                else:
                    print("Job %s has no data folder!" % id_job)
                if not fake:
                    job.delete_instance()
    return gallery_jobs


def parse_data_folders(app_data, gallery_jobs, now, max_age, fake=False):
    """
    Parse data folder and remove too old jobs

    :param app_data: folder where jobs are stored
    :param gallery_jobs: id of jobs which are inside the gallery
    :type gallery_jobs: list
    :param now: current timestamp
    :type now: float
    :param max_age: remove all files & folders older than this age. Define it for each category
        (uploads, data, error, ...)
    :type max_age: dict
    :param fake: if True, just print files to delete, without delete them
    :type fake: bool
    :return:
    """
    for file in os.listdir(app_data):
        if file not in gallery_jobs and file not in ["gallery"]:
            file = os.path.join(app_data, file)
            create_date = os.path.getctime(file)
            age = (now - create_date) / 86400  # Age in days
            if age > max_age["data"]:
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
                    print(traceback.print_exc())
            elif os.path.isdir(file):
                query_name_file = os.path.join(file, ".query")
                if os.path.exists(query_name_file):
                    with open(query_name_file) as query_file:
                        query_filename = query_file.read().strip("\n")
                        sorted_file = Functions.get_fasta_file(file, "query", True)
                        if not sorted_file.endswith(".sorted"):
                            sorted_file = None
                        if sorted_file is not None:
                            create_date = os.path.getctime(sorted_file)
                            age = (now - create_date) / 86400  # Age in days
                            if age > max_age["fasta_sorted"]:
                                print("Removing fasta file %s..." % sorted_file)
                                if not fake:
                                    os.remove(sorted_file)
                        query_reference = os.path.join(file, "as_reference_" + os.path.basename(query_filename))
                        if os.path.exists(query_reference):
                            create_date = os.path.getctime(query_reference)
                            age = (now - create_date) / 86400  # Age in days
                            if age > max_age["fasta_sorted"]:
                                print("Removing fasta file %s..." % query_reference)
                                if not fake:
                                    os.remove(query_reference)


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
    gallery_jobs = parse_database(
        app_data=app_data,
        max_age=max_age,
        fake=fake
    )
    print("")

    print("#######################")
    print("# Parsing Data folder #")
    print("#######################")
    print("")
    parse_data_folders(
        app_data=app_data,
        now=now,
        max_age=max_age,
        fake=fake,
        gallery_jobs=gallery_jobs
    )
    print("")
