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
from flask import render_template, request, url_for, jsonify, Response, abort, send_file, Markup
from pathlib import Path
from dgenies.lib.paf import Paf
from dgenies.lib.job_manager import JobManager
from dgenies.lib.functions import Functions, ALLOWED_EXTENSIONS
from dgenies.lib.upload_file import UploadFile
from dgenies.lib.fasta import Fasta
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
    inforun = None
    inforun_file = os.path.join(config_reader.config_dir, ".inforun")
    if os.path.exists(inforun_file):
        try:
            with open(inforun_file, "r") as info:
                inforun = json.loads(info.read())
        except json.JSONDecodeError:
            print("Unable to parse inforun file. Ignoring it.", file=sys.stderr)
            pass
    tools = Tools().tools
    tools_names = sorted(list(tools.keys()), key=lambda x: (tools[x].order, tools[x].name))
    tools_ava = {}
    tools_options = {}
    for tool_name, tool in tools.items():
        tools_ava[tool_name] = 1 if tool.all_vs_all is not None else 0
        tools_options[tool_name] = tool.options
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
                           menu="run", allowed_ext=ALLOWED_EXTENSIONS, s_id=s_id,
                           max_upload_file_size=config_reader.max_upload_file_size,
                           example=config_reader.example_target != "",
                           target=os.path.basename(config_reader.example_target),
                           query=os.path.basename(config_reader.example_query), tools_names=tools_names, tools=tools,
                           tools_ava=tools_ava, tools_options=tools_options, version=VERSION, inforun=inforun)


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

    id_job = request.form["id_job"]
    email = request.form["email"]
    file_query = request.form["query"]
    file_query_type = request.form["query_type"]
    file_target = request.form["target"]
    file_target_type = request.form["target_type"]
    tool = request.form["tool"] if "tool" in request.form else None
    tool_options = request.form.getlist("tool_options[]")
    alignfile = request.form["alignfile"] if "alignfile" in request.form else None
    alignfile_type = request.form["alignfile_type"] if "alignfile_type" in request.form else None
    backup = request.form["backup"] if "backup" in request.form else None
    backup_type = request.form["backup_type"] if "backup_type" in request.form else None

    # Check form:
    form_pass = True
    errors = []

    if alignfile is not None and alignfile_type is None:
        errors.append("Server error: no alignfile_type in form. Please contact the support")
        form_pass = False

    if backup is not None and backup != "" and (backup_type is None or backup_type == ""):
        errors.append("Server error: no backup_type in form. Please contact the support")
        form_pass = False

    if backup is not None and backup != "":
        alignfile = ""
        file_query = ""
        file_target = ""
    else:
        backup = None
        if file_target == "":
            errors.append("No target fasta selected")
            form_pass = False

    if tool is not None and tool not in Tools().tools:
        errors.append("Tool unavailable: %s" % tool)
        form_pass = False

    valid_options, options = get_tools_options(tool, tool_options)
    if not valid_options:
        errors.append("Chosen options unavailable")
        form_pass = False

    if id_job == "":
        errors.append("Id of job not given")
        form_pass = False

    if MODE == "webserver":
        if email == "":
            errors.append("Email not given")
            form_pass = False
        elif not re.match(r"^.+@.+\..+$", email):
            # The email regex is simple because checking email address is not simple (RFC3696).
            # Sending an email to the address is the most reliable way to check if the email address is correct.
            # The only constrains we set on the email address are:
            # - to have at least one @ in it, with something before and something after
            # - to have something.tdl syntax for email server, as it will be used over Internet (not mandatory in RFC)
            errors.append("Email is invalid")
            form_pass = False

    # Form pass
    if form_pass:
        # Get final job id:
        id_job = re.sub('[^A-Za-z0-9_\-]+', '', id_job.replace(" ", "_"))
        id_job_orig = id_job
        i = 2
        while os.path.exists(os.path.join(APP_DATA, id_job)):
            id_job = id_job_orig + ("_%d" % i)
            i += 1

        folder_files = os.path.join(APP_DATA, id_job)
        os.makedirs(folder_files)

        # Save files:
        query = None
        if file_query != "":
            example = False
            if file_query.startswith("example://"):
                example = True
                query_path = config_reader.example_query
                query_name = os.path.basename(query_path)
                file_query_type = "local"
            else:
                query_name = os.path.splitext(file_query.replace(".gz", ""))[0] if file_query_type == "local" else None
                if file_query_type == "local":
                    query_path = os.path.join(app.config["UPLOAD_FOLDER"], upload_folder, file_query)
                    if os.path.exists(query_path):
                        if " " in file_query:
                            new_query_path = os.path.join(app.config["UPLOAD_FOLDER"], upload_folder,
                                                                       file_query.replace(" ", "_"))
                            shutil.move(query_path, new_query_path)
                            query_path = new_query_path
                    else:
                        errors.append("Query file not correct!")
                        form_pass = False
                else:
                    query_path = file_query
            query = Fasta(name=query_name, path=query_path, type_f=file_query_type, example=example)
        example = False
        target = None
        if file_target != "":
            if file_target.startswith("example://"):
                example = True
                target_path = config_reader.example_target
                target_name = os.path.basename(target_path)
                file_target_type = "local"
            else:
                target_name = os.path.splitext(file_target.replace(".gz", ""))[0] if file_target_type == "local" \
                    else None
                if file_target_type == "local":
                    target_path = os.path.join(app.config["UPLOAD_FOLDER"], upload_folder, file_target)
                    if os.path.exists(target_path):
                        if " " in target_path:
                            new_target_path = os.path.join(app.config["UPLOAD_FOLDER"], upload_folder,
                                                           file_target.replace(" ", "_"))
                            shutil.move(target_path, new_target_path)
                            target_path = new_target_path
                    else:
                        errors.append("Target file not correct!")
                        form_pass = False
                else:
                    target_path = file_target
            target = Fasta(name=target_name, path=target_path, type_f=file_target_type, example=example)

        if alignfile is not None and alignfile != "" and backup is not None:
            Path(os.path.join(folder_files, ".align")).touch()

        align = None
        if alignfile is not None and alignfile != "":
            alignfile_name = os.path.splitext(alignfile)[0] if alignfile_type == "local" else None
            alignfile_path = os.path.join(app.config["UPLOAD_FOLDER"], upload_folder, alignfile) \
                if alignfile_type == "local" else alignfile
            if alignfile_type == "local" and not os.path.exists(alignfile_path):
                errors.append("Alignment file not correct!")
                form_pass = False
            align = Fasta(name=alignfile_name, path=alignfile_path, type_f=alignfile_type)

        bckp = None
        if backup is not None:
            backup_name = os.path.splitext(backup)[0] if backup_type == "local" else None
            backup_path = os.path.join(app.config["UPLOAD_FOLDER"], upload_folder, backup) \
                if backup_type == "local" else backup
            if backup_type == "local" and not os.path.exists(backup_path):
                errors.append("Backup file not correct!")
                form_pass = False
            bckp = Fasta(name=backup_name, path=backup_path, type_f=backup_type)

        if form_pass:
            # Launch job:
            job = JobManager(id_job=id_job,
                             email=email,
                             query=query,
                             target=target,
                             align=align,
                             backup=bckp,
                             mailer=mailer,
                             tool=tool,
                             options=options)
            if MODE == "webserver":
                job.launch()
            else:
                job.launch_standalone()
            return jsonify({"success": True, "redirect": url_for(".status", id_job=id_job)})
    if not form_pass:
        return jsonify({"success": False, "errors": errors})


