#!/usr/bin/env python3

import argparse
import time
import os
import sys
from split_fa import Splitter
from filter_contigs import Filter
from index import index_file


def index_fasta(name, filepath, out_dir, type_f, dofilter = True):
    """
    Index and filter fasta

    :param name: name of the specie
    :param filepath: full path of the fasta file
    :param out_dir: output folder
    :param type_f: type of fasta (query or target)
    """
    uncompressed = None
    if filepath.endswith(".gz") and dofilter:
        uncompressed = filepath[:-3]
    index = os.path.join(out_dir, type_f + ".idx")
    success, nb_contigs, error = index_file(filepath, name, index, uncompressed)
    if success:
        is_filtered = False
        if dofilter:
            in_fasta = filepath
            if uncompressed is not None:
                in_fasta = uncompressed
            filtered_fasta = os.path.join(os.path.dirname(in_fasta), "filtered_" + os.path.basename(in_fasta))
            filter_f = Filter(fasta=in_fasta,
                              index_file=index,
                              type_f=type_f,
                              min_filtered=nb_contigs / 4,
                              split=False,
                              out_fasta=filtered_fasta,
                              replace_fa=True)
            is_filtered = filter_f.filter()
        if uncompressed is not None:
            if is_filtered:
                os.remove(filepath)
                with open(os.path.join(out_dir, "." + type_f), "w") as save_file:
                    save_file.write(uncompressed)
            else:
                os.remove(uncompressed)

    else:
        print("###ERR### %s fasta  file is not valid:<br/> %s" % (type_f[0].upper() + type_f[1:], error), file=sys.stderr)
        if uncompressed is not None:
            try:
                os.remove(uncompressed)
            except FileNotFoundError:
                pass
        exit(1)


parser = argparse.ArgumentParser(description="Split huge contigs")
parser.add_argument('-q', '--query', type=str, required=False, help="Query fasta file")
parser.add_argument('-u', '--query-split', type=str, required=False, help="Query fasta file split")
parser.add_argument('-t', '--target', type=str, required=False, help="Target fasta file")
parser.add_argument('-n', '--query-name', type=str, required=False, help="Query name")
parser.add_argument('-m', '--target-name', type=str, required=False, help="Target name")
parser.add_argument('-s', '--size', type=int, required=False, default=10,
                    help="Max size of contigs (Mb) - for query split")
parser.add_argument('-p', '--preptime-file', type=str, required=True, help="File into save prep times")
parser.add_argument('--split', type=bool, const=True, nargs="?", required=False, default=False,
                        help="Split query")
parser.add_argument('--index-only', type=bool, const=True, nargs="?", required=False, default=False,
                        help="Index files only. No split, no filter.")
args = parser.parse_args()

if args.index_only and args.split:
    raise Exception("--index-only and --split arguments are mutually exclusive")

out_dir = os.path.dirname(args.target)

with open(args.preptime_file, "w") as ptime:
    ptime.write(str(round(time.time())) + "\n")
    if args.query is not None:
        if args.split:
            print("Splitting query...")
            fasta_in = args.query
            index_split = os.path.join(out_dir, "query_split.idx")
            splitter = Splitter(input_f=fasta_in, name_f=args.query_name, output_f=args.query_split,
                                query_index=index_split)
            success, error = splitter.split()
            if success:
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
                print("###ERR### Query fasta file is not valid:<br/> %s" % error, file=sys.stderr)
                exit(1)
        else:
            print("Indexing query...")
            index_fasta(name=args.query_name, filepath=args.query, out_dir=out_dir, type_f="query",
                        dofilter=not args.index_only)
    if args.target is not None:
        print("Indexing target...")
        index_fasta(name=args.target_name, filepath=args.target, out_dir=out_dir, type_f="target",
                    dofilter=not args.index_only)

    ptime.write(str(round(time.time())) + "\n")

print("DONE!")
