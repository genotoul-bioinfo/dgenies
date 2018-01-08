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
from math import sqrt

__NAME__ = "Sort_paf"
__VERSION__ = 0.1


class Sorter:

    def __init__(self, input_f, output_f):
        self.input_f = input_f
        self.output_f = output_f

    def sort(self):
        with open(self.input_f, "r") as paf_file:
            paf_lines = self._get_sorted_paf_lines(paf_file)
            with open(self.output_f, "w") as out:
                out.write("\n".join(["\t".join(x) for x in paf_lines]))

    @staticmethod
    def _sort_key_paf_lines(a):
        x1 = int(a[2])
        x2 = int(a[3])
        y1 = int(a[7])
        y2 = int(a[8])
        return -sqrt(pow(x2 - x1, 2) + pow(y2 - y1, 2)) * (int(a[9]) / int(a[10]))

    def _get_sorted_paf_lines(self, lines: iter):
        paf_lines = []
        for line in lines:
            parts = line.strip("\n").split("\t")
            paf_lines.append(parts)
        paf_lines.sort(key=lambda x: self._sort_key_paf_lines(x))
        return paf_lines


if __name__ == '__main__':
    from docopt import docopt
    args = docopt(__doc__)
    if args["--version"]:
        print(__NAME__, __VERSION__)
    else:
        if not os.path.exists(args["--input"]):
            raise Exception("Input PAF file %s does not exists" % args["--input"])
        sorter = Sorter(args["--input"], args["--output"])
        sorter.sort()
