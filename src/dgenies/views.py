from dgenies import app, app_title, app_folder, config_reader, mailer, APP_DATA, MODE, DEBUG, VERSION

import os
import sys
import time
import datetime
import shutil
import re
import threading
import traceback
import json
from string import Template
from flask import render_template, request, url_for, jsonify, Response, abort, send_file, send_from_directory, Markup
from pathlib import Path
from dgenies.lib.paf import Paf
from dgenies.lib.job_manager import JobManager
from dgenies.lib.functions import Functions
from dgenies.allowed_extensions import AllowedExtensions
from dgenies.lib.upload_file import UploadFile
from dgenies.lib.datafile import DataFile
from dgenies.lib.exceptions import DGeniesExampleNotAvailable, DGeniesJobCheckError, DGeniesMissingJobError,\
    DGeniesDeleteGalleryJobForbidden, DGeniesUnknownToolError, DGeniesUnknownOptionError
from dgenies.lib.latest import Latest
from dgenies.tools import Tools
from markdown import Markdown
from markdown.extensions.toc import TocExtension
from markdown.extensions.tables import TableExtension
import tarfile
from xopen import xopen
from jinja2 import Environment
if MODE == "webserver":
    from dgenies.database import Session, Gallery
    from peewee import DoesNotExist

import logging

logger = logging.getLogger(__name__)

@app.context_processor
def global_templates_variables():
    """
    Global variables used for any view
    """
    return {
        "title": app_title,
        "mode": MODE,
        "all_jobs": Functions.get_list_all_jobs(MODE),
        "cookie_wall": config_reader.cookie_wall,
        "legal_pages": config_reader.legal,
        "debug": DEBUG
    }


# Main
@app.route("/", methods=['GET'])
def main():
    """
    Index page
    """
    if MODE == "webserver":
        # We get the first picture in gallery if exists
        pict = Gallery.select().order_by("id")
        if len(pict) > 0:
            pict = pict[0].picture
        else:
            pict = None
    else:
        pict = None
    return render_template("index.html", menu="index", pict=pict)


@app.route("/run", methods=['GET'])
def run():
    """
    Run page
    """
    # Message banner part
    inforun = None
    inforun_file = os.path.join(config_reader.config_dir, ".inforun")
    if os.path.exists(inforun_file):
        try:
            with open(inforun_file, "r") as info:
                inforun = json.loads(info.read())
        except json.JSONDecodeError:
            print("Unable to parse inforun file. Ignoring it.", file=sys.stderr)
            pass

    # We get the list of tools and their options
    tools = Tools().tools
    tools_names = sorted(list(tools.keys()), key=lambda x: (tools[x].order, tools[x].name))
    tools_ava = {}
    tools_options = {}
    tools_checking = {}
    for tool_name, tool in tools.items():
        tools_ava[tool_name] = 1 if tool.all_vs_all is not None else 0
        tools_options[tool_name] = tool.options
        tools_checking[tool_name] = {
            # "has_ava": 1 if tool.all_vs_all is not None else 0,
            "options": [{
                "group": opt["group"],
                "choices": ["{}:{}".format(opt["group"], e["key"]) for e in opt['entries']],
                "exclusive": 1 if opt['type'] == 'radio' else 0
            } for opt in tool.options],
            "default": ["{}:{}".format(opt["group"], e["key"]) for opt in tool.options for e in opt['entries'] if "default" in e and e["default"]]
        }

        # We get allowed files
    extensions = AllowedExtensions()

    # We create working dirs
    if MODE == "webserver":
        with Session.connect():
            s_id = Session.new()
    else:
        upload_folder = Functions.random_string(20)
        tmp_dir = config_reader.upload_folder
        upload_folder_path = os.path.join(tmp_dir, upload_folder)
        while os.path.exists(upload_folder_path):
            upload_folder = Functions.random_string(20)
            upload_folder_path = os.path.join(tmp_dir, upload_folder)
        s_id = upload_folder

    id_job = Functions.random_string(5) + "_" + datetime.datetime.fromtimestamp(time.time()).strftime('%Y%m%d%H%M%S')
    if "id_job" in request.args:
        id_job = request.args["id_job"]
    email = ""
    if "email" in request.args:
        email = request.args["email"]

    return render_template("run.html", id_job=id_job, email=email,
                           menu="run", allowed_ext=extensions.allowed_extensions_per_format, s_id=s_id,
                           max_upload_file_size=config_reader.max_upload_file_size,
                           limits={
                               "upload_size": Functions.get_readable_size(config_reader.max_upload_file_size),
                               "uncompressed_size_ava": Functions.get_readable_size(config_reader.max_upload_size_ava),
                               "uncompressed_size": Functions.get_readable_size(config_reader.max_upload_size),
                               "walltime_prepare": config_reader.cluster_walltime_prepare,
                               "walltime_align": config_reader.cluster_walltime_align,
                           },
                           example_align=config_reader.example_target != "",
                           target=os.path.basename(config_reader.example_target),
                           query=os.path.basename(config_reader.example_query),
                           example_backup=config_reader.example_backup != "",
                           backup=os.path.basename(config_reader.example_backup),
                           example_batch=config_reader.example_batch != "",
                           batch=os.path.basename(config_reader.example_batch),
                           max_batch_jobs=config_reader.max_nb_jobs_in_batch_mode,
                           tools_names=tools_names, tools=tools,
                           tools_ava=tools_ava, tools_options=tools_options, tools_checking=tools_checking,
                           version=VERSION, inforun=inforun)


