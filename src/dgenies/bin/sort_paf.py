#!/usr/bin/env python3

import os
from math import sqrt

__NAME__ = "Sort_paf"
__VERSION__ = 0.1


class Sorter:

    def __init__(self, input_f, output_f):
        self.input_f = input_f
        self.output_f = output_f

    def sort(self):
        paf_lines = self._get_sorted_paf_lines()
        with open(self.output_f, "w") as out:
            out.write("\n".join(["\t".join(x[:-1]) for x in paf_lines]))

    @staticmethod
    def _sort_key_paf_lines(a):
        x1 = int(a[2])
        x2 = int(a[3])
        y1 = int(a[7])
        y2 = int(a[8])
        return -sqrt(pow(x2 - x1, 2) + pow(y2 - y1, 2)) * (int(a[9]) / int(a[10]))

    def _insert_line(self, line, paf_lines, next_search, min_search, max_search):
        # print(line[3],".",line[2],".",line[8],".",line[7],".",line[9],".",line[10],".")
        len_line = line[-1]
        paf_line = paf_lines[next_search]
        len_paf_line = paf_line[-1]
        if len_line > len_paf_line:
            if next_search == min_search:
                paf_lines.insert(next_search, line)
            else:
                paf_line_next = paf_lines[next_search - 1]
                len_paf_line_next = paf_line_next[-1]
                if len_line < len_paf_line_next:
                    paf_lines.insert(next_search, line)
                elif next_search == 1:
                    paf_lines.insert(0, line)
                else:
                    paf_lines = self._insert_line(line=line,
                                                  paf_lines=paf_lines,
                                                  next_search=min((next_search - min_search) // 2, next_search - 1),
                                                  min_search=min_search,
                                                  max_search=next_search)
        elif len_line < len_paf_line:
            if next_search == max_search:
                paf_lines.insert(next_search + 1, line)
            else:
                paf_line_next = paf_lines[next_search+1]
                len_paf_line_next = paf_line_next[-1]
                if len_line > len_paf_line_next:
                    paf_lines.insert(next_search + 1, line)
                elif next_search == len(paf_lines) - 2:
                    paf_lines.append(line)
                else:
                    paf_lines = self._insert_line(line=line,
                                                  paf_lines=paf_lines,
                                                  next_search=min(max(next_search + ((max_search - next_search) // 2),
                                                                  next_search + 1), len(paf_lines)),
                                                  min_search=next_search,
                                                  max_search=max_search)
        elif len_line == len_paf_line:
            paf_lines.insert(next_search + 1, line)
        if len(paf_lines) > 300000:
            paf_lines = paf_lines[:300000]
        return paf_lines

    def _sort_lines(self, lines):
        paf_lines = []
        nb_lines = 0
        min_len = 0
        for line in lines:
            parts = line.strip("\n").split("\t")
            len_line = sqrt(pow(int(parts[3]) - int(parts[2]), 2) +
                            pow(int(parts[8]) - int(parts[7]), 2)) * (int(parts[9]) / int(parts[10]))
            parts.append(len_line)
            nb_lines += 1
            if nb_lines <= 1000000:
                paf_lines.append(parts)
                if nb_lines == 1000000:
                    print("Sorting lines...")
                    paf_lines.sort(key=lambda x: -x[-1])
                    with open(self.input_f, 'r') as paf:
                        num_lines = sum(1 for line in paf)
                    pct_to_keep = 2000000 / num_lines
                    limit = int(nb_lines * pct_to_keep)
                    paf_lines = paf_lines[:limit]
                    print(len(paf_lines))
                    min_len = paf_lines[-1][-1]
                    print(min_len)
                    print("Sorting done!")
            elif len_line >= min_len:
                print("Processing line %d..." % nb_lines)
                paf_lines.append(parts)
                print(len(paf_lines))
        paf_lines.sort(key=lambda x: -x[-1])

        return paf_lines

    def _get_sorted_paf_lines(self):
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
