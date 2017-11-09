#!/usr/bin/env python3

import sys
import argparse
import gzip
import io
from collections import OrderedDict


def write_contig(name, fasta, o_file):
    o_file.write(">%s\n" % name)
    f_len = len(fasta)
    i = 0
    while i<f_len:
        j = min (i+60, f_len)
        o_file.write(fasta[i:j] + "\n")
        i = j
    o_file.write("\n")


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


def init(input_f, size_c, output_f):
    input_gz = input_f.endswith(".gz")
    output_gz = output_f.endswith(".gz")
    with (gzip.open(input_f) if input_gz else open(input_f)) as gz_file, (gzip.open(output_f, "wb") if output_gz else open(output_f, "w"))  as o_file:
        with (io.TextIOWrapper(gz_file) if input_gz else gz_file) as fasta, (io.TextIOWrapper(o_file, encoding='utf-8') if output_gz else o_file) as enc:
            chr_name = None
            fasta_str = ""
            for line in fasta:
                line = line.strip("\n")
                if line.startswith(">"):
                    if len(fasta_str) > 0 and chr_name is not None:
                        contigs = split_contig(chr_name, fasta_str, size_c)
                        for name, seq in contigs.items():
                            write_contig(name, seq, enc)
                        nb_contigs = len(contigs)
                        if nb_contigs == 1:
                            print("Keeped!")
                        else:
                            print("Splited in %d contigs!" % nb_contigs)
                    chr_name = line[1:].split(" ")[0]
                    fasta_str = ""
                    print("Parsing contig \"%s\"... " % chr_name, end="")
                elif len(line) > 0:
                    fasta_str += line


def parse_args():
    parser = argparse.ArgumentParser(description="Split huge contigs")
    parser.add_argument('-i', '--input', type=str, required=True, help="Input fasta file")
    parser.add_argument('-s', '--size', type=int, required=False, default=10, help="Max size of contigs (Mb)")
    parser.add_argument('-o', '--output', type=str, required=True, help="Output fasta file")
    args = parser.parse_args()

    if args.size < 0:
        parser.error("Max size of contigs must be positive")

    return args


def __main__():
    args = parse_args()
    return(init(args.input, args.size * 1000000, args.output))


if __name__ == '__main__':
    sys.exit(__main__())
