#!/usr/bin/env python3

import os
import time
import datetime
import shutil
import re
import threading
from flask import Flask, render_template, request, url_for, jsonify, Response, abort
from pathlib import Path
from lib.paf import Paf
from config_reader import AppConfigReader
from lib.job_manager import JobManager
from lib.functions import Functions, ALLOWED_EXTENSIONS
from lib.upload_file import UploadFile
from lib.fasta import Fasta
from lib.mailer import Mailer
from lib.crons import Crons
from database import Session
from peewee import DoesNotExist

import sys

app_folder = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, app_folder)
os.environ["PATH"] = os.path.join(app_folder, "bin") + ":" + os.environ["PATH"]

sqlite_file = os.path.join(app_folder, "database.sqlite")


# Init config reader:
config_reader = AppConfigReader()

UPLOAD_FOLDER = config_reader.upload_folder
APP_DATA = config_reader.app_data

app_title = "D-GENIES - Dotplot for Genomes Interactive, E-connected and Speedy"

# Init Flask:
app = Flask(__name__, static_url_path='/static')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config_reader.max_upload_file_size
app.config['SECRET_KEY'] = 'dsqdsq-255sdA-fHfg52-25Asd5'

# Init mail:
mailer = Mailer(app)

# Folder containing data:
app_data = config_reader.app_data

if config_reader.debug and config_reader.log_dir != "stdout" and not os.path.exists(config_reader.log_dir):
    os.makedirs(config_reader.log_dir)

# Crons:
if os.getenv('DISABLE_CRONS') != "True":
    print("Starting crons...")
    crons = Crons(app_folder)
    crons.start_all()


@app.context_processor
def get_launched_results():
    cookie = request.cookies.get("results")
    return {"results": cookie.split("|") if cookie is not None else set()}


# Main
@app.route("/", methods=['GET'])
def main():
    return render_template("index.html", title=app_title, menu="index")


@app.route("/run", methods=['GET'])
def run():
    s_id = Session.new()
    id_job = Functions.random_string(5) + "_" + datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d%H%M%S')
    if "id_job" in request.args:
        id_job = request.args["id_job"]
    email = ""
    if "email" in request.args:
        email = request.args["email"]
    return render_template("run.html", title=app_title, id_job=id_job, email=email,
                           menu="run", allowed_ext=ALLOWED_EXTENSIONS, s_id=s_id,
                           max_upload_file_size=config_reader.max_upload_file_size)


@app.route("/run-test", methods=['GET'])
def run_test():
    print(config_reader.allowed_ip_tests)
    if request.remote_addr not in config_reader.allowed_ip_tests:
        return abort(404)
    return Session.new()


# Launch analysis
@app.route("/launch_analysis", methods=['POST'])
def launch_analysis():
    try:
        session = Session.get(s_id=request.form["s_id"])
    except DoesNotExist:
        return jsonify({"success": False, "errors": ["Session has expired. Please refresh the page and try again"]})
    # Reset session upload:
    session.allow_upload = False
    session.position = -1
    session.save()
    id_job = request.form["id_job"]
    email = request.form["email"]
    file_query = request.form["query"]
    file_query_type = request.form["query_type"]
    file_target = request.form["target"]
    file_target_type = request.form["target_type"]

    # Check form:
    form_pass = True
    errors = []
    if id_job == "":
        errors.append("Id of job not given")
        form_pass = False

    if email == "":
        errors.append("Email not given")
        form_pass = False
    if file_target == "":
        errors.append("No target fasta selected")
        form_pass = False

    # Form pass
    if form_pass:
        # Get final job id:
        id_job = re.sub('[^A-Za-z0-9_\-]+', '', id_job.replace(" ", "_"))
        id_job_orig = id_job
        i = 2
        while os.path.exists(os.path.join(app_data, id_job)):
            id_job = id_job_orig + ("_%d" % i)
            i += 1

        folder_files = os.path.join(app_data, id_job)
        os.makedirs(folder_files)

        # Save files:
        query = None
        upload_folder = session.upload_folder
        if file_query != "":
            query_name = os.path.splitext(file_query.replace(".gz", ""))[0] if file_query_type == "local" else None
            query_path = os.path.join(app.config["UPLOAD_FOLDER"], upload_folder, file_query) \
                if file_query_type == "local" else file_query
            query = Fasta(name=query_name, path=query_path, type_f=file_query_type)
        target_name = os.path.splitext(file_target.replace(".gz", ""))[0] if file_target_type == "local" else None
        target_path = os.path.join(app.config["UPLOAD_FOLDER"], upload_folder, file_target) \
            if file_target_type == "local" else file_target
        target = Fasta(name=target_name, path=target_path, type_f=file_target_type)

        # Launch job:
        job = JobManager(id_job, email, query, target, mailer)
        job.launch()

        # Delete session:
        session.delete_instance()
        return jsonify({"success": True, "redirect": url_for(".status", id_job=id_job)})
    else:
        return jsonify({"success": False, "errors": errors})


