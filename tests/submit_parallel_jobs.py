#!/usr/bin/env python3
"""
Submit parallel jobs to test the server charge
"""

import os
import sys
import re
import argparse
import datetime
import time
import requests
import threading
import random
import string
import shutil
from collections import OrderedDict
from glob import glob


JOBS = {}


class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    OKCYAN = '\033[36m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def random_string(s_len):
    """
    Generate a random string
    :param s_len: length of the string to generate
    :return: the random string
    """
    return ''.join([random.choice(string.ascii_letters + string.digits) for n in range(s_len)])


def parse_args():
    parser = argparse.ArgumentParser(description="Submit several jobs to the server to test its charge")
    parser.add_argument('-s', '--samples', type=str, required=True, help="File describing input files")
    parser.add_argument('-u', '--url', type=str, required=True, help="Url of the server")
    parser.add_argument('-e', '--email', type=str, required=False, default="test@xxxxx.yy",
                        help="Email to set for jobs")
    parser.add_argument('-d', '--logs-dir', type=str, required=False, default="./logs")

    return parser.parse_args()


def upload_file(session, url_upload, file, output):
    files = {'file-target': open(file, "rb")}
    response = session.post(url_upload, files=files)
    is_correct = False
    if response.status_code == 200:
        json = response.json()
        if "success" in json and json["success"] == "OK":
            is_correct = True
            print("OK!", file=output)
        else:
            print("ERROR: ", json, file=output)
    else:
        print("ERROR with status code %s" % response.status_code, file=output)
    return is_correct


def launch_job(nb_job, url, target, query=None, email="test@xxxxx.yy", output=None):
    global JOBS

    with open(output, 'w') if output is not None else sys.stdout as output_p:
        url_run = url + "/run"
        session = requests.Session()
        session.get(url_run)  # To init the session

        # Upload target:
        print("Upload target: %s... " % target, end="", flush=True, file=output_p)
        url_upload = url + "/upload"
        is_correct = upload_file(session, url_upload, target, output_p)

        if is_correct and query is not None:
            # Upload query:
            print("Upload query: %s... " % query, end="", flush=True, file=output_p)
            is_correct = upload_file(session, url_upload, query, output_p)

        # Start run:
        if is_correct:
            print("Start job... ", end="", flush=True, file=output_p)
            url_launch = url + "/launch_analysis"
            id_job = random_string(5) + "_" + datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d%H%M%S')
            params = {
                "id_job": id_job,
                "email": email,
                "query": os.path.basename(query) if query is not None else "",
                "query_type": "local",
                "target": os.path.basename(target),
                "target_type": "local"
            }
            response = session.post(url_launch, data=params)
            if response.status_code == 200:
                print("Started!", file=output_p)
                json = response.json()
                status_url = json['redirect']
                print("Show status:", url + status_url, file=output_p)
                id_job = status_url.rsplit("/", 1)[1]
                is_correct = True
                shutil.move(output, output.replace(".launched", ".submitted"))
                JOBS[nb_job] = id_job
            else:
                is_correct = False
        return is_correct


def init_counts_by_status():
    counts_by_status = OrderedDict()
    for status in ["success", "fail", "no-match", "submitted", "getfiles", "preparing", "prepared", "scheduled",
                   "starting", "started", "scheduled-cluster", "merging"]:
        counts_by_status[status] = 0
    return counts_by_status


def print_status(counts_by_status):
    nb = 0
    if len(counts_by_status) > 0:
        for status, count in counts_by_status.items():
            if count > 0:
                if status == "success":
                    print(bcolors.OKGREEN + status + ":" + str(count) + bcolors.ENDC)
                elif status == "fail":
                    print(bcolors.FAIL + status + ":" + str(count) + bcolors.ENDC)
                elif status == "started":
                    print(bcolors.OKBLUE + status + ":" + str(count) + bcolors.ENDC)
                elif status == "preparing":
                    print(bcolors.OKCYAN + status + ":" + str(count) + bcolors.ENDC)
                elif status == "no-match":
                    print(bcolors.WARNING + status + ":" + str(count) + bcolors.ENDC)
                else:
                    print(bcolors.BOLD + status + ":" + str(count) + bcolors.ENDC)
                nb += 1
        if nb == 0:
            print("No job submitted yet...")
    else:
        print("No job submitted yet...")
    print("")


