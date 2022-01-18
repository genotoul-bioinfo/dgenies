#!/usr/bin/env python3

import sys
import os
import re
from xopen import xopen
import io
from collections import OrderedDict


class Splitter:

    """
    Split large contigs in smaller ones
    """

    def __init__(self, input_f, name_f, output_f, size_c=10000000, query_index="query_split.idx", debug=False):
        """

        :param input_f: input fasta file path
        :type input_f: str
        :param name_f: sample name
        :type name_f: str
        :param output_f: output fasta file path
        :type output_f: str
        :param size_c: size of split contigs
        :type size_c: int
        :param query_index: index file path for query
        :type query_index: str
        :param debug: True to enable debug mode
        :type debug: bool
        """
        self.input_f = input_f
        self.name_f = name_f
        self.size_c = size_c
        self.output_f = output_f
        self.input_gz = input_f.endswith(".gz")
        self.output_gz = output_f.endswith(".gz")
        self.out_dir = os.path.dirname(output_f)
        self.index_file = os.path.join(self.out_dir, query_index)
        self.nb_contigs = 0
        self.debug = debug

    def split(self):
        """
        Split contigs in smaller ones staff

        :return: True if the input Fasta is correct, else False
        """
        has_header = False
        next_header = False  # True if next line must be a header line
        with (xopen(self.input_f, mode="r") if self.input_gz else open(self.input_f, mode="r")) as fasta, \
            (xopen(self.output_f, mode="w") if self.output_gz else open(self.output_f, mode="w")) as enc, \
                open(self.index_file, mode="w") as index_f:
            index_f.write(self.name_f + "\n")
            chr_name = None
            fasta_str = ""
            nb_line = 0
            for line in fasta:
                nb_line += 1
                line = line.strip("\n")
                if re.match(r"^>.+", line) is not None:
                    has_header = True
                    next_header = False
                    if chr_name is not None and len(fasta_str) > 0:
                        self.nb_contigs += 1
                        self.flush_contig(fasta_str, chr_name, self.size_c, enc, index_f)
                    elif chr_name is not None:
                        return False, "Error: contig is empty: %s" % chr_name
                    chr_name = re.split("\s", line[1:])[0]
                    fasta_str = ""
                    if self.debug:
                        print("Parsing contig \"%s\"... " % chr_name, end="")
                elif len(line) > 0:
                    if next_header or re.match(r"^[ATGCKMRYSWBVHDXN.\-]+$", line.upper()) is None:
                        if next_header:
                            return False, "Error: new header line expected at line %d" % nb_line
                        return False, "Error: invalid sequence at line %d" % nb_line
                    fasta_str += line
                elif len(line) == 0:
                    next_header = True
            self.nb_contigs += 1
            self.flush_contig(fasta_str, chr_name, self.size_c, enc, index_f)
        return has_header, ""

    @staticmethod
    def write_contig(name, fasta, o_file):
        o_file.write(">%s\n" % name)
        f_len = len(fasta)
        i = 0
        while i<f_len:
            j = min (i+60, f_len)
            o_file.write(fasta[i:j] + "\n")
            i = j
        o_file.write("\n")

    @staticmethod
    def split_contig(name, sequence, block_sizes):
        seq_len = len(sequence)
        contigs = OrderedDict()
        if seq_len < block_sizes + block_sizes * 0.1:  # Only one block size
            contigs[name] = sequence
            return contigs
        i = 0
        n = 1
        while i < seq_len:
            j = i + block_sizes
            if (j > seq_len) or ((i + (block_sizes * 0.1)) >= seq_len):
                j = seq_len
            contigs[name + ("_###_%d" % n)] = sequence[i:j]
            i = j
            n += 1
        return contigs

    def flush_contig(self, fasta_str, chr_name, size_c, enc, index_f):
        if len(fasta_str) > 0 and chr_name is not None:
            contigs = self.split_contig(chr_name, fasta_str, size_c)
            for name, seq in contigs.items():
                self.write_contig(name, seq, enc)
                index_f.write("%s\t%d\n" % (name, len(seq)))
            nb_contigs = len(contigs)
            if self.debug:
                if nb_contigs == 1:
                    print("Keeped!")
                else:
                    print("Splited in %d contigs!" % nb_contigs)


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(description="Split huge contigs")
    parser.add_argument('-i', '--input', type=str, required=True, help="Input fasta file")
    parser.add_argument('-n', '--name', type=str, required=True, help="Input fasta name")
    parser.add_argument('-s', '--size', type=int, required=False, default=10, help="Max size of contigs (Mb)")
    parser.add_argument('-o', '--output', type=str, required=True, help="Output fasta file")
    args = parser.parse_args()

    if args.size < 0:
        parser.error("Max size of contigs must be positive")

    return args


def __main__():
    args = parse_args()
    splitter = Splitter(args.input, args.name, args.output, args.size * 1000000)
    return not splitter.split()


if __name__ == '__main__':
    sys.exit(__main__())