# Status of a job
@app.route('/status/<id_job>', methods=['GET'])
def status(id_job):
    job = JobManager(id_job)
    j_status = job.status()
    mem_peak = j_status["mem_peak"] if "mem_peak" in j_status else None
    if mem_peak is not None:
        mem_peak = "%.1f G" % (mem_peak / 1024.0 / 1024.0)
    time_e = j_status["time_elapsed"] if "time_elapsed" in j_status else None
    if time_e is not None:
        if time_e < 60:
            time_e = "%d secs" % time_e
        else:
            minutes = time_e // 60
            seconds = time_e - minutes * 60
            time_e = "%d min %d secs" % (minutes, seconds)
    format = request.args.get("format")
    if format is not None and format == "json":
        return jsonify({
            "status": j_status["status"],
            "error": j_status["error"].replace("#ID#", ""),
            "id_job": id_job,
            "mem_peak": mem_peak,
            "time_elapsed": time_e
        })
    return render_template("status.html", title=app_title, status=j_status["status"],
                           error=j_status["error"].replace("#ID#", ""),
                           id_job=id_job, menu="results", mem_peak=mem_peak,
                           time_elapsed=time_e)


# Results path
@app.route("/result/<id_res>", methods=['GET'])
def result(id_res):
    my_render = render_template("results.html", title=app_title, id=id_res, menu="results", current_result=id_res)
    response = app.make_response(my_render)
    cookie = request.cookies.get("results")
    cookie = cookie.split("|") if cookie is not None else []
    if id_res not in cookie:
        cookie.insert(0, id_res)
    response.set_cookie(key="results", value="|".join(cookie), path="/")
    return response


def get_file(file, gzip=False):  # pragma: no cover
    try:
        # Figure out how flask returns static files
        # Tried:
        # - render_template
        # - send_file
        # This should not be so non-obvious
        return open(file, "rb" if gzip else "r").read()
    except IOError as exc:
        return str(exc)


@app.route("/paf/<id_res>", methods=['GET'])
def download_paf(id_res):
    map_file = os.path.join(APP_DATA, id_res, "map.paf.sorted")
    if not os.path.exists(map_file):
        map_file = os.path.join(APP_DATA, id_res, "map.paf")
    if not os.path.exists(map_file):
        abort(404)
    content = get_file(map_file)
    return Response(content, mimetype="text/plain")


# Get graph (ajax request)
@app.route('/get_graph', methods=['POST'])
def get_graph():
    id_f = request.form["id"]
    paf = os.path.join(app_data, id_f, "map.paf")
    idx1 = os.path.join(app_data, id_f, "query.idx")
    idx2 = os.path.join(app_data, id_f, "target.idx")

    paf = Paf(paf, idx1, idx2)

    if paf.parsed:
        res = paf.get_d3js_data()
        res["success"] = True
        return jsonify(res)
    return jsonify({"success": False, "message": paf.error})


@app.route('/sort/<id_res>', methods=['POST'])
def sort_graph(id_res):
    if not os.path.exists(os.path.join(APP_DATA, id_res, ".all-vs-all")):
        paf_file = os.path.join(app_data, id_res, "map.paf")
        idx1 = os.path.join(app_data, id_res, "query.idx")
        idx2 = os.path.join(app_data, id_res, "target.idx")
        paf = Paf(paf_file, idx1, idx2, False)
        paf.sort()
        if paf.parsed:
            res = paf.get_d3js_data()
            res["success"] = True
            return jsonify(res)
        return jsonify({"success": False, "message": paf.error})
    return jsonify({"success": False, "message": "Sort is not available for All-vs-All mode"})


@app.route('/reverse-contig/<id_res>', methods=['POST'])
def reverse_contig(id_res):
    contig_name = request.form["contig"]
    if not os.path.exists(os.path.join(APP_DATA, id_res, ".all-vs-all")):
        paf_file = os.path.join(app_data, id_res, "map.paf")
        idx1 = os.path.join(app_data, id_res, "query.idx")
        idx2 = os.path.join(app_data, id_res, "target.idx")
        paf = Paf(paf_file, idx1, idx2, False)
        paf.reverse_contig(contig_name)
        if paf.parsed:
            res = paf.get_d3js_data()
            res["success"] = True
            return jsonify(res)
        return jsonify({"success": False, "message": paf.error})
    return jsonify({"success": False, "message": "Sort is not available for All-vs-All mode"})


