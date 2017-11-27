#!/usr/bin/env python3

"""Sort PAF file

Short desc: Sort PAF file with size of matches (DESC)
Details: Sort PAF file with size of matches (DESC)

Usage:
    sort_paf.py -i PAF -o OUT
    sort_paf.py -v | --version

Options:
    -i --input=PAF  Input PAF file
    -o --output=OUT Output sorted PAF file
    -h --help   Show this screen
    -v --version    Show version
"""

import os
from docopt import docopt
from math import sqrt

__NAME__ = "PreparePAF"
__VERSION__ = 0.1


def __sort_key_paf_lines(a):
    x1 = int(a[2])
    x2 = int(a[3])
    y1 = int(a[7])
    y2 = int(a[8])
    return -sqrt(pow(x2 - x1, 2) + pow(y2 - y1, 2)) * (int(a[9]) / int(a[10]))


def __get_sorted_paf_lines(lines: iter):
    paf_lines = []
    for line in lines:
        parts = line.strip("\n").split("\t")
        paf_lines.append(parts)
    paf_lines.sort(key=lambda x: __sort_key_paf_lines(x))
    return paf_lines


def init(input_f, output_f):
    with open(input_f, "r") as paf_file:
        paf_lines = __get_sorted_paf_lines(paf_file)
        with open(output_f, "w") as out:
            out.write("\n".join(["\t".join(x) for x in paf_lines]))


if __name__ == '__main__':
    args = docopt(__doc__)
    if args["--version"]:
        print(__NAME__, __VERSION__)
    else:
        if not os.path.exists(args["--input"]):
            raise Exception("Input PAF file %s does not exists" % args["--input"])
        init(args["--input"], args["--output"])