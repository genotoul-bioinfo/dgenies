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
from collections import OrderedDict


class Fasta:
    def __init__(self, fasta, name=None):
        self.fasta = fasta
        self.fai = fasta + ".fai"
        self.name = os.path.splitext(os.path.basename(fasta))[0] if name is None else name
        self.contigs = OrderedDict()
        self.total_length = 0
        self.__load()

    def __load(self):
        start = 0
        with open(self.fai, "r") as fai_file:
            for line in fai_file:
                parts = line.strip("\n").split("\t")
                length = int(parts[1])
                self.contigs[parts[0]] = {
                    "length": length,
                    "start": start
                }
                start += length
                self.total_length += length

    def get_contig(self, contig):
        return self.contigs[contig]

    def build_index(self, filename):
        with open(filename, "w") as idx:
            idx.write(self.name + "\n")
            for contig, props in self.contigs.items():
                idx.write("\t".join([contig, str(props["length"])]) + "\n")


def init(output_d, query, target, query_name=None, target_name=None):
    query = Fasta(query, query_name)
    target = Fasta(target, target_name)
    i = 0
    for fasta in [query, target]:
        idx_file = os.path.join(output_d, "query.idx" if i == 0 else "target.idx")
        fasta.build_index(idx_file)
        i += 1


if __name__ == '__main__':
    args = docopt(__doc__)
    if args["--version"]:
        print(__NAME__, __VERSION__)
    else:
        if not os.path.exists(args["--query"] + ".fai"):
            raise Exception("Fasta file %s is not indexed!" % args["--query"])
        if not os.path.exists(args["--target"] + ".fai"):
            raise Exception("Fasta file %s is not indexed!" % args["--target"])
        init(args["--output"], args["--query"], args["--target"], args["--query-name"], args["--target-name"])
