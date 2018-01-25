#!/usr/bin/env python3

import argparse
import time
import os
from split_fa import Splitter
from filter_contigs import Filter
from index import index_file

parser = argparse.ArgumentParser(description="Split huge contigs")
parser.add_argument('-q', '--query', type=str, required=False, help="Query fasta file")
parser.add_argument('-u', '--query-split', type=str, required=False, help="Query fasta file split")
parser.add_argument('-t', '--target', type=str, required=True, help="Target fasta file")
parser.add_argument('-n', '--query-name', type=str, required=False, help="Query name")
parser.add_argument('-m', '--target-name', type=str, required=True, help="Target name")
parser.add_argument('-s', '--size', type=int, required=False, default=10,
                    help="Max size of contigs (Mb) - for query split")
parser.add_argument('-p', '--preptime-file', type=str, required=True, help="File into save prep times")
args = parser.parse_args()

out_dir = os.path.dirname(args.target)

with open(args.preptime_file, "w") as ptime:
    ptime.write(str(round(time.time())) + "\n")
    if args.query is not None:
        print("Splitting query...")
        fasta_in = args.query
        index_split = os.path.join(out_dir, "query_split.idx")
        splitter = Splitter(input_f=fasta_in, name_f=args.query_name, output_f=args.query_split,
                            query_index=index_split)
        if splitter.split():
            filtered_fasta = os.path.join(os.path.dirname(args.query_split), "filtered_" +
                                          os.path.basename(args.query_split))
            filter_f = Filter(fasta=args.query_split,
                              index_file=index_split,
                              type_f="query",
                              min_filtered=splitter.nb_contigs / 4,
                              split=True,
                              out_fasta=filtered_fasta,
                              replace_fa=True)
            filter_f.filter()
        else:
            exit(1)
    print("Indexing target...")
    uncompressed = None
    if args.target.endswith(".gz"):
        uncompressed = args.target[:-3]
    target_index = os.path.join(out_dir, "target.idx")
    success, nb_contigs = index_file(args.target, args.target_name, target_index, uncompressed)
    if success:
        in_fasta = args.target
        if uncompressed is not None:
            in_fasta = uncompressed
        filtered_fasta = os.path.join(os.path.dirname(in_fasta), "filtered_" + os.path.basename(in_fasta))
        filter_f = Filter(fasta=in_fasta,
                          index_file=target_index,
                          type_f="target",
                          min_filtered=nb_contigs / 4,
                          split=False,
                          out_fasta=filtered_fasta,
                          replace_fa=True)
        is_filtered = filter_f.filter()
        if uncompressed is not None:
            if is_filtered:
                os.remove(args.target)
                with open(os.path.join(out_dir, ".target"), "w") as save_file:
                    save_file.write(uncompressed)
            else:
                os.remove(uncompressed)
    else:
        if uncompressed is not None:
            try:
                os.remove(uncompressed)
            except FileNotFoundError:
                pass
        exit(1)
    ptime.write(str(round(time.time())) + "\n")

print("DONE!")