@app.route("/run-test", methods=['GET'])
def run_test():
    """
    Run test page (used to simulate a real client run)
    """
    if MODE == "webserver":
        print(config_reader.allowed_ip_tests)
        if request.remote_addr not in config_reader.allowed_ip_tests:
            return abort(404)
        with Session.connect():
            return Session.new()
    return abort(500)


def create_datafile(f: str, f_type: str, upload_folder: str, example_path: str) -> DataFile:
    """
    Create DataFile object. Raise an DGeniesExampleNotAvailable if example file does not exist

   :param f: filename or url
   :type f: str
   :param f_type: file type
   :type f_type: str
   :param upload_folder: upload folder
   :type upload_folder: str
   :param example_path: example file path
   :type example_path: str
   :return: Fasta object
   :rtype: DataFile
    """
    example = False
    f_name = None
    if f.startswith("example://"):
        if example_path:
            # File path is local example file
            f_path = example_path
            f_name = os.path.basename(f_path)
            # TODO: check if re.sub(r"^example://", "", f) matches f_name
            f_type = "local"
            example = True
        else:
            raise DGeniesExampleNotAvailable
    else:
        if f_type == "local":
            f_name = os.path.splitext(re.sub(r"\.gz$", "", f))[0]
            f_path = os.path.join(app.config["UPLOAD_FOLDER"], upload_folder, f)
            # Sanitize filename
            # TODO: use secure_filename instead
            if os.path.exists(f_path):
                if " " in f:
                    new_f_path = os.path.join(app.config["UPLOAD_FOLDER"], upload_folder,
                                              f.replace(" ", "_"))
                    shutil.move(f_path, new_f_path)
                    f_path = new_f_path
            else:
                raise FileNotFoundError
        else:
            # File path is file url
            f_path = f
    return DataFile(name=f_name, path=f_path, type_f=f_type, example=example)


def check_file_type_and_resolv_options(job: dict):
    """
    Check and normalize the given job parameters.
    Job syntax and parameters constraints must have been verified on the client side.

    :param job: job parameters
    :type job: dict
    :return: (True, []) if everything is alright, (False, list of errors) else
    :rtype: (bool, list)
    """
    errors = []
    job_type = job["type"]

    if job_type == "align":
        for key in ("target", "query"):
            if job[key] is not None:
                errors.extend(check_file_type(job, key))

        if job["target"] == "":
            errors.append("No target fasta selected")

        try:
            if job["tool"] is None:
                job["tool"] = Tools().get_default()
            elif job["tool"] not in Tools().tools:
                raise DGeniesUnknownToolError(job["tool"])

            job["options"] = " ".join(get_tools_options(job["tool"], job["options"]))
        except (DGeniesUnknownToolError, DGeniesUnknownOptionError) as e:
            errors.append(e.message)

    elif job_type == "plot":
        for key in ("target", "query", "align", "backup"):
            if job[key] is not None:
                errors.extend(check_file_type(job, key))

    if errors:
        raise DGeniesJobCheckError(errors)


def check_file_type(job: dict, key: str) -> (bool, list):
    errors = []
    if job[key] and not job["{k}_type".format(k=key)]:
        errors.append("Server error: no {k}_type in form. Please contact the support".format(k=key))
    return errors


def update_files(jobs: list, upload_folder: str):
    """
    Update job list by replacing file url and file path by datafile object.
    Same path is replaced by same datafile object avoiding duplication.

    jobs:
    """
    # entries with a potential file
    file_keys = ["query", "target", "align", "backup"]
    # entries with a potential example
    keys_with_example = {k: getattr(config_reader, "example_{}".format(k)) for k in ["query", "target", "backup"]}
    datafiles = dict()  # cache for deduplication
    for j in jobs:
        for k in file_keys:
            if k in j and j[k]:
                path = j[k]
                if path in datafiles:
                    f = datafiles[path]
                else:
                    file_type = j["{}_type".format(k)]
                    f = create_datafile(path, file_type, upload_folder, keys_with_example.get(k, ""))
                    datafiles[path] = f
                j[k] = f
                del j["{}_type".format(k)]


def create_batch_file(batch_path: str, jobs: list) -> DataFile:
    # We create the batch file in tmpdir
    with open(batch_path, "wt") as outfile:
        for j in jobs:
            params_dict = {'type': j['type'], 'id_job': j['id_job']}
            params_dict.update({a: j[a].get_path() for a in ['query', 'target', 'align', 'backup'] if a in j and j[a] is not None})
            if 'tool_options' in j and j['tool_options']:
                params_dict.update({'options': j['tool_options']})
            outfile.write("{}\n".format("\t".join(["{k}={v}".format(k=k, v=v) for k, v in params_dict.items()])))
    # We must avoid that a file has the same name as batch_file
    return DataFile(name="batch", path=batch_path, type_f="local")