@app.route('/freenoise/<id_res>', methods=['POST'])
def free_noise(id_res):
    paf_file = os.path.join(app_data, id_res, "map.paf")
    idx1 = os.path.join(app_data, id_res, "query.idx")
    idx2 = os.path.join(app_data, id_res, "target.idx")
    paf = Paf(paf_file, idx1, idx2, False)
    paf.parse_paf(noise=request.form["noise"] == "1")
    if paf.parsed:
        res = paf.get_d3js_data()
        res["success"] = True
        return jsonify(res)
    return jsonify({"success": False, "message": paf.error})


@app.route('/get-fasta-query/<id_res>', methods=['POST'])
def build_fasta(id_res):
    res_dir = os.path.join(app_data, id_res)
    lock_query = os.path.join(res_dir, ".query-fasta-build")
    is_sorted = os.path.exists(os.path.join(res_dir, ".sorted"))
    compressed = request.form["gzip"].lower() == "true"
    query_fasta = Functions.get_fasta_file(res_dir, "query", is_sorted)
    if query_fasta is not None:
        if is_sorted and not query_fasta.endswith(".sorted"):
            # Do the sort
            Path(lock_query).touch()
            if not compressed:  # If compressed, it will took a long time, so not wait
                Path(lock_query + ".pending").touch()
            thread = threading.Timer(1, Functions.sort_fasta, kwargs={
                "job_name": id_res,
                "fasta_file": query_fasta,
                "index_file": os.path.join(res_dir, "query.idx.sorted"),
                "lock_file": lock_query,
                "compress": compressed,
                "mailer": mailer
            })
            thread.start()
            if not compressed:
                i = 0
                time.sleep(5)
                while os.path.exists(lock_query) and i < 2:
                    i += 1
                    time.sleep(5)
                os.remove(lock_query + ".pending")
                if os.path.exists(lock_query):
                    return jsonify({"success": True, "status": 1, "status_message": "In progress"})
                return jsonify({"success": True, "status": 2, "status_message": "Done",
                                "gzip": False})
            else:
                return jsonify({"success": True, "status": 1, "status_message": "In progress"})
        elif is_sorted and os.path.exists(lock_query):
            # Sort is already in progress
            return jsonify({"success": True, "status": 1, "status_message": "In progress"})
        else:
            # No sort to do or sort done
            if compressed and not query_fasta.endswith(".gz.fasta"):
                # If compressed file is asked, we must compress it now if not done before...
                Path(lock_query).touch()
                thread = threading.Timer(1, Functions.compress_and_send_mail, kwargs={
                    "job_name": id_res,
                    "fasta_file": query_fasta,
                    "index_file": os.path.join(res_dir, "query.idx.sorted"),
                    "lock_file": lock_query,
                    "compressed": compressed,
                    "mailer": mailer
                })
                thread.start()
                return jsonify({"success": True, "status": 1, "status_message": "In progress"})
            return jsonify({"success": True, "status": 2, "status_message": "Done",
                            "gzip": query_fasta.endswith(".gz") or query_fasta.endswith(".gz.sorted")})
    else:
        return jsonify({"success": False,
                        "message": "Unable to get fasta file for query. Please contact us to report the bug"})


@app.route('/fasta-query/<id_res>', defaults={'filename': ""}, methods=['GET'])
@app.route('/fasta-query/<id_res>/<filename>', methods=['GET'])  # Use fake URL in mail to set download file name
def dl_fasta(id_res, filename):
    res_dir = os.path.join(app_data, id_res)
    lock_query = os.path.join(res_dir, ".query-fasta-build")
    is_sorted = os.path.exists(os.path.join(res_dir, ".sorted"))
    if not os.path.exists(lock_query) or not is_sorted:
        query_fasta = Functions.get_fasta_file(res_dir, "query", is_sorted)
        if query_fasta is not None:
            if query_fasta.endswith(".gz") or query_fasta.endswith(".gz.sorted"):
                content = get_file(query_fasta, True)
                return Response(content, mimetype="application/gzip")
            content = get_file(query_fasta)
            return Response(content, mimetype="text/plain")
    abort(404)


