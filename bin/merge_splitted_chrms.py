#!/usr/bin/env python3

import re
import argparse
from collections import OrderedDict


def parse_args():
    parser = argparse.ArgumentParser(description='Merge in PAF file and indexed when fasta has been split',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-pi", "--paf-in", help="Input PAF file", type=str, required=True)
    parser.add_argument("-po", "--paf-out", help="Output PAF file", type=str, required=True)
    parser.add_argument("-qi", "--query-in", help="Input query index file", type=str, required=True)
    parser.add_argument("-qo", "--query-out", help="Output query index file", type=str, required=True)
    p_args = parser.parse_args()
    return p_args


def __get_sorted_splits(contigs_split: dict, all_contigs: dict):
    """
    For each contigs_split, save how many base we will must add to each line of the corresponding split contig in PAF
    file.
    Also, save the final merged contig size in all contig dict
    :param contigs_split: split contigs
    :param all_contigs: all and final contigs
    :return: all contigs and new split contigs with start of each split contig set
    """
    new_contigs = {}
    for contig, splits_d in contigs_split.items():
        new_contigs[contig] = OrderedDict()
        splits = sorted(list(splits_d.keys()), key=lambda x: int(x))
        cum_len = 0
        for split in splits:
            new_contigs[contig][split] = cum_len  # What must be added to each line in this contig
            cum_len += splits_d[split]
        all_contigs[contig] = cum_len
    return all_contigs, new_contigs


def load_query_index(index):
    contigs = OrderedDict()
    contigs_split = {}
    with open(index) as idx_f:
        q_name = idx_f.readline().strip("\n")
        for line in idx_f:
            parts = line.strip("\n").split("\t")
            contig_name = parts[0]
            contig_len = int(parts[1])
            match_split = re.match(r"^(.+)_###_(\d+)$", contig_name)
            if match_split is not None:
                contig_name = match_split.group(1)
                if contig_name not in contigs_split:
                    contigs_split[contig_name] = {}
                nb_split = match_split.group(2)
                contigs_split[contig_name][nb_split] = contig_len
                contigs[contig_name] = None  # Will be filled after
            else:
                contigs[contig_name] = contig_len
    if len(contigs_split) > 0:
        contigs, contigs_split = __get_sorted_splits(contigs_split, contigs)
    return contigs, contigs_split, q_name


def write_query_index(index: str, contigs: dict, q_name: str):
    with open(index, "w") as idx_f:
        idx_f.write(q_name + "\n")
        for contig_name, contig_len in contigs.items():
            idx_f.write("%s\t%d\n" % (contig_name, contig_len))


def merge_paf(paf_in, paf_out, contigs, contigs_split):
    with open(paf_in) as paf_i, open(paf_out, "w") as paf_o:
        for line in paf_i:
            parts = line.strip("\n").split("\t")
            match_split = re.match(r"^(.+)_###_(\d+)$", parts[0])
            if match_split is None:
                paf_o.write(line)
            else:
                contig_name = match_split.group(1)
                nb_split = match_split.group(2)
                parts[0] = contig_name
                parts[1] = str(contigs[contig_name])
                parts[2] = str(int(parts[2]) + contigs_split[contig_name][nb_split])
                parts[3] = str(int(parts[3]) + contigs_split[contig_name][nb_split])
                paf_o.write("\t".join(parts) + "\n")


def init(paf_in, paf_out, query_in, query_out):
    print("Loading query index...")
    contigs, contigs_split, q_name = load_query_index(query_in)
    print("Merging contigs in PAF file...")
    merge_paf(paf_in, paf_out, contigs, contigs_split)
    print("Writing new query index...")
    write_query_index(query_out, contigs, q_name)
    print("DONE!")


if __name__ == '__main__':
    args = parse_args()
    exit(init(args.paf_in, args.paf_out, args.query_in, args.query_out))