# Launch analysis
@app.route("/launch_analysis", methods=['POST'])
def launch_analysis():
    """
    Launch the job
    """
    if MODE == "webserver":
        try:
            with Session.connect():
                session = Session.get(s_id=request.form["s_id"])
        except DoesNotExist:
            return jsonify({"success": False, "errors": ["Session has expired. Please refresh the page and try again"]})
        upload_folder = session.upload_folder
        # Delete session:
        session.delete_instance()
    else:
        upload_folder = request.form["s_id"]

    # We get the distinct client's message elements
    id_job = request.form["id_job"]
    job_type = request.form["type"]
    email = request.form["email"]
    nb_jobs = int(request.form["nb_jobs"]) if "nb_jobs" in request.form else 0
    jobs = list()
    for i in range(0, nb_jobs):
        jt = Template("jobs[$i][$attr]") # job template
        k = jt.safe_substitute(i=i, attr="id_job")
        id_sub_job = request.form[k] if k in request.form else id_job
        # subjob
        j = {"id_job": id_sub_job,
             "email": email}
        # k: key in j, attr: key in jt
        for k, attr in (
                ("type", "type"),
                ("query", "query"),
                ("query_type", "query_type"),
                ("target", "target"),
                ("target_type", "target_type"),
                ("tool", "tool"),
                ("align", "alignfile"),
                ("align_type", "alignfile_type"),
                ("backup", "backup"),
                ("backup_type", "backup_type"),
                ("batch", "batch"),
                ("batch_type", "batch_type")
            ):
            s = jt.safe_substitute(i=i, attr=attr)
            j[k] = request.form[s] if s in request.form else None
            if j[k] == "":
                j[k] = None
        tool_options = jt.safe_substitute(i=i, attr="tool_options][")
        j["options"] = request.form.getlist(tool_options) if tool_options in request.form else []
        jobs.append(j)

    # Check form
    # Client side must have sent correct message depending on the job type.
    # Here we check that everything was correctly transmitted.
    # Convention:
    # - an element set to None is not checked
    # - an element set to "" is checked but empty.
    form_pass = True
    errors = []

    # No alignfile_type given for alignfile
    batch_mode = job_type == "batch"

    # We check job header (id + email)
    if id_job == "":
        errors.append("Id of job not given")
        form_pass = False

    # An email is required in webserver mode
    if MODE == "webserver":
        if email == "":
            errors.append("Email not given")
            form_pass = False
        elif not re.match(r"^.+@.+\..+$", email):
            # The email regex is simple because checking email address is not simple (RFC3696).
            # Sending an email to the address is the most reliable way to check if the email address is correct.
            # The only constraints we set on the email address are:
            # - to have at least one @ in it, with something before and something after
            # - to have something.tdl syntax for email server, as it will be used over Internet (not mandatory in RFC)
            errors.append("Email is invalid")
            form_pass = False

    # We check each job parameters

    for j in jobs:
        try:
            check_file_type_and_resolv_options(j)
        except DGeniesJobCheckError as e:
            form_pass = False
            errors.append(e.message)

    # Form pass
    if form_pass:
        # Get final job id (sanitize and avoid collision):
        id_job = re.sub('[^A-Za-z0-9_\-]+', '', id_job.replace(" ", "_"))
        id_job_orig = id_job
        i = 2
        while os.path.exists(os.path.join(APP_DATA, id_job)):
            id_job = id_job_orig + ("_%d" % i)
            i += 1

        folder_files = os.path.join(APP_DATA, id_job)
        os.makedirs(folder_files)

        # Transform files path into datafiles:
        try:
            update_files(jobs, upload_folder)
            if form_pass:
                # Launch job:
                job = JobManager.create(id_job=id_job, job_type=job_type, jobs=jobs, email=email, mailer=mailer)
                if MODE == "webserver":
                    job.launch()
                else:
                    job.launch_standalone()
                return jsonify({"success": True, "redirect": url_for(".status", id_job=id_job)})

        except Exception:
            traceback.print_exc()
            return jsonify({"success": False, "errors": ["Something went wrong during job creation!"]})

    if not form_pass:
        return jsonify({"success": False, "errors": errors})


def get_status(job):
    """
    Return the needed information for displaying the status page or sending the status message
    :param job: job
    :type job: JobManager
    :return: a dict containing describing the job status preparing the json answer. (TODO: describe each entry)
    :rtype: dict
    """
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
    return {
        "status": j_status["status"],
        "error": j_status["error"].replace("#ID#", ""),
        "id_job": job.id_job,
        "mem_peak": mem_peak,
        "time_elapsed": time_e
    }


# Status of a job
@app.route('/status/<id_job>', methods=['GET'])
def status(id_job):
    """
    Status page

    :param id_job: job id
    :type id_job: str
    """
    job = JobManager(id_job)
    answer = get_status(job)
    if job.is_batch():
        answer["batch"] = [get_status(JobManager(subjob_id)) for subjob_id in job.get_subjob_ids()]

    fmt = request.args.get("format")
    if fmt is not None and fmt == "json":
        return jsonify(answer)
    return render_template("status.html", status=answer["status"],
                           error=answer["error"],
                           id_job=id_job, menu="results", mem_peak=answer["mem_peak"],
                           time_elapsed=answer["time_elapsed"], do_align=job.do_align(),
                           query_filtered=job.is_query_filtered(), target_filtered=job.is_target_filtered(),
                           batch=answer["batch"] if "batch" in answer else None)


