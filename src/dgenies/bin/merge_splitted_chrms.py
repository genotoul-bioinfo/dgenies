#!/usr/bin/env python3

import re
from collections import OrderedDict


class Merger:

    """
    Merge splitted contigs together in PAF file
    """

    def __init__(self, paf_in, paf_out, query_in, query_out, debug=False):
        """

        :param paf_in: input PAF file path
        :type paf_in: str
        :param paf_out: output PAF file path
        :type paf_out: str
        :param query_in: input query index file path
        :type query_in: str
        :param query_out: output query index file path
        :type query_out: str
        :param debug: True to enable debug mode
        :type debug: bool
        """
        self.paf_in = paf_in
        self.paf_out = paf_out
        self.query_in = query_in
        self.query_out = query_out
        self.debug = debug

    def _printer(self, message):
        """
        Print debug messages if debug mode enabled

        :param message: message to print
        :type message: str
        """
        if self.debug:
            print(message)

    def merge(self):
        """
        Launch the merge
        """
        self._printer("Loading query index...")
        contigs, contigs_split, q_name = self.load_query_index(self.query_in)

        self._printer("Merging contigs in PAF file...")
        self.merge_paf(self.paf_in, self.paf_out, contigs, contigs_split)

        self._printer("Writing new query index...")
        self.write_query_index(self.query_out, contigs, q_name)

        self._printer("DONE!")

    @staticmethod
    def _get_sorted_splits(contigs_split, all_contigs):
        """
        For each contigs_split, save how many base we will must add to each line of the corresponding split contig in PAF
        file.
        Also, save the final merged contig size in all contig dict

        :param contigs_split: split contigs
        :type contigs_split: dict
        :param all_contigs: all and final contigs
        :type all_contigs: dict
        :return: all contigs and new split contigs with start of each split contig set
        :rtype: (dict, dict)
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

    def load_query_index(self, index):
        """
        Load query index

        :param index: index file path
        :type index: str
        :return:
            * [0] contigs length
            * [1] splitted contigs length
            * [2] sample name
        :rtype: (dict, dict, str)
        """
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
            contigs, contigs_split = self._get_sorted_splits(contigs_split, contigs)
        return contigs, contigs_split, q_name


    @staticmethod
    def write_query_index(index, contigs, q_name):
        """
        Save new query index

        :param index: index file path
        :type index: str
        :param contigs: contigs size
        :type contigs: dict
        :param q_name: sample name
        :type q_name: str
        """
        with open(index, "w") as idx_f:
            idx_f.write(q_name + "\n")
            for contig_name, contig_len in contigs.items():
                idx_f.write("%s\t%d\n" % (contig_name, contig_len))

    @staticmethod
    def merge_paf(paf_in, paf_out, contigs, contigs_split):
        """
        Do merge PAF staff

        :param paf_in: path of input PAF with split contigs
        :type paf_in: str
        :param paf_out: path of output PAF where split contigs are now merged together
        :type paf_out: str
        :param contigs: contigs size
        :type contigs: dict
        :param contigs_split: split contigs size
        :type contigs_split: dict
        """
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


def parse_args():
    """
    Parse command line arguments

    :return: arguments
    :rtype: argparse.Namespace
    """
    import argparse

    parser = argparse.ArgumentParser(description='Merge in PAF file and indexed when fasta has been split',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-pi", "--paf-in", help="Input PAF file", type=str, required=True)
    parser.add_argument("-po", "--paf-out", help="Output PAF file", type=str, required=True)
    parser.add_argument("-qi", "--query-in", help="Input query index file", type=str, required=True)
    parser.add_argument("-qo", "--query-out", help="Output query index file", type=str, required=True)
    p_args = parser.parse_args()
    return p_args


if __name__ == '__main__':
    args = parse_args()
    merger = Merger(args.paf_in, args.paf_out, args.query_in, args.query_out)
    exit(merger.merge())
