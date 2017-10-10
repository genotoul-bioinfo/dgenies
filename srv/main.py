#!/usr/bin/env python3

import os
import json
from flask import Flask, render_template, request
from lib.parse_paf import parse_paf

app_title = "ALGECO - A Live GEnome COmparator"

# Init Flash:
app = Flask(__name__, static_url_path='/static')

# Folder containing data:
app_data = "/home/fcabanettes/public_html/test"


# Root path
@app.route("/result/<id_res>", methods=['GET'])
def result(id_res):
    title = app_title
    return render_template("index.html", title=title, id=id_res)


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