def mv_file(log_file, status):
    log_file = glob(log_file + "*")
    if len(log_file) == 1:
        log_file = log_file[0]
        dirname = os.path.dirname(log_file)
        basename = os.path.basename(log_file)
        basename_woext = basename.rsplit(".", 1)[0]
        new_log_file = os.path.join(dirname, ".".join([basename_woext, status]))
        shutil.move(log_file, new_log_file)
    else:
        print("UNABLE TO FIND LOG FILE!!")


def check_jobs(log_dir, url):
    global JOBS

    status = {}
    status_url = url + "/status/"
    nb_pending = len(JOBS)
    success = 0
    fail = 0
    no_match = 0
    print("")
    while nb_pending > 0:
        print("CHECKING STATUS... ", end="", flush=True)
        counts_by_status = init_counts_by_status()
        nb_pending = 0
        for nb_subjob, id_job in JOBS.items():
            if id_job is not None:
                if nb_subjob not in status or status[nb_subjob] not in ["success", "fail", "no-match"]:
                    response = requests.get(status_url + id_job + "?format=json")
                    if response.status_code == 200:
                        data = response.json()
                        status_job = data["status"]
                        status[nb_subjob] = status_job
                        if status_job == "success":
                            success += 1
                        elif status_job == "fail":
                            fail += 1
                        elif status_job == "no-match":
                            no_match += 1
                        else:
                            if status_job not in counts_by_status:
                                counts_by_status[status_job] = 0
                            counts_by_status[status_job] += 1
                            nb_pending += 1
                        mv_file(os.path.join(log_dir, "job_" + nb_subjob), status_job)
                    else:
                        print("ERR: ", response.status_code)
                        nb_pending += 1
            else:
                nb_pending += 1
        counts_by_status["success"] += success
        counts_by_status["fail"] += fail
        counts_by_status["no-match"] += no_match

        print("\b\b\b\b", end="")
        print(":  ", flush=True)
        print_status(counts_by_status)
        if nb_pending > 0:
            time.sleep(10)
        else:
            print("DONE!")


if __name__ == '__main__':
    args = parse_args()
    url = args.url
    logs = args.logs_dir
    if os.path.exists(logs):
        if os.path.isdir(logs):
            job_files = glob(os.path.join(logs, "job_*"))
            if len(job_files) > 0:
                for job_file in job_files:
                    print("Remove old job file %s..." % job_file)
                    os.remove(job_file)
        else:
            print("Log dir exists and is not a folder!")
            exit(1)
    else:
        os.makedirs(logs)
    nb_job = 1
    with open(args.samples) as samples:
        for line in samples:
            if not line.startswith("#"):
                sample = re.split(r"\s+", line.strip("\n"))
                target = sample[0]
                query = sample[1] if sample[1].upper() != "NONE" else None
                n_jobs = int(sample[2])
                for i in range(0, n_jobs):
                    print("Launching job %d (%d/%d)..." % (nb_job, i+1, n_jobs))
                    nb_subjob = "%d_%d" % (nb_job, i)
                    JOBS[nb_subjob] = None
                    log_file = os.path.join(logs, "job_%s.launched" % nb_subjob)
                    thread = threading.Timer(0, launch_job,
                                             kwargs={"nb_job": nb_subjob,
                                                     "url": url,
                                                     "target": target,
                                                     "query": query,
                                                     "email": args.email,
                                                     "output": log_file})
                    thread.start()  # Start the execution
                nb_job += 1
        time.sleep(5)
        check_jobs(logs, url)