# Results path
@app.route("/result/<id_res>", methods=['GET'])
def result(id_res):
    """
    Result page

    :param id_res: job id
    :type id_res: str
    """
    res_dir = os.path.join(APP_DATA, id_res)
    return render_template("result.html", id=id_res, menu="result", current_result=id_res,
                           is_gallery=Functions.is_in_gallery(id_res, MODE),
                           fasta_file=Functions.query_fasta_file_exists(res_dir))


@app.route("/gallery", methods=['GET'])
def gallery():
    """
    Gallery page
    """
    if MODE == "webserver":
        return render_template("gallery.html", items=Functions.get_gallery_items(), menu="gallery")
    return abort(404)


@app.route("/gallery/<filename>", methods=['GET'])
def gallery_file(filename):
    """
    Getting gallery illustration

    :param filename: filename of the PNG file
    """
    if MODE == "webserver":
        try:
            return send_file(os.path.join(config_reader.app_data, "gallery", filename))
        except FileNotFoundError:
            abort(404)
    return abort(404)


def get_tools_options(tool_name, chosen_options):
    """
    Transform options chosen from client side into option values

    :param tool_name: the tool name
    :type tool_name: str
    :param chosen_options: the list of option ids
    :type chosen_options: list of str
    :return: return options value
    :rtype: list
    """
    tools = Tools().tools
    if tool_name is None or tool_name not in tools:
        raise DGeniesUnknownToolError(tool_name)
    return tools[tool_name].resolve_option_keys(chosen_options)


def get_file(file, gzip=False):  # pragma: no cover
    """
    Download a file

    :param file: filename
    :type file: str
    :param gzip: is file gzipped?
    :type gzip: bool
    """
    try:
        # Figure out how flask returns static files
        # Tried:
        # - render_template
        # - send_file
        # This should not be so non-obvious
        return open(file, "rb" if gzip else "r").read()
    except FileNotFoundError:
        abort(404)
    except IOError as exc:
        print(exc.__traceback__)
        abort(500)


@app.route("/documentation/run", methods=['GET'])
def documentation_run():
    """
    Documentation run page
    """
    latest = Latest()
    version = latest.latest
    max_upload_file_size = config_reader.max_upload_file_size
    if max_upload_file_size == -1:
        max_upload_file_size = "no limit"
    else:
        max_upload_file_size = Functions.get_readable_size(max_upload_file_size, 0)
    max_upload_size = config_reader.max_upload_size
    if max_upload_size == -1:
        max_upload_size = "no limit"
    else:
        max_upload_size = Functions.get_readable_size(max_upload_size, 0)
    max_upload_size_ava = config_reader.max_upload_size_ava
    if max_upload_size_ava == -1:
        max_upload_size_ava = "no limit"
    else:
        max_upload_size_ava = Functions.get_readable_size(max_upload_size_ava, 0)
    with open(os.path.join(app_folder, "md", "doc_run.md"), "r",  encoding='utf-8') as install_instr:
        content = install_instr.read()
    env = Environment()
    template = env.from_string(content)
    content = template.render(mode=MODE, version=version, size=max_upload_file_size, size_unc=max_upload_size,
                              size_ava=max_upload_size_ava)
    md = Markdown(extensions=[TocExtension(baselevel=1)])
    content = Markup(md.convert(content))
    toc = Markup(md.toc)
    return render_template("documentation.html", menu="documentation", content=content, toc=toc)


@app.route("/documentation/definitions", methods=['GET'])
def documentation_definitions():
    """
    Documentation result page
    """
    with open(os.path.join(app_folder, "md", "doc_definitions.md"), "r",
              encoding='utf-8') as install_instr:
        content = install_instr.read()
    md = Markdown(extensions=[TocExtension(baselevel=1)])
    content = Markup(md.convert(content))
    toc = Markup(md.toc)
    return render_template("documentation.html", menu="documentation", content=content, toc=toc)


@app.route("/documentation/result", methods=['GET'])
def documentation_result():
    """
    Documentation result page
    """
    with open(os.path.join(app_folder, "md", "user_manual.md"), "r",
              encoding='utf-8') as install_instr:
        content = install_instr.read()
    md = Markdown(extensions=[TocExtension(baselevel=1)])
    content = Markup(md.convert(content))
    toc = Markup(md.toc)
    return render_template("documentation.html", menu="documentation", content=content, toc=toc)


@app.route("/documentation/formats", methods=['GET'])
def documentation_formats():
    """
    Documentation formats page
    """
    with open(os.path.join(app_folder, "md", "doc_formats.md"), "r",
              encoding='utf-8') as install_instr:
        content = install_instr.read()
    md = Markdown(extensions=[TocExtension(baselevel=1), TableExtension()])
    content = Markup(md.convert(content))
    toc = Markup(md.toc)
    return render_template("documentation.html", menu="documentation", content=content, toc=toc)


