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
import sched
import requests
import threading
import random
import string
import shutil
from collections import OrderedDict
from glob import glob


__jobs = {}


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


def upload_file(s_id, url_upload, file, output):
    files = {'file-target': open(file, "rb")}
    response = requests.post(url_upload, files=files, data={"s_id": s_id})
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
    global __jobs

    with open(output, 'w') if output is not None else sys.stdout as output_p:
        url_run = url + "/run-test"
        run = requests.get(url_run)  # To init the session
        if run.status_code != 200:
            print("ERR: Unable to init session!", file=output_p)
            return False
        s_id = run.content
        print("Session:", s_id, file=output_p)

        url_pattern = r"((http(s)?)|(ftp))://.+"
        query_type = "local" if (query is not None and not re.match(url_pattern, query) is not None) else "url"
        target_type = "local" if (target is not None and not re.match(url_pattern, target) is not None) else "url"

        if query_type == "local" or target_type == "local":
            # Ask for upload:
            allowed = False
            while not allowed:
                response = requests.post(url + "/ask-upload", data={"s_id": s_id})
                if response.status_code != 200:
                    print("ERR: Unable to ask upload!", file=output_p)
                    return False
                response = response.json()
                if response["success"]:
                    allowed = response["allowed"]
                else:
                    print(response["message"], file=output_p)
                    return False
                if not allowed:
                    print("Waiting for upload...", file=output_p)
                    time.sleep(15)

            if not allowed:
                print("Not allowed!", file=output_p)
                return False

            # Ping upload
            s = sched.scheduler(time.time, time.sleep)
            uploading = True

            def ping_upload():
                if uploading:
                    try:
                        print(str(datetime.datetime.now()) + " - Ping...", file=output_p)
                        response1 = requests.post(url + "/ping-upload", data={"s_id": s_id})
                        if response1.status_code != 200:
                            print("Warn: ping fail!", file=output_p)
                        s.enter(15, 1, ping_upload)
                    except ValueError:
                        print("Unable to print ping to file")
                        pass

            s.enter(15, 1, ping_upload)

            thread_u = threading.Timer(0, s.run)
            thread_u.start()

        url_upload = url + "/upload"

        # Upload target:
        is_correct = True
        if target_type == "local":
            print("Upload target: %s... " % target, file=output_p)
            is_correct = upload_file(s_id, url_upload, target, output_p)

        if is_correct and query is not None and query_type == "local":
            # Upload query:
            print("Upload query: %s... " % query, file=output_p)
            is_correct = upload_file(s_id, url_upload, query, output_p)

        if not is_correct:
            print("ERR: error while uploading files", file=output_p)
            uploading = False
            return False

        uploading = False

        # Start run:
        print("Start job... ", end="", flush=True, file=output_p)
        url_launch = url + "/launch_analysis"
        id_job = random_string(5) + "_" + datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d%H%M%S')
        if query_type == "local":
            query = os.path.basename(query) if query is not None else ""
        if target_type == "local":
            target = os.path.basename(target)
        params = {
            "s_id": s_id,
            "id_job": id_job,
            "email": email,
            "query": query if query is not None else "",
            "query_type": query_type,
            "target": target,
            "target_type": target_type
        }
        response = requests.post(url_launch, data=params)
        if response.status_code == 200:
            print("Started!", file=output_p)
            json = response.json()
            status_url = json['redirect']
            print("Show status:", url + status_url, file=output_p)
            id_job = status_url.rsplit("/", 1)[1]
            is_correct = True
            shutil.move(output, output.replace(".launched", ".submitted"))
            __jobs[nb_job] = id_job
        else:
            is_correct = False
            print("ERR %d: Failed to launch job" % response.status_code, file=output_p)
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
    log_file = glob(log_file + ".*")
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
    global __jobs

    status = {}
    status_url = url + "/status/"
    nb_pending = len(__jobs)
    success = 0
    fail = 0
    no_match = 0
    print("")
    while nb_pending > 0:
        print("CHECKING STATUS... ", end="", flush=True)
        counts_by_status = init_counts_by_status()
        nb_pending = 0
        for nb_subjob, id_job in __jobs.items():
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
                n_jobs = int(sample[2]) if len(sample) >= 3 else 1
                for i in range(0, n_jobs):
                    print("Launching job %d (%d/%d)..." % (nb_job, i+1, n_jobs))
                    nb_subjob = "%d_%d" % (nb_job, i)
                    __jobs[nb_subjob] = None
                    log_file = os.path.join(logs, "job_%s.launched" % nb_subjob)
                    thread = threading.Timer(0, launch_job,
                                             kwargs={"nb_job": nb_subjob,
                                                     "url": url,
                                                     "target": target,
                                                     "query": query,
                                                     "email": args.email,
                                                     "output": log_file})
                    thread.start()  # Start the execution
                    time.sleep(0.01)
                nb_job += 1
        time.sleep(5)
        check_jobs(logs, url)
