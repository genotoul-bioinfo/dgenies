#!/usr/bin/env python3

import sys
import os
import re
import gzip
import io
from collections import OrderedDict


class Splitter:

    def __init__(self, input_f, name_f, output_f, size_c=10000000, query_index="query_split.idx", debug=False):
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
        Split contigs in smaller ones
        :return: True if the Fasta is correct, else False
        """
        has_header = False
        next_header = False  # True if next line must be a header line
        with (gzip.open(self.input_f) if self.input_gz else open(self.input_f)) as gz_file, \
                (gzip.open(self.output_f, "wb") if self.output_gz else open(self.output_f, "w"))  as o_file:
            with (io.TextIOWrapper(gz_file) if self.input_gz else gz_file) as fasta, \
                    (io.TextIOWrapper(o_file, encoding='utf-8') if self.output_gz else o_file) as enc, \
                    open(self.index_file, "w") as index_f:
                index_f.write(self.name_f + "\n")
                chr_name = None
                fasta_str = ""
                for line in fasta:
                    line = line.strip("\n")
                    if re.match(r"^>.+", line) is not None:
                        has_header = True
                        next_header = False
                        if chr_name is not None and len(fasta_str) > 0:
                            self.nb_contigs += 1
                            self.flush_contig(fasta_str, chr_name, self.size_c, enc, index_f)
                        elif chr_name is not None:
                            return False
                        chr_name = re.split("\s", line[1:])[0]
                        fasta_str = ""
                        if self.debug:
                            print("Parsing contig \"%s\"... " % chr_name, end="")
                    elif len(line) > 0:
                        if next_header or re.match(r"^[ATGCKMRYSWBVHDXN.\-]+$", line.upper()) is None:
                            return False
                        fasta_str += line
                    elif len(line) == 0:
                        next_header = True
                self.nb_contigs += 1
                self.flush_contig(fasta_str, chr_name, self.size_c, enc, index_f)
        return has_header

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