@app.route("/documentation/dotplot", methods=['GET'])
def documentation_dotplot():
    """
    Documentation dotplot page
    """
    with open(os.path.join(app_folder, "md", "doc_dotplot.md"), "r",
              encoding='utf-8') as install_instr:
        content = install_instr.read()
    md = Markdown(extensions=[TocExtension(baselevel=1)])
    content = Markup(md.convert(content))
    toc = Markup(md.toc)
    return render_template("documentation.html", menu="documentation", content=content, toc=toc)


@app.route("/install", methods=['GET'])
def install():
    """
    Documentation: how to install? page
    """
    latest = Latest()

    with open(os.path.join(app_folder, "md", "INSTALL.md"), "r", encoding='utf-8') as install_instr:
        content = install_instr.read()
    env = Environment()
    template = env.from_string(content)
    content = template.render(version=latest.latest, win32=latest.win32)
    md = Markdown(extensions=[TocExtension(baselevel=1)])
    content = Markup(md.convert(content))
    toc = Markup(md.toc)
    return render_template("documentation.html", menu="install", content=content, toc=toc)


@app.route("/contact", methods=['GET'])
def contact():
    """
    Contact page
    """
    return render_template("contact.html", menu="contact")


@app.route("/legal/<page>", methods=['GET'])
def legal(page):
    """
    Display legal things
    """
    if page not in config_reader.legal:
        abort(404)
    with open(config_reader.legal[page], "r", encoding='utf-8') as md_page:
        content = md_page.read()
    env = Environment()
    template = env.from_string(content)
    content = template.render()
    md = Markdown(extensions=['extra', 'toc'])
    content = Markup(md.convert(content))
    return render_template("simple.html", menu="legal", content=content)


@app.route("/paf/<id_res>", methods=['GET'])
def download_paf(id_res):
    """
    Download PAF file of a job

    :param id_res: job id
    :type id_res: str
    """
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
    """
    Get dot plot data for a job
    """
    id_f = request.form["id"]
    paf = os.path.join(APP_DATA, id_f, "map.paf")
    idx1 = os.path.join(APP_DATA, id_f, "query.idx")
    idx2 = os.path.join(APP_DATA, id_f, "target.idx")

    paf = Paf(paf, idx1, idx2)

    if paf.parsed:
        valid = os.path.join(APP_DATA, id_f, ".valid")
        if not os.path.exists(valid):
            Path(valid).touch()
        res = paf.get_d3js_data()
        res["success"] = True
        return jsonify(res)
    return jsonify({"success": False, "message": paf.error})


@app.route('/sort/<id_res>', methods=['POST'])
def sort_graph(id_res):
    """
    Sort dot plot to reference

    :param id_res: job id
    :type id_res: str
    """
    if not os.path.exists(os.path.join(APP_DATA, id_res, ".all-vs-all")):
        paf_file = os.path.join(APP_DATA, id_res, "map.paf")
        idx1 = os.path.join(APP_DATA, id_res, "query.idx")
        idx2 = os.path.join(APP_DATA, id_res, "target.idx")
        paf = Paf(paf_file, idx1, idx2, False)
        paf.sort()
        if paf.parsed:
            res = paf.get_d3js_data()
            res["success"] = True
            return jsonify(res)
        return jsonify({"success": False, "message": paf.error})
    return jsonify({"success": False, "message": "Sort is not available for All-vs-All mode"})


@app.route('/reset-sort/<id_res>', methods=['POST'])
def reset_sort(id_res):
    """
    Reset sort of dot plot

    :param id_res: job id
    :type id_res: str
    """
    to_remove = [".sorted", "map.paf.sorted", "query.idx.sorted"]
    for f in to_remove:
        if os.path.exists(os.path.join(APP_DATA, id_res, f)):
            os.remove(os.path.join(APP_DATA, id_res, f))

    paf = os.path.join(APP_DATA, id_res, "map.paf")
    idx1 = os.path.join(APP_DATA, id_res, "query.idx")
    idx2 = os.path.join(APP_DATA, id_res, "target.idx")

    paf = Paf(paf, idx1, idx2)

    if paf.parsed:
        res = paf.get_d3js_data()
        res["success"] = True
        return jsonify(res)
    return jsonify({"success": False, "message": paf.error})


@app.route('/reverse-contig/<id_res>', methods=['POST'])
def reverse_contig(id_res):
    """
    Reverse contig order

    :param id_res: job id
    :type id_res: str
    """
    contig_name = request.form["contig"]
    if not os.path.exists(os.path.join(APP_DATA, id_res, ".all-vs-all")):
        paf_file = os.path.join(APP_DATA, id_res, "map.paf")
        idx1 = os.path.join(APP_DATA, id_res, "query.idx")
        idx2 = os.path.join(APP_DATA, id_res, "target.idx")
        paf = Paf(paf_file, idx1, idx2, False)
        Path(os.path.join(APP_DATA, id_res, ".new-reversals")).touch()
        paf.reverse_contig(contig_name)
        if paf.parsed:
            res = paf.get_d3js_data()
            res["success"] = True
            return jsonify(res)
        return jsonify({"success": False, "message": paf.error})
    return jsonify({"success": False, "message": "Sort is not available for All-vs-All mode"})


