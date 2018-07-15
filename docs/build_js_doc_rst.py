#!/usr/bin/env python3

import os
import re
import shutil
from glob import glob
from collections import OrderedDict


PACKAGES = ["dgenies", "d3.boxplot"]
EXCLUDES = ["dgenies.prototypes"]


def parse_js_file(module_name, file_path, js_writer, separator):
    with open(file_path) as js_f:
        js_writer.write(module_name + "\n")
        js_writer.write(len(module_name) * separator + "\n\n")
        js_code = js_f.read()
        functions_doc = re.findall(r"/\*\*.*?\*/\n([^\n/]+) = function", js_code, re.DOTALL)
        functions_doc.sort(key=lambda x: "0000000" if x.rsplit(".", 1)[-1] == "init" else
                           (("zzzzzzzzzz" + x) if x.rsplit(".", 1)[-1].startswith("_") else x))
        for func in functions_doc:
            js_writer.write(".. js:autofunction:: " + func + "\n")
        all_functions = re.findall(r"\n([^\n/]+) = function\s?\(", js_code)
        print(module_name, ":", len(functions_doc) / len(all_functions) * 100, "%")
        js_writer.write("\n")


def get_modules_list():
    modules = OrderedDict()
    for package in PACKAGES:
        submodules = sorted(map(lambda x: os.path.basename(x).rsplit(".", 1)[0],
                            filter(lambda x: not x.endswith(".min.js"),
                            glob(os.path.abspath(os.path.join("..", "src", "dgenies", "static", "js", package + "*"))))
                            ), key=lambda x: x[:-3])
        if submodules[0] != package:
            print(submodules)
            raise Exception("Error with package %s: package js file not found" % package)
        if len(submodules) > 1:
            submodules = submodules[1:]
            subpackages = OrderedDict()
            has_subsubpackages = False
            for submodule in submodules:
                if submodule not in EXCLUDES:
                    is_subsubpackage = False
                    for subpackage in subpackages:
                        if subpackage in submodule:
                            is_subsubpackage = True
                            subpackages[subpackage].append(submodule)
                            has_subsubpackages = True
                            break
                    if not is_subsubpackage:
                        subpackages[submodule] = []

            if has_subsubpackages:
                modules[package] = subpackages
            else:
                if len(subpackages) > 0:
                    modules[package] = list(subpackages.keys())
                else:
                    modules[package] = None
        else:
            modules[package] = None

    return modules


def build_rst_files():
    if os.path.exists("javascript"):
        shutil.rmtree("javascript")
    os.mkdir("javascript")

    if os.path.exists("javascript/js"):
        shutil.rmtree("javascript/js")
    os.mkdir("javascript/js")

    app_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    js_dir = os.path.join(app_dir, "src", "dgenies", "static", "js")
    js_files =  set()
    for package in PACKAGES:
        for file in glob(os.path.join(js_dir, package + "*")):
            is_excl = False
            for excl in EXCLUDES:
                if os.path.basename(file).startswith(excl):
                    is_excl = True
                    break
            if not is_excl and not file.endswith(".min.js"):
                js_files.add(file)

    for js_file in js_files:
        os.symlink(js_file, os.path.join("javascript", "js", os.path.basename(js_file)))

    print("Parse javascript files...")
    js_files = get_modules_list()

    with open("javascript/index.rst", "w") as rst:
        rst.write("Javascript client functions\n"
                  "***************************\n"
                  "\n")

        for package, subpackages in js_files.items():
            js_file_path = os.path.abspath(os.path.join("..", "src", "dgenies", "static", "js", package + ".js"))
            package_file = "javascript/%s.rst" % package
            rst.write("\n.. toctree::\n"
                      "\n"
                      "   %s.rst\n" % package)
            with open(package_file, "w") as rst_p:
                parse_js_file(package, js_file_path, rst_p, "=")
                if subpackages is None:
                    continue
                if type(subpackages) == list:
                    for subpackage in subpackages:
                        js_file_path_sp = os.path.abspath(
                            os.path.join("..", "src", "dgenies", "static", "js", subpackage + ".js"))
                        parse_js_file(subpackage, js_file_path_sp, rst_p, "-")
                elif type(subpackages) == OrderedDict:
                    for subpackage, subsubpackages in subpackages.items():
                        if subsubpackages is not None and type(subsubpackages) != list:
                            raise Exception("Two many ranges of items: subsubpackages must be a list.\n"
                                            "This error occurs with subpackage %s" % subpackage)
                        rst_p.write("\n.. toctree::\n"
                                    "\n"
                                    "   %s.rst\n" % subpackage)
                        js_file_path_sp = os.path.abspath(
                            os.path.join("..", "src", "dgenies", "static", "js", subpackage + ".js"))
                        subpackage_file = "javascript/%s.rst" % subpackage
                        with open(subpackage_file, "w") as rst_sp:
                            parse_js_file(subpackage, js_file_path_sp, rst_sp, "=")
                            if len(subsubpackages) > 0:
                                for subsubpackage in subsubpackages:
                                    js_file_path_ssp = os.path.abspath(
                                        os.path.join("..", "src", "dgenies", "static", "js", subsubpackage + ".js"))
                                    parse_js_file(subsubpackage, js_file_path_ssp, rst_sp, "-")


if __name__ == "__main__":
    build_rst_files()
    # print(get_modules_list())
