#!/usr/bin/env python3

import io
import re
from xopen import xopen


class Index:

    """
    Manage Fasta Index
    """

    def __init__(self):
        pass

    @staticmethod
    def load(index_file, merge_splits=False):
        """
        Load index

        :param index_file: index file path
        :type index: str
        :param merge_splits: if True, merge split contigs together
        :type merge_splits: bool
        :return:
            * [0] sample name
            * [1] contigs order
            * [2] contigs size
            * [3] reversed status for each contig
            * [4] absolute start position for each contig
            * [5] total len of the sample
        :rtype: (str, list, dict, dict, dict, int)
        """
        with open(index_file, "r") as idx_q_f:
            abs_start = {}
            abs_current_start = 0
            c_len = 0
            name = idx_q_f.readline().strip("\n")
            order = []
            contigs = {}
            reversed_c = {}
            for line in idx_q_f:
                parts = line.strip("\n").split("\t")
                id_c = parts[0]
                is_split = False
                if merge_splits:
                    match = re.match(r"(.+)_###_\d+", id_c)
                    if match is not None:
                        id_c = match.group(1)
                        is_split = True
                len_c = int(parts[1])
                if len(parts) > 2:
                    reversed_c[id_c] = parts[2] == "1"
                else:
                    reversed_c[id_c] = False
                if not is_split or (is_split and id_c not in order):
                    order.append(id_c)
                    abs_start[id_c] = abs_current_start
                    contigs[id_c] = len_c
                else:
                    contigs[id_c] += len_c
                c_len += len_c
                abs_current_start += len_c
            return name, order, contigs, reversed_c, abs_start, c_len

    @staticmethod
    def save(index_file, name, contigs, order, reversed_c):
        """
        Save index

        :param index_file: index file path
        :type index_file: str
        :param name: sample name
        :type name: str
        :param contigs: contigs size
        :type contigs: dict
        :param order: contifs order
        :type order: list
        :param reversed_c: reversed status for each contig
        :type reversed_c: dict
        """
        with open(index_file, "w") as idx:
            idx.write(name + "\n")
            for contig in order:
                idx.write("\t".join([contig, str(contigs[contig]), "1" if reversed_c[contig] else "0"])
                          + "\n")


def index_file(fasta_path, fasta_name, out, write_fa=None):
    """
    Index fasta file

    :param fasta_path: fasta file path
    :type fasta_path: str
    :param fasta_name: sample name
    :type fasta_name: str
    :param out: output index file
    :type out: str
    :param write_fa: file path of the new fasta file to write, None to don't save fasta in a new file
    :type write_fa: str
    :return:
        * [0] True if success, else False
        * [1] Number of contigs
        * [2] Error message
    :rtype: (bool, int, str)
    """
    has_header = False
    next_header = False  # True if next line must be a header line
    compressed = fasta_path.endswith(".gz")
    nb_contigs = 0
    write_f = None
    if write_fa is not None:
        write_f = open(write_fa, "w")
    with (xopen(fasta_path) if compressed else open(fasta_path)) as fasta, \
            open(out, "w") as out_file:
        out_file.write(fasta_name + "\n")
        contig = None
        len_c = 0
        nb_line = 0
        for line in fasta:
            nb_line += 1
            if write_f is not None:
                write_f.write(line)
            line = line.strip("\n")
            if re.match(r"^>.+", line) is not None:
                has_header = True
                next_header = False
                if contig is not None:
                    if len_c > 0:
                        nb_contigs += 1
                        out_file.write("%s\t%d\n" % (contig, len_c))
                    else:
                        return False, 0, "Error: contig is empty: %s" % contig
                contig = re.split("\s", line[1:])[0]
                len_c = 0
            elif len(line) > 0:
                if next_header or re.match(r"^[ATGCKMRYSWBVHDXN.\-]+$", line.upper()) is None:
                    if next_header:
                        return False, 0, "Error: new header line expected at line %d" % nb_line
                    return False, 0, "Error: invalid sequence at line %d" % nb_line
                len_c += len(line)
            elif len(line) == 0:
                next_header = True

        if contig is not None and len_c > 0:
            nb_contigs += 1
            out_file.write("%s\t%d\n" % (contig, len_c))

    if write_f is not None:
        write_f.close()

    return has_header, nb_contigs, ""


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Split huge contigs")
    parser.add_argument('-i', '--input', type=str, required=True, help="Input fasta file")
    parser.add_argument('-n', '--name', type=str, required=True, help="Input name")
    parser.add_argument('-o', '--output', type=str, required=True, help="Output index file")
    args = parser.parse_args()

    success, nb_contigs, message = index_file(args.input, args.name, args.output)
    if success:
        print("Success!")
    else:
        print(message)
