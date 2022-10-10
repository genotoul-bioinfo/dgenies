#!/usr/bin/env python3

import os
from math import sqrt

__NAME__ = "Sort_paf"
__VERSION__ = 0.1


class Sorter:
    """
    Sort PAF file by match size
    """

    def __init__(self, input_f, output_f):
        """

        :param input_f: input fasta file path
        :type input_f: str
        :param output_f: output fasta file path
        :type output_f: str
        """
        self.input_f = input_f
        self.output_f = output_f

    def sort(self):
        """
        Launch sort staff
        """
        paf_lines = self._get_sorted_paf_lines()
        with open(self.output_f, "w") as out:
            out.write("\n".join(["\t".join(x[:-1]) for x in paf_lines]))

    def _sort_lines(self, lines):
        """
        Sort lines stuff

        :param lines: lines of PAF file to be sorted
        :type lines: _io.TextIO
        :return: sorted lines
        :rtype: list
        """
        paf_lines = []
        nb_lines = 0
        min_len = 0
        for line in lines:
            parts = line.strip("\n").split("\t")
            # len_line is length (euclidean distance) x similarity score
            len_line = sqrt(pow(int(parts[3]) - int(parts[2]), 2) +
                            pow(int(parts[8]) - int(parts[7]), 2)) * (int(parts[9]) / int(parts[10]))
            # len_line is "added" as a new column
            parts.append(len_line)
            nb_lines += 1
            # We add the first 1_000_000 lines
            if nb_lines <= 1000000:
                paf_lines.append(parts)
                if nb_lines == 1000000:
                    # When line limit is reached, we switch to the most representative strategy
                    # We will drop the smallest ones from current selection and only add long ones
                    print("Sorting lines...")
                    # We sort them by len_line in desc. order
                    paf_lines.sort(key=lambda x: -x[-1])
                    # We look at the input file in order to know the proportion of lines in % to keep
                    with open(self.input_f, 'r') as paf:
                        num_lines = sum(1 for line in paf)
                    pct_to_keep = 2000000 / num_lines
                    # We remove small lines
                    limit = int(nb_lines * pct_to_keep)
                    paf_lines = paf_lines[:limit]
                    # We set a min length for next lines
                    min_len = paf_lines[-1][-1]
                    print("Sorting done!")
            elif len_line >= min_len:
                # We only keep long enough lines
                print("Processing line %d..." % nb_lines)
                paf_lines.append(parts)
        paf_lines.sort(key=lambda x: -x[-1])

        return paf_lines

    def _get_sorted_paf_lines(self):
        """
        Get sorted PAF

        :return: sorted PAF lines
        """
        with open(self.input_f, "r") as lines:
            paf_lines = self._sort_lines(lines)
        return paf_lines


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Sort PAF file with size of matches (DESC)")
    parser.add_argument('-i', '--input', type=str, required=True, help="Input PAF file")
    parser.add_argument('-o', '--output', type=str, required=True, help="Output PAF file")

    args = parser.parse_args()
    if args["--version"]:
        print(__NAME__, __VERSION__)
    else:
        if not os.path.exists(args.input):
            raise Exception("Input PAF file %s does not exists" % args.input)
        sorter = Sorter(args.input, args.output)
        sorter.sort()