@app.route('/qt-assoc/<id_res>', methods=['GET'])
def qt_assoc(id_res):
    res_dir = os.path.join(app_data, id_res)
    if os.path.exists(res_dir) and os.path.isdir(res_dir):
        paf_file = os.path.join(app_data, id_res, "map.paf")
        idx1 = os.path.join(app_data, id_res, "query.idx")
        idx2 = os.path.join(app_data, id_res, "target.idx")
        try:
            paf = Paf(paf_file, idx1, idx2, False)
            paf.parse_paf(False)
        except FileNotFoundError:
            print("Unable to load data!")
            abort(404)
            return False
        csv_content = paf.build_query_on_target_association_file()
        return Response(csv_content, mimetype="text/plain")
    abort(404)


@app.route('/no-assoc/<id_res>', methods=['POST'])
def no_assoc(id_res):
    """
    Get contigs that match with None target
    :param id_res: id of the result
    """
    res_dir = os.path.join(app_data, id_res)
    if os.path.exists(res_dir) and os.path.isdir(res_dir):
        paf_file = os.path.join(app_data, id_res, "map.paf")
        idx1 = os.path.join(app_data, id_res, "query.idx")
        idx2 = os.path.join(app_data, id_res, "target.idx")
        try:
            paf = Paf(paf_file, idx1, idx2, False)
        except FileNotFoundError:
            print("Unable to load data!")
            abort(404)
            return False
        file_content = paf.build_list_no_assoc(request.form["to"])
        empty = file_content == "\n"
        return jsonify({
            "file_content": file_content,
            "empty": empty
        })
    abort(404)


@app.route('/summary/<id_res>', methods=['POST'])
def summary(id_res):
    pass


@app.route("/ask-upload", methods=['POST'])
def ask_upload():
    try:
        s_id = request.form['s_id']
        session = Session.get(s_id=s_id)
        allowed, position = session.ask_for_upload(True)
        return jsonify({
            "success": True,
            "allowed": allowed,
            "position": position
        })
    except DoesNotExist:
        return jsonify({"success": False, "message": "Session not initialized. Please refresh the page."})


@app.route("/ping-upload", methods=['POST'])
def ping_upload():
    s_id = request.form['s_id']
    session = Session.get(s_id=s_id)
    session.ping()
    return "OK"


@app.route("/upload", methods=['POST'])
def upload():
    try:
        s_id = request.form['s_id']
        session = Session.get(s_id=s_id)
        if session.ask_for_upload(False)[0]:
            folder = session.upload_folder
            files = request.files[list(request.files.keys())[0]]

            if files:
                filename = files.filename
                folder_files = os.path.join(app.config["UPLOAD_FOLDER"], folder)
                if not os.path.exists(folder_files):
                    os.makedirs(folder_files)
                filename = Functions.get_valid_uploaded_filename(filename, folder_files)
                mime_type = files.content_type

                if not Functions.allowed_file(files.filename):
                    result = UploadFile(name=filename, type_f=mime_type, size=0, not_allowed_msg="File type not allowed")
                    shutil.rmtree(folder_files)

                else:
                    # save file to disk
                    uploaded_file_path = os.path.join(folder_files, filename)
                    files.save(uploaded_file_path)

                    # get file size after saving
                    size = os.path.getsize(uploaded_file_path)

                    # return json for js call back
                    result = UploadFile(name=filename, type_f=mime_type, size=size)

                return jsonify({"files": [result.get_file()], "success": "OK"})

            return jsonify({"files": [], "success": "404", "message": "No file provided"})
        return jsonify({"files": [], "success": "ERR", "message": "Not allowed to upload!"})
    except DoesNotExist:
        return jsonify({"files": [], "success": "ERR", "message": "Session not initialized. Please refresh the page."})
    except:  # Except all possible exceptions to prevent crashes
        return jsonify({"files": [], "success": "ERR", "message": "An unexpected error has occurred on upload. "
                                                                  "Please contact the support."})


@app.route("/send-mail/<id_res>", methods=['POST'])
def send_mail(id_res):
    allowed = False
    key_file = None
    if "key" in request.form:
        key = request.form["key"]
        res_dir = os.path.join(app_data, id_res)
        key_file = os.path.join(res_dir, ".key")
        if os.path.exists(key_file):
            with open(key_file) as k_f:
                true_key = k_f.readline().strip("\n")
                allowed = key == true_key
    if allowed:
        os.remove(key_file)
        job_mng = JobManager(id_job=id_res, mailer=mailer)
        job_mng.set_inputs_from_res_dir()
        job_mng.send_mail()
        return "OK"
    else:
        abort(403)


if __name__ == '__main__':
    app.run()