# Status of a job
@app.route('/status/<id_job>', methods=['GET'])
def status(id_job):
    """
    Status page

    :param id_job: job id
    :type id_job: str
    """
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
    return render_template("status.html", status=j_status["status"],
                           error=j_status["error"].replace("#ID#", ""),
                           id_job=id_job, menu="results", mem_peak=mem_peak,
                           time_elapsed=time_e, do_align=job.do_align(),
                           query_filtered=job.is_query_filtered(), target_filtered=job.is_target_filtered())


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
    Transform options chosen in javascript into parameters

    :return: True is chosen options are valid + a string containing optional parameters to use with tool
    :rtype: boolean, str
    """
    tools = Tools().tools
    if tool_name is None:
        return True, None
    tool = tools[tool_name] if tool_name in tools else None
    tool_options = tool.options if tool is not None else None
    # We filter options for the chosen tool.
    tool_prefix = "tool-options-%s-" % tool_name
    filtered_options = [s[len(tool_prefix):].split("-") for s in chosen_options if s.startswith(tool_prefix)]
    valid = True
    options_params = None
    try:
        options_params = [tool_options[int(o)]['entries'][int(e)]['value'] for o, e in filtered_options]
    except KeyError:
        valid = False
    except IndexError:
        valid = False
    return True, " ".join(options_params)


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
    compressed = request.form["gzip"].lower() == "true"
    query_fasta = Functions.get_fasta_file(res_dir, "query", is_sorted)
    if query_fasta is not None:
        if is_sorted and not query_fasta.endswith(".sorted"):
            # Do the sort
            Path(lock_query).touch()
            if not compressed or MODE == "standalone":  # If compressed, it will took a long time, so not wait
                Path(lock_query + ".pending").touch()
            index_file = os.path.join(res_dir, "query.idx.sorted")
            if MODE == "webserver":
                thread = threading.Timer(1, Functions.sort_fasta, kwargs={
                    "job_name": id_res,
                    "fasta_file": query_fasta,
                    "index_file": index_file,
                    "lock_file": lock_query,
                    "compress": compressed,
                    "mailer": mailer,
                    "mode": MODE
                })
                thread.start()
            else:
                Functions.sort_fasta(job_name=id_res,
                                     fasta_file=query_fasta,
                                     index_file=index_file,
                                     lock_file=lock_query,
                                     compress=compressed,
                                     mailer=None,
                                     mode=MODE)
            if not compressed or MODE == "standalone":
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
                                "gzip": compressed})
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
                    "mailer": mailer
                })
                thread.start()
                return jsonify({"success": True, "status": 1, "status_message": "In progress"})
            return jsonify({"success": True, "status": 2, "status_message": "Done",
                            "gzip": query_fasta.endswith(".gz") or query_fasta.endswith(".gz.sorted")})
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
    return send_file(build_query_as_reference(id_res))


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
    tar = os.path.join(res_dir, "%s.tar.gz" % id_res)
    with xopen(tar, mode="wb", compresslevel=9) as gz_file:
        with tarfile.open(fileobj=gz_file, mode="w|") as tarf:
            for file in ("map.paf", "target.idx", "query.idx"):
                tarf.add(os.path.join(res_dir, file), arcname=file)
    return send_file(tar)


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
        job_mng.send_mail()
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
    success, error = job.delete()
    return jsonify({
        "success": success,
        "error": error
    })