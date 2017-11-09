#!/usr/bin/env python3

"""Build Indexes

Short desc: Build index for query and target
Details: Build index for query and target, which defines contigs and chromosomes positions

Usage:
    build_indexes.py -q FASTA1 -t FASTA2 -o OUT [-r NAME1] [-u NAME2]
    build_indexes.py -v | --version

Options:
    -q --query=FASTA1    Query fasta file compared with minimap
    -t --target=FASTA2    Target fasta file compared with minimap
    -r --query-name=NAME1   Query name
    -u --target-name=NAME2  Target name
    -o --output=OUT Output directory
    -h --help   Show this screen
    -v --version    Show version
"""

__NAME__ = "PreparePAF"
__VERSION__ = 0.1

import os
from docopt import docopt
from lib.functions import Functions
from lib.Fasta import Fasta


def init(output_d, query, target, query_name=None, target_name=None):
    query_f = Fasta(query_name, query, "local")
    target_f = Fasta(target_name, target, "local")
    Functions.index_file(query_f, os.path.join(output_d, "query.idx"))
    Functions.index_file(target_f, os.path.join(output_d, "target.idx"))


if __name__ == '__main__':
    args = docopt(__doc__)
    if args["--version"]:
        print(__NAME__, __VERSION__)
    else:
        if not os.path.exists(args["--query"]):
            raise Exception("Fasta file %s does not exists!" % args["--query"])
        if not os.path.exists(args["--target"]):
            raise Exception("Fasta file %s does not exists!" % args["--target"])
        init(args["--output"], args["--query"], args["--target"], args["--query-name"], args["--target-name"])