@app.route('/freenoise/<id_res>', methods=['POST'])
def free_noise(id_res):
    """
    Remove noise from the dot plot

    :param id_res: job id
    :type id_res: str
    """
    paf_file = os.path.join(APP_DATA, id_res, "map.paf")
    idx1 = os.path.join(APP_DATA, id_res, "query.idx")
    idx2 = os.path.join(APP_DATA, id_res, "target.idx")
    paf = Paf(paf_file, idx1, idx2, False)
    paf.parse_paf(noise=request.form["noise"] == "1")
    if paf.parsed:
        res = paf.get_d3js_data()
        res["success"] = True
        return jsonify(res)
    return jsonify({"success": False, "message": paf.error})


@app.route('/get-fasta-query/<id_res>', methods=['POST'])
def build_fasta(id_res):
    """
    Generate the fasta file of query

    :param id_res: job id
    :type id_res: str
    """
    res_dir = os.path.join(APP_DATA, id_res)
    lock_query = os.path.join(res_dir, ".query-fasta-build")
    is_sorted = os.path.exists(os.path.join(res_dir, ".sorted"))
    need_refresh = os.path.exists(os.path.join(res_dir, ".new-reversals"))
    to_compress = request.form["gzip"].lower() == "true"
    query_fasta = Functions.get_fasta_file(res_dir, "query", is_sorted and not need_refresh)
    if need_refresh:
        os.remove(os.path.join(res_dir, ".new-reversals"))
    if query_fasta is not None:
        if is_sorted and not query_fasta.endswith(".sorted"):
            # Do the sort
            Path(lock_query).touch()
            if not to_compress or MODE == "standalone":  # If compressed, it will took a long time, so not wait
                Path(lock_query + ".pending").touch()
            index_file = os.path.join(res_dir, "query.idx.sorted")
            logger.debug("Sort file{}: {}".format(" and compress" if to_compress else "", query_fasta))
            if MODE == "webserver":
                thread = threading.Timer(1, Functions.sort_fasta, kwargs={
                    "job_name": id_res,
                    "fasta_file": query_fasta,
                    "index_file": index_file,
                    "lock_file": lock_query,
                    "compress": to_compress,
                    "mailer": mailer,
                    "mode": MODE
                })
                thread.start()
            else:
                Functions.sort_fasta(job_name=id_res,
                                     fasta_file=query_fasta,
                                     index_file=index_file,
                                     lock_file=lock_query,
                                     compress=to_compress,
                                     mailer=None,
                                     mode=MODE)
            if not to_compress or MODE == "standalone":
                if MODE == "webserver":
                    i = 0
                    time.sleep(5)
                    while os.path.exists(lock_query) and (i < 2 or MODE == "standalone"):
                        i += 1
                        time.sleep(5)
                os.remove(lock_query + ".pending")
                if os.path.exists(lock_query):
                    return jsonify({"success": True, "status": 1, "status_message": "In progress"})
                return jsonify({"success": True, "status": 2, "status_message": "Done",
                                "gzip": to_compress})
            else:
                return jsonify({"success": True, "status": 1, "status_message": "In progress"})
        elif is_sorted and os.path.exists(lock_query):
            # Sort is already in progress
            return jsonify({"success": True, "status": 1, "status_message": "In progress"})
        else:
            # No sort to do or sort done
            is_compressed = query_fasta.endswith(".gz") or query_fasta.endswith(".gz.sorted")
            if to_compress and not is_compressed:
                logger.debug("Compress file: {}".format(query_fasta))
                # If compressed file is asked, we must compress it now if not done before...
                Path(lock_query).touch()
                thread = threading.Timer(1, Functions.compress_and_send_mail, kwargs={
                    "job_name": id_res,
                    "fasta_file": query_fasta,
                    "index_file": os.path.join(res_dir, "query.idx.sorted"),
                    "lock_file": lock_query,
                    "mailer": mailer
                })
                thread.start()
                return jsonify({"success": True, "status": 1, "status_message": "In progress"})
            return jsonify({"success": True, "status": 2, "status_message": "Done",
                            "gzip": is_compressed})
    else:
        return jsonify({"success": False,
                        "message": "Unable to get fasta file for query. Please contact us to report the bug"})


def build_query_as_reference(id_res):
    """
    Build fasta of query with contigs order like reference

    :param id_res: job id
    :type id_res: str
    """
    paf_file = os.path.join(APP_DATA, id_res, "map.paf")
    idx1 = os.path.join(APP_DATA, id_res, "query.idx")
    idx2 = os.path.join(APP_DATA, id_res, "target.idx")
    paf = Paf(paf_file, idx1, idx2, False, mailer=mailer, id_job=id_res)
    paf.parse_paf(False, True)
    if MODE == "webserver":
        thread = threading.Timer(0, paf.build_query_chr_as_reference)
        thread.start()
        return True
    return paf.build_query_chr_as_reference()


@app.route('/build-query-as-reference/<id_res>', methods=['POST'])
def post_query_as_reference(id_res):
    """
    Launch build fasta of query with contigs order like reference

    :param id_res: job id
    :type id_res: str
    """
    build_query_as_reference(id_res)
    return jsonify({"success": True})


