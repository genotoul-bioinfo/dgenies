#!/usr/bin/env python3

import os
import re
import shutil
try:
    from dgenies.bin.index import Index
except ImportError:
    from index import Index
from pathlib import Path
from Bio import SeqIO


class Filter:

    """
    Filter of a fasta file: remove too small contigs
    """

    def __init__(self, fasta, index_file, type_f, min_filtered=0, split=False, out_fasta=None, replace_fa=False):
        """

        :param fasta: fasta file path
        :type fasta: str
        :param index_file: index file path
        :type index_file: str
        :param type_f: type of sample (query or target)
        :type type_f: str
        :param min_filtered: minimum number of large contigs to allow filtering
        :type min_filtered: int
        :param split: are contigs split
        :type split: bool
        :param out_fasta: output fasta file path
        :type out_fasta: str
        :param replace_fa: if True, replace fasta file
        :type replace_fa: bool
        """
        self.fasta = fasta
        self.index_file = index_file
        self.type_f = type_f
        self.min_filtered = min_filtered
        self.split = split
        if out_fasta is not None:
            self.out_fasta = out_fasta
        else:
            self.out_fasta = os.path.join(os.path.dirname(self.fasta), "filtered_" + os.path.basename(self.fasta))
        self.replace_fa = replace_fa

    def filter(self):
        """
        Run filter of contigs

        :return: True if success, else False
        :rtype: bool
        """
        f_outs = self._check_filter()
        if len(f_outs) > 0:
            self._filter_out(f_outs=f_outs)
            return True
        return False

    def _check_filter(self):
        """
        Load index of fasta file, and determine contigs which must be removed. Remove them only in the index

        :return: list of contigs which must be removed
        :rtype: list
        """
        # Load contigs:
        name, order, contigs, reversed_c, abs_start, c_len = Index.load(index_file=self.index_file,
                                                                        merge_splits=self.split)

        # Sort contigs:
        contigs_order = sorted(order, key=lambda x: -contigs[x])

        # Find the N90:
        sum_l = 0
        n95_contig = None
        n95_value = 0.95 * c_len
        pos = -1
        len_small_contigs = 0
        len_1_pct = 0.01 * c_len
        for contig in contigs_order:
            pos += 1
            sum_l += contigs[contig]
            if contigs[contig] < len_1_pct:
                len_small_contigs += contigs[contig]
            if sum_l >= n95_value:
                n95_contig = contig

        if self.type_f == "query" and len_small_contigs >= 0.7 * 0.95 * c_len:
            Path(os.path.join(os.path.dirname(self.fasta), ".do-sort")).touch()

        # Min length of contigs
        min_length = 0.05 * contigs[n95_contig]

        f_outs = []

        breakpoint = None

        for contig in contigs_order[pos:]:
            if contigs[contig] < min_length:
                breakpoint = pos
                break
            pos += 1

        if breakpoint is not None:
            f_outs = contigs_order[breakpoint:]
            if len(f_outs) > self.min_filtered:
                with open(os.path.join(os.path.dirname(self.fasta), ".filter-" + self.type_f), "w") as list_f:
                    list_f.write("\n".join(f_outs) + "\n")
                kept = contigs_order[:breakpoint]
                if self.split:
                    f_outs = []
                    name, contigs_order_split, contigs, reversed_c, abs_start_split, c_len_split = \
                        Index.load(index_file=self.index_file, merge_splits=False)
                    kept_s = []
                    for contig in contigs_order_split:
                        match = re.match(r"(.+)_###_\d+", contig)
                        contig_name = contig
                        if match is not None:
                            contig_name = match.group(1)
                        if contig_name in kept:
                            kept_s.append(contig)
                        else:
                            f_outs.append(contig)
                    kept = kept_s
                else:
                    kept.sort(key=lambda k: order.index(k))
                Index.save(index_file=self.index_file,
                           name=name,
                           contigs=contigs,
                           order=kept,
                           reversed_c=reversed_c)
            else:
                f_outs = []

        return f_outs

    def _filter_out(self, f_outs):
        """
        Remove too small contigs from Fasta file

        :param f_outs: contigs which must be filtered out
        :type f_outs: list
        """
        sequences = SeqIO.parse(open(self.fasta), "fasta")
        keeped = (record for record in sequences if record.name not in f_outs)
        with open(self.out_fasta, "w") as out_fa:
            SeqIO.write(keeped, out_fa, "fasta")

        if self.replace_fa:
            os.remove(self.fasta)
            shutil.move(self.out_fasta, self.fasta)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Filter too small contigs")
    parser.add_argument('-f', '--fasta', type=str, required=True, help="Input fasta file")
    parser.add_argument('-i', '--index', type=str, required=True, help="Index file for the fasta file")
    parser.add_argument('-t', '--type', type=str, required=True, choices=["query", "target"],
                        help="Type of fasta: query or target")
    parser.add_argument('-m', '--min-filtered', type=int, required=False, default=0,
                        help="Minimum number of filtered contigs")
    parser.add_argument('-r', "--replace-fasta", action='store_const', const=True, default=False,
                        help="Replace original fasta file")
    parser.add_argument('-s', "--split", action='store_const', const=True, default=False,
                        help="Is fasta split")
    args = parser.parse_args()

    filter_f = Filter(fasta=args.fasta,
                      index_file=args.index,
                      type_f=args.type,
                      min_filtered=args.min_filtered,
                      split=args.split,
                      replace_fa=args.replace_fasta)
    filter_f.filter()
