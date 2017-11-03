#!/usr/bin/env python3

import time
import datetime
import shutil
from flask import Flask, render_template, request, url_for, jsonify, session
from lib.paf import Paf
from config_reader import AppConfigReader
from lib.job_manager import JobManager
from lib.functions import *
from lib.upload_file import UploadFile
from lib.Fasta import Fasta

import sys

app_folder = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, app_folder)
os.environ["PATH"] = os.path.join(app_folder, "bin") + ":" + os.environ["PATH"]

sqlite_file = os.path.join(app_folder, "database.sqlite")


# Init config reader:
config_reader = AppConfigReader()

UPLOAD_FOLDER = config_reader.get_upload_folder()

app_title = "D-GENIES - Dotplot for Genomes Interactive, E-connected and Speedy"

# Init Flask:
app = Flask(__name__, static_url_path='/static')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'dsqdsq-255sdA-fHfg52-25Asd5'

# Folder containing data:
app_data = config_reader.get_app_data()


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
    session["user_tmp_dir"] = random_string(5) + "_" + \
                              datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d%H%M%S')
    id_job = random_string(5) + "_" + datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d%H%M%S')
    if "id_job" in request.args:
        id_job = request.args["id_job"]
    email = ""
    if "email" in request.args:
        email = request.args["email"]
    return render_template("run.html", title=app_title, id_job=id_job, email=email,
                           menu="run")


# Launch analysis
@app.route("/launch_analysis", methods=['POST'])
def launch_analysis():
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
    if file_query == "":
        errors.append("No query fasta selected")
        form_pass = False

    # Form pass
    if form_pass:
        # Get final job id:
        id_job_orig = id_job
        while os.path.exists(os.path.join(app_data, id_job)):
            id_job = id_job_orig + "_2"

        folder_files = os.path.join(app_data, id_job)
        os.makedirs(folder_files)

        # Save files:
        query_name = os.path.splitext(file_query.replace(".gz", ""))[0] if file_query_type == "local" else None
        query_path = os.path.join(app.config["UPLOAD_FOLDER"], session["user_tmp_dir"], file_query) \
            if file_query_type == "local" else file_query
        query = Fasta(name=query_name, path=query_path, type_f=file_query_type)
        target = None
        if file_target != "":
            target_name = os.path.splitext(file_target.replace(".gz", ""))[0] if file_target_type == "local" else None
            target_path = os.path.join(app.config["UPLOAD_FOLDER"], session["user_tmp_dir"], file_target) \
                if file_target_type == "local" else file_target
            target = Fasta(name=target_name, path=target_path, type_f=file_target_type)

        # Launch job:
        job = JobManager(id_job, email, query, target)
        job.launch()
        return jsonify({"success": True, "redirect": url_for(".status", id_job=id_job)})
    else:
        return jsonify({"success": False, "errors": errors})


# Status of a job
@app.route('/status/<id_job>', methods=['GET'])
def status(id_job):
    job = JobManager(id_job)
    j_status, error = job.status()
    return render_template("status.html", title=app_title, status=j_status, error=error, id_job=id_job,
                           menu="results")


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
    paf = os.path.join(app_data, id_res, "map.paf")
    idx1 = os.path.join(app_data, id_res, "query.idx")
    idx2 = os.path.join(app_data, id_res, "target.idx")
    paf = Paf(paf, idx1, idx2)
    paf.sort()
    if paf.parsed:
        res = paf.get_d3js_data()
        res["success"] = True
        return jsonify(res)
    return jsonify({"success": False, "message": paf.error})


@app.route("/upload", methods=['POST'])
def upload():
    if "user_tmp_dir" in session and session["user_tmp_dir"] != "":
        folder = session["user_tmp_dir"]
        files = request.files[list(request.files.keys())[0]]

        if files:
            filename = files.filename
            folder_files = os.path.join(app.config["UPLOAD_FOLDER"], folder)
            if not os.path.exists(folder_files):
                os.makedirs(folder_files)
            filename = get_valid_uploaded_filename(filename, folder_files)
            mime_type = files.content_type

            if not allowed_file(files.filename):
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
    return jsonify({"files": [], "success": "ERR", "message": "Session not initialized. Please refresh the page."})


if __name__ == '__main__':
    app.run()
