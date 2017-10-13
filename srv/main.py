#!/usr/bin/env python3

import json
import time
import datetime
from flask import Flask, render_template, request, redirect, flash, url_for
from werkzeug.utils import secure_filename
from lib.parse_paf import parse_paf
from config_reader import AppConfigReader
from lib.job_manager import JobManager
from lib.functions import *

import sys
app_folder = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, app_folder)
os.environ["PATH"] = os.path.join(app_folder, "bin") + ":" + os.environ["PATH"]

sqlite_file = os.path.join(app_folder, "database.sqlite")


# Init config reader:
config_reader = AppConfigReader()

UPLOAD_FOLDER = config_reader.get_upload_folder()

app_title = "D-GENIES - Dotplot for Genomes Interactive, E-connected and Speedy"
app_title_small = "D-GENIES"

# Init Flask:
app = Flask(__name__, static_url_path='/static')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'dsqdsq-255sdA-fHfg52-25Asd5'

# Folder containing data:
app_data = config_reader.get_app_data()


# Main
@app.route("/", methods=['GET'])
def main():
    id_job = random_string(5) + "_" + datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d%H%M%S')
    if "id_job" in request.args:
        id_job = request.args["id_job"]
    email = ""
    if "email" in request.args:
        email = request.args["email"]
    return render_template("index.html", title=app_title, title_small=app_title_small, id_job=id_job, email=email)


# Launch analysis
@app.route("/launch_analysis", methods=['POST'])
def launch_analysis():
    id_job = request.form["id_job"]
    email = request.form["email"]
    file_query = request.files["file_query"]
    file_target = request.files["file_target"]

    # Check form:
    form_pass = True
    if id_job == "":
        flash("Id of job not given")
        form_pass = False

    if email == "":
        flash("Email not given")
        form_pass = False
    if file_query.filename == "":
        flash("No query fasta selected")
        form_pass = False
    if file_target.filename == "":
        flash("No target fasta selected")
        form_pass = False

    # Form pass
    if form_pass:
        # Check files are correct:
        if not allowed_file(file_query.filename):
            flash("Format of query fasta must be in fasta format (.fa, .fa.gz, .fasta, .fasta.gz)")
            form_pass = False
        if not allowed_file(file_target.filename):
            flash("Format of target fasta must be in fasta format (.fa, .fa.gz, .fasta, .fasta.gz)")
            form_pass = False
        if form_pass:
            # Save files:
            query_name = os.path.splitext(os.path.basename(file_query.filename))[0]
            filename_query = get_valid_uploaded_filename(secure_filename(file_query.filename), app.config["UPLOAD_FOLDER"])
            target_name = os.path.splitext(os.path.basename(file_target.filename))[0]
            query_path = os.path.join(app.config["UPLOAD_FOLDER"], filename_query)
            file_query.save(query_path)
            filename_target = get_valid_uploaded_filename(secure_filename(file_target.filename), app.config["UPLOAD_FOLDER"])
            target_path = os.path.join(app.config["UPLOAD_FOLDER"], filename_target)
            file_target.save(target_path)

            # Get final job id:
            id_job_orig = id_job
            while os.path.exists(os.path.join(app_data, id_job)):
                id_job = id_job_orig + "_2"

            # Launch job:
            job = JobManager(id_job, email, query_path, target_path, query_name, target_name)
            job.launch()
            return redirect(url_for(".status", id_job=id_job))
        else:
            return redirect(url_for(".main", id_job=id_job, email=email))
    else:
        return redirect(url_for(".main", id_job=id_job, email=email))


# Status of a job
@app.route('/status/<id_job>', methods=['GET'])
def status(id_job):
    job = JobManager(id_job)
    status = job.status()
    return render_template("status.html", title=app_title, title_small=app_title_small, status=status, id_job=id_job)


# Results path
@app.route("/result/<id_res>", methods=['GET'])
def result(id_res):
    return render_template("results.html", title=app_title, title_small=app_title_small, id=id_res)


# Get graph (ajax request)
@app.route('/get_graph', methods=['POST'])
def get_graph():
    id_f = request.form["id"]
    paf = os.path.join(app_data, id_f, "map.paf")
    idx1 = os.path.join(app_data, id_f, "query.idx")
    idx2 = os.path.join(app_data, id_f, "target.idx")

    success, res = parse_paf(paf, idx1, idx2)

    if success:
        res["success"] = True
        return json.dumps(res)
    return json.dumps({"success": False, "message": res})