@app.route('/get-query-as-reference/<id_res>', methods=['GET'])
def get_query_as_reference(id_res):
    """
    Get fasta of query with contigs order like reference

    :param id_res: job id
    :type id_res: str
    """
    if MODE != "standalone":
        return abort(404)
    return send_file(build_query_as_reference(id_res), as_attachment=True)


@app.route('/download/<id_res>/<filename>')
def download_file(id_res, filename):
    """
    Download a file from a job

    :param id_res: job id
    :type id_res: str
    :param filename: file name
    :type filename: str
    """
    file_dl = os.path.join(APP_DATA, id_res, filename)
    if os.path.isfile(file_dl):
        return send_file(file_dl)
    return abort(404)


@app.route('/fasta-query/<id_res>', defaults={'filename': ""}, methods=['GET'])
@app.route('/fasta-query/<id_res>/<filename>', methods=['GET'])  # Use fake URL in mail to set download file name
def dl_fasta(id_res, filename):
    """
    Download fasta file

    :param id_res: job id
    :type id_res: str
    :param filename: file name (not used, but can be in the URL to define download filename to the browser)
    :type filename: str
    """
    res_dir = os.path.join(APP_DATA, id_res)
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
    """
    Query - Target association TSV file

    :param id_res:
    :return:
    """
    res_dir = os.path.join(APP_DATA, id_res)
    if os.path.exists(res_dir) and os.path.isdir(res_dir):
        paf_file = os.path.join(APP_DATA, id_res, "map.paf")
        idx1 = os.path.join(APP_DATA, id_res, "query.idx")
        idx2 = os.path.join(APP_DATA, id_res, "target.idx")
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

    :param id_res: job id
    :type id_res: str
    """
    res_dir = os.path.join(APP_DATA, id_res)
    if os.path.exists(res_dir) and os.path.isdir(res_dir):
        paf_file = os.path.join(APP_DATA, id_res, "map.paf")
        idx1 = os.path.join(APP_DATA, id_res, "query.idx")
        idx2 = os.path.join(APP_DATA, id_res, "target.idx")
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
    """
    Get Dot plot summary data

    :param id_res: job id
    :type id_res: str
    """
    paf_file = os.path.join(APP_DATA, id_res, "map.paf")
    idx1 = os.path.join(APP_DATA, id_res, "query.idx")
    idx2 = os.path.join(APP_DATA, id_res, "target.idx")
    try:
        paf = Paf(paf_file, idx1, idx2, False)
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "message": "Unable to load data!"
        })
    percents = None
    s_status = "waiting"  # Accepted values: waiting, done, fail
    status_file = os.path.join(APP_DATA, id_res, ".summarize")
    fail_file = status_file + ".fail"
    if not os.path.exists(status_file):  # The job is finished or not started
        if not os.path.exists(fail_file):  # The job has not started yet or has successfully ended
            percents = paf.get_summary_stats()
            if percents is None:  # The job has not started yet
                Path(status_file).touch()
                thread = threading.Timer(0, paf.build_summary_stats, kwargs={"status_file": status_file})
                thread.start()
            else:  # The job has successfully ended
                s_status = "done"
        else:  # The job has failed
            s_status = "fail"

    if s_status == "waiting":  # The job is running
        # Check if the job end in the next 30 seconds
        nb_iter = 0
        while os.path.exists(status_file) and not os.path.exists(fail_file) and nb_iter < 10:
            time.sleep(3)
            nb_iter += 1
        if not os.path.exists(status_file):  # The job has ended
            percents = paf.get_summary_stats()
            if percents is None:  # The job has failed
                s_status = "fail"
            else:  # The job has successfully ended
                s_status = "done"

    if s_status == "fail":
        return jsonify({
            "success": False,
            "message": "Build of summary failed. Please contact us to report the bug"
        })
    return jsonify({
        "success": True,
        "percents": percents,
        "status": s_status
    })


@app.route('/backup/<id_res>')
def get_backup_file(id_res):
    """
    Download archive backup file of a job

    :param id_res: job id
    :type id_res: str
    """
    res_dir = os.path.join(APP_DATA, id_res)
    filename = "%s.tar.gz" % id_res
    tar = os.path.join(res_dir, filename)
    with xopen(tar, mode="wb", compresslevel=9) as gz_file:
        with tarfile.open(fileobj=gz_file, mode="w|") as tarf:
            for file in ("map.paf", "target.idx", "query.idx"):
                tarf.add(os.path.join(res_dir, file), arcname=file)
    response = send_from_directory(res_dir, filename, as_attachment=True)
    response.headers.remove('Content-Disposition')  # Restore flask<2 behavior (else file cannot be renamed by js side)
    return response


def get_filter_out(id_res, type_f):
    """
    Download filter fasta, when it has been filtered before job run

    :param id_res: job id
    :type id_res: str
    :param type_f: type of fasta (query or target)
    :type type_f: str
    """
    filter_file = os.path.join(APP_DATA, id_res, ".filter-" + type_f)
    return Response(get_file(filter_file), mimetype="text/plain")


@app.route('/filter-out/<id_res>/query')
def get_filter_out_query(id_res):
    """
    Download query filtered fasta, when it has been filtered before job run

    :param id_res: job id
    :type id_res: str
    """
    return get_filter_out(id_res=id_res, type_f="query")


@app.route('/filter-out/<id_res>/target')
def get_filter_out_target(id_res):
    """
    Download target filtered fasta, when it has been filtered before job run

    :param id_res: job id
    :type id_res: str
    """
    return get_filter_out(id_res=id_res, type_f="target")


@app.route('/viewer/<id_res>')
def get_viewer_html(id_res):
    """
    Get HTML file with offline interactive viewer inside

    :param id_res: job id
    :type id_res: str
    """
    paf = os.path.join(APP_DATA, id_res, "map.paf")
    idx1 = os.path.join(APP_DATA, id_res, "query.idx")
    idx2 = os.path.join(APP_DATA, id_res, "target.idx")

    paf = Paf(paf, idx1, idx2)

    if paf.parsed:
        res = paf.get_d3js_data()
        res["success"] = True
        percents = paf.get_summary_stats()
        with open(os.path.join(app_folder, "static", "js", "dgenies-offline-result.min.js"), "r") as js_min:
            js = js_min.read()
        with open(os.path.join(app_folder, "static", "css", "dgenies-offline-result.min.css"), "r") as css_min:
            css = css_min.read()
        return render_template("map_offline.html", json=json.dumps(res), version=VERSION, js=js, css=css,
                               percents=percents)
    return abort(403)


@app.route("/ask-upload", methods=['POST'])
def ask_upload():
    """
    Ask for upload: to keep a max number of concurrent uploads
    """
    if MODE == "standalone":
        return jsonify({
            "success": True,
            "allowed": True
        })
    try:
        s_id = request.form['s_id']
        with Session.connect():
            session = Session.get(s_id=s_id)
            allowed = session.ask_for_upload(True)
        return jsonify({
            "success": True,
            "allowed": allowed
        })
    except DoesNotExist:
        return jsonify({"success": False, "message": "Session not initialized. Please refresh the page."})


@app.route("/ping-upload", methods=['POST'])
def ping_upload():
    """
    When upload waiting, ping to be kept in the waiting line
    """
    if MODE == "webserver":
        s_id = request.form['s_id']
        with Session.connect():
            session = Session.get(s_id=s_id)
            session.ping()
    return "OK"


@app.route("/upload", methods=['POST'])
def upload():
    """
    Do upload of a file
    """
    try:
        s_id = request.form['s_id']
        if MODE == "webserver":
            try:
                with Session.connect():
                    session = Session.get(s_id=s_id)
                    if session.ask_for_upload(False):
                        folder = session.upload_folder
                    else:
                        return jsonify({"files": [], "success": "ERR", "message": "Not allowed to upload!"})
            except DoesNotExist:
                return jsonify(
                    {"files": [], "success": "ERR", "message": "Session not initialized. Please refresh the page."})
        else:
            folder = s_id

        files = request.files[list(request.files.keys())[0]]
        if files:
            filename = files.filename
            folder_files = os.path.join(app.config["UPLOAD_FOLDER"], folder)
            if not os.path.exists(folder_files):
                os.makedirs(folder_files)
            filename = Functions.get_valid_uploaded_filename(filename, folder_files)
            mime_type = files.content_type

            if not Functions.allowed_file(files.filename, request.form['formats'].split(",")):
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
    except:  # Except all possible exceptions to prevent crashes
        traceback.print_exc()
        return jsonify({"files": [], "success": "ERR", "message": "An unexpected error has occurred on upload. "
                                                                  "Please contact the support."})


@app.route("/send-mail/<id_res>", methods=['POST'])
def send_mail(id_res):
    """
    Send mail

    :param id_res: job id
    :type id_res: str
    """
    allowed = False
    key_file = None
    if "key" in request.form:
        key = request.form["key"]
        res_dir = os.path.join(APP_DATA, id_res)
        key_file = os.path.join(res_dir, ".key")
        if os.path.exists(key_file):
            with open(key_file) as k_f:
                true_key = k_f.readline().strip("\n")
                allowed = key == true_key
    if allowed:
        os.remove(key_file)
        job_mng = JobManager(id_job=id_res, mailer=mailer)
        job_mng.set_inputs_from_res_dir()
        job_mng.send_mail_if_allowed()
        return "OK"
    else:
        abort(403)


@app.route("/delete/<id_res>", methods=['POST'])
def delete_job(id_res):
    """
    Delete a job

    :param id_res: job id
    :type id_res: str
    """
    job = JobManager(id_job=id_res)
    try:
        job.delete()
        return jsonify({
            "success": True,
            "error": ""
        })
    except (DGeniesDeleteGalleryJobForbidden, DGeniesMissingJobError) as e:
        return jsonify({
            "success": False,
            "error": e.message
        })


@app.route("/example/backup", methods=['GET'])
def download_example_backup():
    """
    Download example batch file
    """
    example_file = config_reader.example_backup
    if not os.path.exists(example_file):
        abort(404)
    return send_file(example_file, as_attachment=True,
                     download_name=os.path.basename(example_file))


@app.route("/example/batch", methods=['GET'])
def download_example_batch():
    """
    Download example batch file
    """
    example_file = config_reader.example_batch
    if not os.path.exists(example_file):
        abort(404)
    content = get_file(example_file)
    return Response(content, mimetype="text/plain")
