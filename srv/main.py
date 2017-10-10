#!/usr/bin/env python3

import os
import json
from flask import Flask, render_template, request
from lib.parse_paf import parse_paf

# Init Jinja2 template loader:
dirname = os.path.dirname(__file__)

# Init Flash:
app = Flask(__name__, static_url_path='/static')

# Folder containing data:
app_data = "/home/fcabanettes/public_html/test"


# Root path
@app.route("/")
def hello():
    title = "IGenoComp - An Interactive Genome Comparator"
    return render_template("index.html", title=title)


@app.route('/get_graph', methods=['POST'])
def get_graph():
    id_f = request.form["id"]
    paf = os.path.join(app_data, id_f + ".paf")
    idx1 = os.path.join(app_data, id_f + "_1.idx")
    idx2 = os.path.join(app_data, id_f + "_2.idx")

    success, res = parse_paf(paf, idx1, idx2)

    if success:
        res["success"] = True
        return json.dumps(res)
    return json.dumps({"success": False, "message": res})
