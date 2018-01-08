#!/usr/bin/env python3

import io
import re
import gzip


def index_file(fasta_path, fasta_name, out):
    has_header = False
    next_header = False  # True if next line must be a header line
    compressed = fasta_path.endswith(".gz")
    with (gzip.open(fasta_path) if compressed else open(fasta_path)) as in_file, \
            open(out, "w") as out_file:
        out_file.write(fasta_name + "\n")
        with (io.TextIOWrapper(in_file) if compressed else in_file) as fasta:
            contig = None
            len_c = 0
            for line in fasta:
                line = line.strip("\n")
                if re.match(r"^>.+", line) is not None:
                    has_header = True
                    next_header = False
                    if contig is not None:
                        if len_c > 0:
                            out_file.write("%s\t%d\n" % (contig, len_c))
                        else:
                            return False
                    contig = re.split("\s", line[1:])[0]
                    len_c = 0
                elif len(line) > 0:
                    if next_header or re.match(r"^[ATGCKMRYSWBVHDXN.\-]+$", line.upper()) is None:
                        return False
                    len_c += len(line)
                elif len(line) == 0:
                    next_header = True

            if contig is not None and len_c > 0:
                out_file.write("%s\t%d\n" % (contig, len_c))

    return has_header


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Split huge contigs")
    parser.add_argument('-i', '--input', type=str, required=True, help="Input fasta file")
    parser.add_argument('-n', '--name', type=str, required=True, help="Input name")
    parser.add_argument('-o', '--output', type=str, required=True, help="Output index file")
    args = parser.parse_args()

    if index_file(args.input, args.name, args.output):
        print("Success!")
    else:
        print("Error while building index")
